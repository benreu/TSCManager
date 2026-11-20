"""
TSC's TSPL2 file commands: store, list, delete and test-print fonts and
images in a printer's memory.

From the TSPL/TSPL2 Programming Manual 3.0 (tspl_manual.pdf; the page
numbers here are the manual's own). What the manual leaves open - the exact
shape of ~!F's reply, how OUT frames an answer, which way round a BMP
prints - is settled against a printer with `tscmanager.py --probe`, and the
parsers here follow what the printer does.

- DOWNLOAD [n,]"NAME",size,data stores a file (p.150). n is nothing for
  DRAM, F for flash, E for a memory card. DRAM is lost at power off.
  File names are case sensitive.
- KILL [n,]"NAME" deletes one, with the same n; * is a wildcard (p.154).
- MOVE copies what is in DRAM to flash (p.156).
- ~!F lists the files: each name ends 0x0D, the list ends 0x1A (p.140).
  FILES is no use here: it prints the list on a label (p.153).
- ~!A is the free memory in bytes (p.136), ~!T the model (p.142).
- OUT "";GETSETTING$(...) answers a setting back down the same port
  (pp.215, 305); firmware V6.93 EZ and later.

The printer has to be taking TSPL: on a TSC that is set to emulate ZPL,
these are not understood. That is a printer setting, not sent from here.

Every function that talks to a printer takes a connection.Printer and
blocks, so a frontend runs it off its GUI thread. The queries return None
when the printer could not be asked, but let a PortProblem through: its
text tells the user how to fix a USB port, where "could not be asked" would
not.
"""

import re
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from . import connection
from .local_port import PortProblem

DRAM, FLASH, CARD = 'dram', 'flash', 'card'
MEMORIES = (DRAM, FLASH, CARD)
MEMORY_NAMES = {DRAM: 'DRAM', FLASH: 'Flash', CARD: 'Card'}
_SELECTOR = {DRAM: '', FLASH: 'F,', CARD: 'E,'}

FONT, IMAGE, PROGRAM, OTHER = 'font', 'image', 'program', 'other'
KIND_NAMES = {FONT: 'Font', IMAGE: 'Image', PROGRAM: 'Program', OTHER: 'File'}
_KINDS = {'.TTF': FONT, '.TTC': FONT, '.FNT': FONT,
          '.BMP': IMAGE, '.PCX': IMAGE, '.PNG': IMAGE,
          '.BAS': PROGRAM}

# Up to 50 files fit in DRAM; flash holds 256 on a TSPL2 printer (p.149).
MAX_DRAM_FILES = 50
MAX_FLASH_FILES = 256

# DOWNLOAD's data goes out in pieces of this size, so a bar can follow it.
CHUNK = 16384


def kind_of(name: str) -> str:
    """FONT, IMAGE, PROGRAM or OTHER, by the file name's extension."""
    dot = name.rfind('.')
    return _KINDS.get(name[dot:].upper(), OTHER) if dot >= 0 else OTHER


def name_problem(name: str) -> Optional[str]:
    """Why `name` cannot be a file name on the printer, or None if it can.

    TSPL quotes a name with " and has no way to escape one inside it, and a
    line break would end the command; anything outside printable ASCII is
    refused too, since the manual says nothing about how a printer would
    take it."""
    if not name.strip():
        return "The name is empty."
    if '"' in name:
        return "A name cannot hold a double quote (\")."
    if not all(' ' <= c <= '~' for c in name):
        return "A name can only hold plain ASCII letters, digits and signs."
    if '.' not in name.strip('.'):
        return "A name needs an extension, such as .TTF or .BMP."
    return None


def _check_name(name: str) -> None:
    problem = name_problem(name)
    if problem:
        raise ValueError(f"{problem} ({name!r})")


def suggest_name(source: str, extension: str,
                 taken: Iterable[str] = ()) -> str:
    """A printer name for a file called `source`: its first eight letters,
    digits, _ or - in capitals, then `extension` (".TTF"). A name already
    `taken` (compared without case, so two names that differ only in case
    never sit side by side) gets a number in place of its last letters."""
    stem = source.rsplit('/', 1)[-1]
    if '.' in stem:
        stem = stem[:stem.rindex('.')]
    stem = re.sub(r'[^A-Za-z0-9_-]', '', stem).upper()[:8] or 'FILE'
    extension = extension.upper()
    used = {t.upper() for t in taken}
    name = stem + extension
    number = 1
    while name in used:
        suffix = str(number)
        name = stem[:8 - len(suffix)] + suffix + extension
        number += 1
    return name


# --- storing and deleting ---------------------------------------------------

def build_download(name: str, data: bytes, memory: str = DRAM) -> bytes:
    """DOWNLOAD [n,]"NAME",size,data - the name as given, case kept."""
    _check_name(name)
    header = f'DOWNLOAD {_SELECTOR[memory]}"{name}",{len(data)},'
    return header.encode('ascii') + data


def upload(printer: 'connection.Printer', name: str, data: bytes,
           memory: str = DRAM, timeout: float = 30, cancel=None,
           progress: Optional[Callable[[int, int], None]] = None) -> None:
    """Store `data` on the printer as `name`. Raises on failure."""
    payload = build_download(name, data, memory)
    chunks = (payload[i:i + CHUNK] for i in range(0, len(payload), CHUNK))
    connection.send_stream(printer, chunks, len(payload), timeout,
                           cancel=cancel, progress=progress)


def build_kill(name: str, memory: str = DRAM) -> bytes:
    """KILL [n,]"NAME"."""
    _check_name(name)
    return f'KILL {_SELECTOR[memory]}"{name}"\r\n'.encode('ascii')


def delete(printer: 'connection.Printer', name: str,
           memories: Iterable[str] = (DRAM,), timeout: float = 10,
           cancel=None) -> None:
    """KILL `name` from each of `memories`, in one send."""
    payload = b''.join(build_kill(name, memory) for memory in memories)
    connection.send(printer, payload, timeout, cancel=cancel)


MOVE = b'MOVE\r\n'


def move_to_flash(printer: 'connection.Printer', timeout: float = 30,
                  cancel=None) -> None:
    """MOVE: what is in DRAM goes to flash, to outlast a power off."""
    connection.send(printer, MOVE, timeout, cancel=cancel)


# --- asking ---------------------------------------------------------------

LIST_FILES = b'~!F'
FREE_MEMORY = b'~!A'
MODEL = b'~!T'
END_OF_LIST = b'\x1a'


def _ask(printer, request: bytes, timeout: float, cancel) -> Optional[bytes]:
    """The printer's reply to `request`; None if it could not be asked.
    A PortProblem is let through, and so is Cancelled."""
    try:
        return connection.send(printer, request, timeout, read_reply=True,
                               cancel=cancel)
    except PortProblem:
        raise
    except OSError:
        return None


def parse_file_list(reply: bytes) -> List[str]:
    """~!F's reply: names each ending 0x0D, the list ending 0x1A. Anything
    after the 0x1A is not part of it."""
    body = reply.split(END_OF_LIST, 1)[0]
    names = []
    for line in body.replace(b'\n', b'\r').split(b'\r'):
        name = line.strip().decode('latin-1')
        if name:
            names.append(name)
    return names


def list_files(printer: 'connection.Printer', timeout: float = 5,
               cancel=None) -> Optional[List[str]]:
    """The names of the files in the printer's memory, or None if it did
    not answer. An empty reply is an empty printer only if it carried the
    0x1A that ends a list; silence is no answer."""
    reply = _ask(printer, LIST_FILES, timeout, cancel)
    if not reply:
        return None
    return parse_file_list(reply)


def parse_number(reply: bytes) -> Optional[int]:
    """The first run of digits in a reply such as ~!A's, or None."""
    found = re.search(rb'\d+', reply or b'')
    return int(found.group()) if found else None


@dataclass
class Info:
    """What a printer says about itself. Any field the printer did not
    answer is None (or missing from `memory`)."""
    model: Optional[str] = None
    version: Optional[str] = None
    serial: Optional[str] = None
    dpi: Optional[int] = None
    free: Optional[int] = None               # ~!A, bytes
    memory: Dict[str, Tuple[Optional[int], Optional[int]]] = field(
        default_factory=dict)                 # memory -> (capacity, available)
    card_installed: Optional[bool] = None


# Each answer comes back behind a tag of our own, so a setting the firmware
# does not know (or a line it drops) cannot shift the ones after it.
_SETTINGS = (
    ('model', 'SYSTEM', 'INFORMATION', 'MODEL'),
    ('version', 'SYSTEM', 'INFORMATION', 'VERSION'),
    ('serial', 'SYSTEM', 'INFORMATION', 'SERIAL'),
    ('dpi', 'SYSTEM', 'INFORMATION', 'DPI'),
    ('dram_capacity', 'FILE', 'DRAM', 'CAPACITY'),
    ('dram_available', 'FILE', 'DRAM', 'AVAILABLE'),
    ('flash_capacity', 'FILE', 'FLASH', 'CAPACITY'),
    ('flash_available', 'FILE', 'FLASH', 'AVAILABLE'),
    ('card_installed', 'FILE', 'CARD', 'INSTALLED'),
    ('card_capacity', 'FILE', 'CARD', 'CAPACITY'),
    ('card_available', 'FILE', 'CARD', 'AVAILABLE'),
)


def build_settings_request() -> bytes:
    lines = [f'OUT "{tag}=";GETSETTING$("{app}","{sec}","{key}")'
             for tag, app, sec, key in _SETTINGS]
    return ("\r\n".join(lines) + "\r\n").encode('ascii')


def parse_settings(reply: bytes) -> Dict[str, str]:
    """`tag=value` lines from build_settings_request(), as {tag: value}."""
    tags = {tag for tag, *_ in _SETTINGS}
    found = {}
    for line in reply.decode('latin-1').replace('\n', '\r').split('\r'):
        tag, sep, value = line.partition('=')
        if sep and tag.strip() in tags:
            found[tag.strip()] = value.strip()
    return found


def _int(text: Optional[str]) -> Optional[int]:
    return parse_number(text.encode('latin-1')) if text else None


def info_from(model_reply: Optional[bytes], free_reply: Optional[bytes],
              settings: Dict[str, str]) -> Info:
    """An Info from ~!T's and ~!A's replies and the GETSETTING$ answers."""
    info = Info()
    info.model = settings.get('model') or (
        model_reply.decode('latin-1').strip(' \r\n\x00') if model_reply
        else None) or None
    info.version = settings.get('version') or None
    info.serial = settings.get('serial') or None
    info.dpi = _int(settings.get('dpi'))
    info.free = parse_number(free_reply) if free_reply else None
    installed = settings.get('card_installed')
    info.card_installed = None if installed is None else installed == '1'
    for memory in MEMORIES:
        capacity = _int(settings.get(f'{memory}_capacity'))
        available = _int(settings.get(f'{memory}_available'))
        if capacity is not None or available is not None:
            info.memory[memory] = (capacity, available)
    return info


def query_info(printer: 'connection.Printer', timeout: float = 3,
               cancel=None) -> Optional[Info]:
    """Model, firmware, dpi and memory, or None if the printer answered
    nothing at all. Older firmware (before V6.93 EZ) has no OUT, so then
    only ~!T's model and ~!A's free memory are filled in."""
    model = _ask(printer, MODEL, timeout, cancel)
    free = _ask(printer, FREE_MEMORY, timeout, cancel)
    reply = _ask(printer, build_settings_request(), timeout, cancel)
    if not (model or free or reply):
        return None
    return info_from(model, free, parse_settings(reply or b''))


# --- test labels ----------------------------------------------------------

SAMPLE_TEXT = "The quick brown fox 0123456789"


def quote_text(text: str) -> str:
    """Text for inside a TSPL string: a " is written \\["] (p.115), and a
    line break, which would end the command, becomes a space."""
    text = text.replace('\r', ' ').replace('\n', ' ')
    return text.replace('"', '\\["]')


def _label(lines: List[str]) -> bytes:
    """A label from its drawing commands. No SIZE or GAP: the printer keeps
    the media it is set up for."""
    return ("\r\n".join(["CLS"] + lines + ["PRINT 1,1"]) + "\r\n").encode(
        'cp1252', 'replace')


def build_font_test(name: str, text: str = SAMPLE_TEXT,
                    points: int = 24) -> bytes:
    """A label of `text` in the stored font `name`. For a .TTF, TEXT reads
    its two multipliers as the width and height in points (p.114). The
    caption is in built-in font 2, which every TSPL printer has."""
    _check_name(name)
    if name.upper().endswith(('.TTF', '.TTC')):
        caption, scale = f"{name} at {points} pt", f"{points},{points}"
    else:
        # A bitmap font's multipliers are a scale, 1 to 10.
        caption, scale = name, "1,1"
    return _label([
        f'TEXT 20,20,"2",0,1,1,"{quote_text(caption)}"',
        f'TEXT 20,60,"{name}",0,{scale},"{quote_text(text)}"',
    ])


def build_image_test(name: str, bpp: int = 1, contrast: int = 80) -> bytes:
    """A label showing the stored image `name`: PUTBMP, PUTPCX or PUTPNG
    by its extension (pp.92-95). `bpp` 8 prints a BMP in grey, which needs
    firmware V6.91 EZ or later and direct thermal printing."""
    _check_name(name)
    extension = name[name.rfind('.'):].upper()
    if extension == '.PCX':
        draw = f'PUTPCX 20,60,"{name}"'
    elif extension == '.PNG':
        draw = f'PUTPNG 20,60,"{name}"'
    elif bpp == 8:
        draw = f'PUTBMP 20,60,"{name}",8,{contrast}'
    else:
        draw = f'PUTBMP 20,60,"{name}"'
    return _label([f'TEXT 20,20,"2",0,1,1,"{quote_text(name)}"', draw])


def test_print(printer: 'connection.Printer', name: str, timeout: float = 15,
               cancel=None, **options) -> None:
    """Print a test label for the stored font or image `name`."""
    kind = kind_of(name)
    if kind == FONT:
        payload = build_font_test(name, **options)
    elif kind == IMAGE:
        payload = build_image_test(name, **options)
    else:
        raise ValueError(f"{name} is neither a font nor an image")
    connection.send(printer, payload, timeout, cancel=cancel)

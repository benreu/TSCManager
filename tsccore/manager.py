"""
What both frontends show and decide, without a widget in sight: the lines
of text, the list rows, which buttons can be pressed, the checks before an
upload, and the work each button sends off to the printer.

A frontend builds widgets, runs `load()`, `upload()` and the rest on its
busy bar's worker thread, and puts the strings from here on screen. Both
frontends doing that is what keeps them the same.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from . import connection, tspl
from .tspl import CARD, DRAM, FLASH

APP_NAME = "TSC Manager"

NOT_CONNECTED = "Not connected. Choose the printer and press Connect."
NO_ANSWER = ("The printer did not answer. Check that it is switched on, that "
             "the address is right, and that it is set to TSPL rather than "
             "ZPL emulation.")
PICK_A_FILE = "Pick a file in the list."


# --- the printer's state ----------------------------------------------------

@dataclass
class Loaded:
    """What one Connect or Refresh found out."""
    info: Optional[tspl.Info]
    names: Optional[List[str]]       # None: the file list did not come back

    @property
    def answered(self) -> bool:
        return self.info is not None or self.names is not None


def load(printer: 'connection.Printer', cancel=None) -> Loaded:
    """Ask the printer about itself and its files. Runs on a worker."""
    info = tspl.query_info(printer, cancel=cancel)
    names = tspl.list_files(printer, cancel=cancel) if info is not None else None
    return Loaded(info, names)


def printer_line(printer: Optional['connection.Connection'],
                 info: Optional[tspl.Info]) -> str:
    """`TSC MB241 at 192.168.50.235 · firmware 1.28.002 · 203 dpi`."""
    if printer is None or info is None:
        return NOT_CONNECTED
    parts = [f"{info.model or 'Printer'} at {printer.where(with_port=False)}"
             if not printer.is_usb else f"{info.model or 'Printer'} by USB"]
    if info.version:
        parts.append(f"firmware {info.version}")
    if info.dpi:
        parts.append(f"{info.dpi} dpi")
    return " · ".join(parts)


def format_kb(kb: Optional[int]) -> str:
    """KB as the printer counts it, for reading: `850 KB`, `8.0 MB`."""
    if kb is None:
        return "?"
    if kb < 1024:
        return f"{kb} KB"
    return f"{kb / 1024:.1f} MB"


def memory_line(info: Optional[tspl.Info]) -> str:
    """`DRAM 8.0 MB free of 8.0 MB · Flash 206.7 MB free of 207.4 MB`;
    a card only when one is installed."""
    if info is None:
        return ""
    parts = []
    for memory in (DRAM, FLASH, CARD):
        if memory not in info.memory:
            continue
        capacity, available = info.memory[memory]
        text = f"{tspl.MEMORY_NAMES[memory]} {format_kb(available)} free"
        if capacity:
            text += f" of {format_kb(capacity)}"
        parts.append(text)
    if not parts and info.free_bytes is not None:
        parts.append(f"{format_kb(info.free_bytes // 1024)} free")
    return " · ".join(parts)


def dram_in_use(info: Optional[tspl.Info]) -> Optional[bool]:
    """Whether anything sits in DRAM - what MOVE would carry to flash - or
    None when the printer did not say."""
    if info is None or DRAM not in info.memory:
        return None
    capacity, available = info.memory[DRAM]
    if capacity is None or available is None:
        return None
    return available < capacity


# --- the file list ----------------------------------------------------------

@dataclass
class Row:
    name: str
    kind: str          # tspl.FONT, IMAGE, PROGRAM or OTHER

    @property
    def kind_label(self) -> str:
        return tspl.KIND_NAMES[self.kind]


def rows(names: Optional[Sequence[str]]) -> List[Row]:
    """The list rows, in the printer's order (DRAM's files first)."""
    return [Row(name, tspl.kind_of(name)) for name in (names or ())]


def files_status(loaded: Optional[Loaded]) -> str:
    if loaded is None:
        return NOT_CONNECTED
    if not loaded.answered:
        return NO_ANSWER
    if loaded.names is None:
        return "The printer did not send its file list."
    count = len(loaded.names)
    if count == 0:
        return "No fonts or images are stored on the printer."
    return f"{count} file{'s' if count != 1 else ''} on the printer."


ACTIONS = ('upload_font', 'upload_image', 'delete', 'test_print',
           'move_to_flash', 'refresh')

ACTION_LABELS = {
    'upload_font': "Upload Font…",
    'upload_image': "Upload Image…",
    'delete': "Delete",
    'test_print': "Test Print",
    'move_to_flash': "Move DRAM to Flash",
    'refresh': "Refresh",
}

ACTION_TIPS = {
    'upload_font': "Store a TrueType font on the printer.",
    'upload_image': "Store a picture on the printer, as a BMP or PNG.",
    'delete': "Delete the chosen file from the printer's memory.",
    'test_print': "Print a label in the chosen font, or showing the chosen "
                  "image, on the labels loaded now.",
    'move_to_flash': "Move every file in DRAM to flash, so it is kept when "
                     "the printer is switched off.",
    'refresh': "Ask the printer again for its files and memory.",
}


def enabled_actions(connected: bool, selected: Optional[Row],
                    info: Optional[tspl.Info] = None) -> Dict[str, bool]:
    """Which buttons can be pressed. Move needs something in DRAM, when
    the printer says how much DRAM is in use."""
    printable = selected is not None and selected.kind in (tspl.FONT,
                                                           tspl.IMAGE)
    in_dram = dram_in_use(info)
    return {
        'upload_font': connected,
        'upload_image': connected,
        'delete': connected and selected is not None,
        'test_print': connected and printable,
        'move_to_flash': connected and in_dram is not False,
        'refresh': connected,
    }


# --- uploading -------------------------------------------------------------

def memory_choices(info: Optional[tspl.Info]) -> List[Tuple[str, str]]:
    """(memory, label) for the Memory list of an upload, flash first: a
    font or image is usually wanted after a power off."""
    choices = [(FLASH, "Flash (kept when switched off)"),
               (DRAM, "DRAM (lost when switched off)")]
    if info is not None and info.card_installed:
        choices.append((CARD, "Memory card"))
    return choices


def delete_memories(info: Optional[tspl.Info]) -> Tuple[str, ...]:
    """Every memory a file could be in: ~!F does not say which."""
    if info is not None and info.card_installed:
        return (DRAM, FLASH, CARD)
    return (DRAM, FLASH)


def upload_problem(name: str, size: int, memory: str,
                   info: Optional[tspl.Info]) -> Optional[str]:
    """Why this upload cannot go ahead, or None."""
    problem = tspl.name_problem(name)
    if problem:
        return problem
    if info is not None and memory in info.memory:
        available = info.memory[memory][1]
        if available is not None and -(-size // 1024) > available:
            return (f"{format_kb(-(-size // 1024))} does not fit: "
                    f"{tspl.MEMORY_NAMES[memory]} has {format_kb(available)} "
                    f"free.")
    return None


def upload_note(name: str, size: int, memory: str,
                info: Optional[tspl.Info],
                names: Sequence[str] = ()) -> str:
    """The line under an upload's name: its size and the space left, or
    what is wrong, and a warning when it replaces a stored file."""
    problem = upload_problem(name, size, memory, info)
    if problem:
        return problem
    text = f"{format_kb(-(-size // 1024))}"
    if info is not None and memory in info.memory:
        available = info.memory[memory][1]
        if available is not None:
            text += f"; {tspl.MEMORY_NAMES[memory]} has " \
                    f"{format_kb(available)} free"
    text += "."
    if name in names:
        text += f" It replaces the {name} already on the printer."
    return text


def upload(printer: 'connection.Printer', name: str, data: bytes,
           memory: str, cancel=None, fraction=None) -> None:
    """Store a file, reporting `fraction(0..1)` as it goes. Worker."""
    progress = (lambda sent, total: fraction(sent / total)) if fraction \
        else None
    tspl.upload(printer, name, data, memory, timeout=30, cancel=cancel,
                progress=progress)


# --- elapsed time, for a busy bar ------------------------------------------
# From LinuxZPL's zplcore/firmware.py, which both busy bars there use.

def format_elapsed(seconds: float) -> str:
    """m:ss, or h:mm:ss from an hour up."""
    seconds = max(0, int(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def progress_text(fraction: float, elapsed: float) -> str:
    """`42%  0:12 elapsed, ~0:17 left` for an upload `fraction` done after
    `elapsed` seconds."""
    fraction = max(0.0, min(1.0, fraction))
    text = f"{int(fraction * 100)}%  {format_elapsed(elapsed)} elapsed"
    if 0.02 <= fraction < 1.0 and elapsed >= 1:
        text += f", ~{format_elapsed(elapsed * (1 - fraction) / fraction)} left"
    return text


# --- what a session remembers ---------------------------------------------

@dataclass
class Session:
    """Things the printer cannot be asked, known only because this run of
    the app did them: which BMPs went up in grey, so Test Print shows them
    with PUTBMP's bpp 8."""
    grey: set = field(default_factory=set)

    def test_options(self, name: str) -> dict:
        return {'bpp': 8} if name in self.grey else {}

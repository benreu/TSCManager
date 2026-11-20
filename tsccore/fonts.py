"""
TrueType files on this computer: what family one holds, and which ones
there are to choose from.

The same ways LinuxZPL's zplcore/fonts.py uses (family_for_file and
fc-list), without anything of ZPL's.
"""

import os
import shutil
import subprocess
from typing import List, Optional, Tuple

FONT_EXTENSIONS = ('.ttf', '.ttc')


def family_for_file(path: str) -> Optional[str]:
    """The family name inside a TrueType file, or None if it cannot be
    read as one."""
    try:
        from PIL import ImageFont
        family, style = ImageFont.truetype(path, 12).getname()
    except (OSError, ValueError, ImportError):
        return None
    if style and style.lower() not in ('regular', 'book', 'normal', 'roman'):
        return f"{family} {style}"
    return family


def system_fonts(lang: str = '') -> List[Tuple[str, str]]:
    """(family, path) for every TrueType file fontconfig knows, by family -
    or only those that cover `lang` ("en"). Empty where fc-list is
    missing."""
    if not shutil.which('fc-list'):
        return []
    try:
        pattern = [f':lang={lang}'] if lang else []
        out = subprocess.run(['fc-list'] + pattern +
                             ['--format', '%{file}\\t%{family[0]}'
                              '\\t%{style[0]}\\n'],
                             capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    found = {}
    for line in out.splitlines():
        path, _, rest = line.partition('\t')
        family, _, style = rest.partition('\t')
        if not path.lower().endswith(FONT_EXTENSIONS) or not family:
            continue
        name = family if style.lower() in ('regular', 'book', 'normal',
                                           'roman', '') else f"{family} {style}"
        found.setdefault(name, path)
    return sorted(found.items(), key=lambda item: item[0].lower())


# Ordinary text faces with the Latin alphabet, for a test font. fontconfig's
# own language coverage cannot pick one: it says a math-symbol face covers
# English.
TEXT_FAMILIES = ('Liberation Sans', 'DejaVu Sans', 'Noto Sans', 'FreeSans',
                 'Ubuntu', 'Open Sans', 'Arial')


def probe_font() -> Optional[str]:
    """The smallest file among the common text faces installed, quick to
    send for a check; failing those, the smallest TrueType file there is.
    None where there is none."""
    known = system_fonts()
    common = [path for family, path in known if family in TEXT_FAMILIES]
    paths = [p for p in (common or [path for _f, path in known])
             if p.lower().endswith('.ttf') and os.path.isfile(p)]
    return min(paths, key=os.path.getsize) if paths else None


def preview_image(path: str, text: str, pixels: int = 28):
    """`text` drawn in the font file itself, black on white (mode 'L'), by
    PIL rather than either toolkit, so the preview is that file and not
    whatever fontconfig would put in its place. None if it cannot be read
    as a font."""
    try:
        from PIL import Image, ImageDraw, ImageFont
        font = ImageFont.truetype(path, pixels)
        left, top, right, bottom = font.getbbox(text)
    except (OSError, ValueError, ImportError):
        return None
    pad = max(2, pixels // 6)
    image = Image.new('L', (max(1, right - left) + 2 * pad,
                            max(1, bottom - top) + 2 * pad), 255)
    ImageDraw.Draw(image).text((pad - left, pad - top), text, font=font,
                               fill=0)
    return image

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


def system_fonts() -> List[Tuple[str, str]]:
    """(family, path) for every TrueType file fontconfig knows, by family.
    Empty where fc-list is missing."""
    if not shutil.which('fc-list'):
        return []
    try:
        out = subprocess.run(['fc-list', '--format', '%{file}\\t%{family[0]}'
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


def smallest_system_font() -> Optional[str]:
    """The smallest TrueType file fontconfig knows: quick to send for a
    check. None where there is none."""
    paths = [path for _family, path in system_fonts()]
    paths = [p for p in paths if p.lower().endswith('.ttf')
             and os.path.isfile(p)]
    return min(paths, key=os.path.getsize) if paths else None

"""
The settings file both frontends share: $XDG_CONFIG_HOME/tscmanager/
settings.ini (~/.config/tscmanager/settings.ini).

[printer] is the printer last connected to, written by Connection.write.
[folders] remembers where the font and image choosers were last pointed.
Saving reads the file, replaces the one section and writes it back, so a
section this version does not know survives.
"""

import configparser
import os
from pathlib import Path

from .connection import Connection

FOLDERS = 'folders'


def path() -> Path:
    base = os.environ.get('XDG_CONFIG_HOME') or os.path.expanduser('~/.config')
    return Path(base) / 'tscmanager' / 'settings.ini'


def _read() -> configparser.ConfigParser:
    parser = configparser.ConfigParser()
    try:
        parser.read(path())
    except (OSError, configparser.Error):
        pass
    return parser


def _write(parser: configparser.ConfigParser) -> None:
    target = path()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, 'w') as f:
            parser.write(f)
    except OSError:
        pass


def load_printer() -> Connection:
    """The printer last connected to, or an empty network one."""
    try:
        return Connection.read(_read(), Connection())
    except (ValueError, configparser.Error):
        return Connection()


def save_printer(printer: Connection) -> None:
    parser = _read()
    printer.write(parser)
    _write(parser)


def load_folder(key: str, fallback: str = '') -> str:
    folder = _read().get(FOLDERS, key, fallback=fallback)
    return folder if folder and os.path.isdir(folder) else fallback


def save_folder(key: str, folder: str) -> None:
    parser = _read()
    if not parser.has_section(FOLDERS):
        parser.add_section(FOLDERS)
    parser.set(FOLDERS, key, folder)
    _write(parser)

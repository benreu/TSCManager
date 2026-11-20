"""tsccore.manager and tsccore.settings: what both frontends show and decide,
checked without a display."""
import os
import time

from _check import check, finish

from fake_printer import FakePrinter

from tsccore import fonts, manager, settings, tspl
from tsccore.connection import Connection
from tsccore.manager import Loaded, Row

MB241 = tspl.Info(model='MB241', version='1.28.002', serial='MB225230141',
                  dpi=203, memory={tspl.DRAM: (8192, 8192),
                                   tspl.FLASH: (212352, 211710)},
                  card_installed=False)
net = Connection.network('192.168.50.235', 9100)

check("printer_line: model, where, firmware and dpi",
      manager.printer_line(net, MB241)
      == "MB241 at 192.168.50.235 · firmware 1.28.002 · 203 dpi")
check("printer_line: by USB, or not connected",
      manager.printer_line(Connection.usb('S', 'TSC MB241'), MB241)
      .startswith("MB241 by USB")
      and manager.printer_line(None, None) == manager.NOT_CONNECTED)
check("format_kb: KB under a megabyte, MB above",
      (manager.format_kb(850), manager.format_kb(8192),
       manager.format_kb(None)) == ("850 KB", "8.0 MB", "?"))
check("memory_line: DRAM and flash, free of the whole",
      manager.memory_line(MB241)
      == "DRAM 8.0 MB free of 8.0 MB · Flash 206.7 MB free of 207.4 MB",
      manager.memory_line(MB241))
with_card = tspl.Info(memory={tspl.DRAM: (8192, 8000),
                              tspl.CARD: (None, 2048)}, card_installed=True)
check("memory_line: a card when there is one; a capacity left out when "
      "unknown", manager.memory_line(with_card)
      == "DRAM 7.8 MB free of 8.0 MB · Card 2.0 MB free")
check("memory_line from old firmware: the one number ~!A gives",
      manager.memory_line(tspl.Info(free_bytes=2 * 1024 * 1024))
      == "2.0 MB free")

check("rows: name and kind, in the printer's order",
      [(r.name, r.kind_label) for r in manager.rows(['A.TTF', 'b.bmp',
                                                     'RUN.BAS', 'X.DAT'])]
      == [('A.TTF', 'Font'), ('b.bmp', 'Image'), ('RUN.BAS', 'Program'),
          ('X.DAT', 'File')])
check("files_status: a count, empty, silent, or not connected",
      manager.files_status(Loaded(MB241, ['A.TTF', 'B.BMP']))
      == "2 files on the printer."
      and manager.files_status(Loaded(MB241, ['A.TTF']))
      == "1 file on the printer."
      and manager.files_status(Loaded(MB241, [])).startswith("No fonts")
      and manager.files_status(Loaded(None, None)) == manager.NO_ANSWER
      and manager.files_status(None) == manager.NOT_CONNECTED)

nothing = manager.enabled_actions(False, None)
check("not connected: no button but none", not any(nothing.values()))
font_row, program_row = Row('A.TTF', tspl.FONT), Row('R.BAS', tspl.PROGRAM)
on = manager.enabled_actions(True, font_row, MB241)
check("connected, a font chosen: everything but Move, DRAM being empty",
      on == {'upload_font': True, 'upload_image': True, 'delete': True,
             'test_print': True, 'move_to_flash': False, 'refresh': True}, on)
check("a program chosen can be deleted, not test-printed",
      manager.enabled_actions(True, program_row)['delete']
      and not manager.enabled_actions(True, program_row)['test_print'])
in_dram = tspl.Info(memory={tspl.DRAM: (8192, 8175)})
check("Move: with something in DRAM, or when the printer did not say",
      manager.enabled_actions(True, None, in_dram)['move_to_flash']
      and manager.enabled_actions(True, None, tspl.Info())['move_to_flash'])
check("every action has a label and a tip",
      set(manager.ACTION_LABELS) == set(manager.ACTIONS)
      == set(manager.ACTION_TIPS))

check("memory_choices: flash first, then DRAM; a card only when installed",
      [m for m, _ in manager.memory_choices(MB241)] == [tspl.FLASH, tspl.DRAM]
      and [m for m, _ in manager.memory_choices(with_card)][-1] == tspl.CARD)
check("delete_memories: DRAM and flash, and the card when there is one",
      manager.delete_memories(MB241) == (tspl.DRAM, tspl.FLASH)
      and manager.delete_memories(with_card) == (tspl.DRAM, tspl.FLASH,
                                                 tspl.CARD))
check("upload_problem: a bad name, or a file bigger than the space left",
      'quote' in manager.upload_problem('a"b.TTF', 10, tspl.FLASH, MB241)
      and manager.upload_problem('BIG.TTF', 9 * 1024 * 1024, tspl.DRAM, MB241)
      == "9.0 MB does not fit: DRAM has 8.0 MB free."
      and manager.upload_problem('OK.TTF', 1000, tspl.FLASH, MB241) is None)
check("upload_note: size and space, and a warning on replacing",
      manager.upload_note('A.TTF', 217360, tspl.FLASH, MB241, ['A.TTF'])
      == "213 KB; Flash has 206.7 MB free. It replaces the A.TTF already "
         "on the printer.")
check("progress_text: percent, elapsed, then an estimate",
      manager.progress_text(0.5, 10) == "50%  0:10 elapsed, ~0:10 left"
      and manager.progress_text(1.0, 21) == "100%  0:21 elapsed")
session = manager.Session()
session.grey.add('G.BMP')
check("Session: a BMP sent in grey test-prints with bpp 8",
      session.test_options('G.BMP') == {'bpp': 8}
      and session.test_options('L.BMP') == {})

# --- load(), against the fake printer --------------------------------------
fake = FakePrinter()
try:
    fake.files['flash']['A.TTF'] = b'x' * 5000
    loaded = manager.load(Connection.network('127.0.0.1', fake.port))
    check("load: the printer's info and its files",
          loaded.answered and loaded.info.model == 'MB241'
          and loaded.names == ['A.TTF'], loaded)
    fractions = []
    manager.upload(Connection.network('127.0.0.1', fake.port), 'B.BMP',
                   b'y' * 40000, tspl.DRAM, fraction=fractions.append)
    time.sleep(0.3)
    check("upload: stored, reporting fractions up to 1",
          fake.files['dram'].get('B.BMP') == b'y' * 40000
          and fractions[-1] == 1.0 and len(fractions) > 1)
finally:
    fake.close()
mute = FakePrinter(answers=False)
try:
    started = time.monotonic()
    loaded = manager.load(Connection.network('127.0.0.1', mute.port))
    check("load from a silent printer: nothing answered, and it does not ask "
          "for the file list after the info went unanswered",
          not loaded.answered and '~!F' not in mute.received, mute.received)
finally:
    mute.close()

# --- settings ---------------------------------------------------------------
check("settings live under XDG_CONFIG_HOME/tscmanager",
      str(settings.path()).startswith(os.environ['XDG_CONFIG_HOME'])
      and settings.path().name == 'settings.ini')
check("no settings file: an empty network printer",
      settings.load_printer() == Connection())
settings.save_printer(net)
settings.save_folder('fonts', '/usr/share/fonts')
check("the printer and a folder come back as saved, side by side",
      settings.load_printer() == net
      and settings.load_folder('fonts') == '/usr/share/fonts')
check("a folder that has gone falls back",
      settings.save_folder('images', '/no/such/dir') is None
      and settings.load_folder('images', '/tmp') == '/tmp')

# --- the font preview -------------------------------------------------------
font = fonts.probe_font()
if font:
    image = fonts.preview_image(font, "The quick brown fox", 28)
    check("preview_image: the text drawn in the file, black on white",
          image is not None and image.getextrema() == (0, 255)
          and image.size[0] > image.size[1])
else:
    print("SKIPPED: no TrueType font for preview_image")
check("preview_image says None for a file that is no font",
      fonts.preview_image(__file__, "x") is None)

finish()

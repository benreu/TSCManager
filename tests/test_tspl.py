"""tsccore.tspl, tsccore.images and tsccore.fonts: the TSPL commands, the
reply parsers, the files made from pictures, and a whole store / list /
print / delete round against the fake printer."""
import io

from PIL import Image

from _check import check, finish, raises
from fake_printer import FakePrinter

from tsccore import fonts, images, tspl
from tsccore.connection import Connection

# --- building commands --------------------------------------------------
check("DOWNLOAD to DRAM: no memory letter, the name's case kept",
      tspl.build_download('my.ttf', b'xyz') == b'DOWNLOAD "my.ttf",3,xyz')
check("DOWNLOAD to flash and to a card: F, and E,",
      tspl.build_download('A.TTF', b'xy', tspl.FLASH)
      == b'DOWNLOAD F,"A.TTF",2,xy'
      and tspl.build_download('A.TTF', b'', tspl.CARD)
      == b'DOWNLOAD E,"A.TTF",0,')
check("KILL from DRAM and from flash",
      tspl.build_kill('A.BMP') == b'KILL "A.BMP"\r\n'
      and tspl.build_kill('A.BMP', tspl.FLASH) == b'KILL F,"A.BMP"\r\n')
check("a quote, a line break, a non-ASCII letter or no extension is refused",
      all(raises(ValueError, tspl.build_download, bad, b'')
          for bad in ('a"b.ttf', 'a\r.ttf', 'ä.ttf', 'NOEXT', '')))
check("name_problem says why, and None for a good name",
      tspl.name_problem('A.TTF') is None
      and 'quote' in tspl.name_problem('a"b.ttf')
      and 'extension' in tspl.name_problem('FONT'))

check("kind_of sorts by extension, without case",
      [tspl.kind_of(n) for n in ('a.ttf', 'B.BMP', 'c.Png', 'D.PCX', 'E.BAS',
                                 'F.TXT', 'NOEXT')]
      == [tspl.FONT, tspl.IMAGE, tspl.IMAGE, tspl.IMAGE, tspl.PROGRAM,
          tspl.OTHER, tspl.OTHER])
check("suggest_name: eight capitals from the file name, then the extension",
      tspl.suggest_name('/usr/share/fonts/DejaVu Sans-Bold.ttf', '.ttf')
      == 'DEJAVUSA.TTF')
check("suggest_name: a taken name gets a number, compared without case",
      tspl.suggest_name('logo.png', '.BMP', ['logo.bmp']) == 'LOGO1.BMP'
      and tspl.suggest_name('longername.png', '.BMP',
                            ['LONGERNA.BMP', 'LONGERN1.BMP'])
      == 'LONGERN2.BMP')
check("suggest_name: a name with nothing usable in it becomes FILE",
      tspl.suggest_name('äöü.png', '.BMP') == 'FILE.BMP')

# --- parsing replies ------------------------------------------------------
check("~!F: names each ending 0x0D, up to the 0x1A",
      tspl.parse_file_list(b'A.TTF\rLOGO.BMP\r\x1a') == ['A.TTF', 'LOGO.BMP'])
check("~!F: an empty list is just the 0x1A; CR LF and blanks are fine",
      tspl.parse_file_list(b'\x1a') == []
      and tspl.parse_file_list(b'A.TTF\r\n\r\nB.BMP\r\n\x1a') == ['A.TTF',
                                                                'B.BMP'])
check("~!A: the number in the reply", tspl.parse_number(b'1048576\r')
      == 1048576 and tspl.parse_number(b'') is None)
reply = (b'model=TE210\r\nversion=V6.93 EZ\r\ndpi=203\r\n'
         b'dram_capacity=8000000\r\ndram_available=7000000\r\n'
         b'flash_capacity=4000000\r\nflash_available=\r\ncard_installed=0\r\n'
         b'junk line\r\n')
settings = tspl.parse_settings(reply)
check("GETSETTING$ answers come back by tag, and a stray line is ignored",
      settings['model'] == 'TE210' and settings['dpi'] == '203'
      and 'junk line' not in settings and settings['flash_available'] == '')
info = tspl.info_from(b'TE210\r', b'123\r', settings)
check("Info: what was answered, None for what was not",
      (info.model, info.version, info.dpi, info.free, info.card_installed)
      == ('TE210', 'V6.93 EZ', 203, 123, False)
      and info.memory == {tspl.DRAM: (8000000, 7000000),
                          tspl.FLASH: (4000000, None)}, info)
check("Info from old firmware (no OUT): ~!T's model and ~!A's free memory",
      tspl.info_from(b'TTP-244 Plus\r', b'500\r', {})
      == tspl.Info(model='TTP-244 Plus', free=500))
check("the settings request tags each answer",
      b'OUT "dpi=";GETSETTING$("SYSTEM","INFORMATION","DPI")\r\n'
      in tspl.build_settings_request())

# --- test labels ----------------------------------------------------------
label = tspl.build_font_test('My.ttf', 'Say "hi"')
check("font test: CLS, a caption, the text in the font in points, PRINT; "
      "no SIZE or GAP", label.startswith(b'CLS\r\n')
      and b'TEXT 20,60,"My.ttf",0,24,24,"Say \\["]hi\\["]"' in label
      and label.endswith(b'PRINT 1,1\r\n')
      and b'SIZE' not in label and b'GAP' not in label, label)
check("a bitmap font is printed at scale 1, not in points",
      b'"A.FNT",0,1,1,' in tspl.build_font_test('A.FNT'))
check("image test: PUTBMP, PUTBMP in grey, PUTPCX, PUTPNG by extension",
      b'PUTBMP 20,60,"L.BMP"\r\n' in tspl.build_image_test('L.BMP')
      and b'PUTBMP 20,60,"L.BMP",8,80' in tspl.build_image_test('L.BMP', 8)
      and b'PUTPCX 20,60,"L.PCX"' in tspl.build_image_test('L.PCX')
      and b'PUTPNG 20,60,"L.PNG"' in tspl.build_image_test('L.PNG'))
check("a line break in test text cannot end the command",
      tspl.quote_text('a\r\nb') == 'a  b')

# --- pictures to files ----------------------------------------------------
check("dots: millimetres at a dpi, never under one",
      images.dots(25.4, 203) == 203 and images.dots(0, 300) == 1)
check("fit_size keeps the proportions, to a width, a height or a box",
      images.fit_size((400, 200), width=100) == (100, 50)
      and images.fit_size((400, 200), height=100) == (200, 100)
      and images.fit_size((400, 200), 100, 100) == (100, 50)
      and images.fit_size((400, 200)) == (400, 200))
photo = images.gradient(64, 16).convert('RGB')
one = images.prepare(photo, (32, 8), images.BMP_1BIT)
back = Image.open(io.BytesIO(one.data))
check("1-bit BMP: a BMP of mode 1 at the size asked, previewed as it is",
      one.data[:2] == b'BM' and back.mode == '1' and back.size == (32, 8)
      and one.extension == '.BMP' and one.preview.size == (32, 8)
      and set(one.preview.getdata()) <= {0, 255})
grey = images.prepare(photo, (32, 8), images.BMP_8BIT)
check("8-bit BMP keeps the greys",
      Image.open(io.BytesIO(grey.data)).mode in ('L', 'P')
      and len(set(grey.preview.getdata())) > 2)
png = images.prepare(photo, (32, 8), images.PNG)
check("PNG: black and white, in a PNG", png.data[:4] == b'\x89PNG'
      and png.extension == '.PNG' and set(png.preview.getdata()) <= {0, 255})
crisp = images.prepare(images.gradient(64, 4), (64, 4), images.BMP_1BIT,
                       dither=False, threshold=128)
row = list(crisp.preview.getdata())[:64]
check("threshold: dark half black, light half white, nothing scattered",
      row == sorted(row) and row[0] == 0 and row[-1] == 255)
clear = Image.new('RGBA', (4, 4), (0, 0, 0, 0))
check("see-through parts print as paper, not black",
      set(images.flatten(clear).getdata()) == {255})

# --- local fonts ------------------------------------------------------------
font = fonts.smallest_system_font()
if font:
    check("family_for_file reads a TrueType file's family",
          bool(fonts.family_for_file(font)))
else:
    print("SKIPPED: no TrueType font installed for family_for_file")
check("family_for_file says None for a file that is no font",
      fonts.family_for_file(__file__) is None)

# --- against the fake printer --------------------------------------------
fake = FakePrinter()
printer = Connection.network('127.0.0.1', fake.port)
try:
    progress = []
    tspl.upload(printer, 'Big.TTF', b'\0' * 50000, tspl.FLASH,
                progress=lambda a, b: progress.append((a, b)))
    tspl.upload(printer, 'LOGO.BMP', one.data)
    import time
    time.sleep(0.3)
    check("upload: each file lands in its memory under its own name",
          fake.files['flash'].get('Big.TTF') == b'\0' * 50000
          and fake.files['dram'].get('LOGO.BMP') == one.data, fake.received)
    check("upload: progress rises to the whole DOWNLOAD",
          len(progress) > 1 and progress[-1][0] == progress[-1][1])
    check("list_files: both files, from ~!F", sorted(tspl.list_files(printer))
          == ['Big.TTF', 'LOGO.BMP'])
    got = tspl.query_info(printer)
    check("query_info: model, firmware, dpi and memory from one printer",
          got.model == 'TE210' and got.version == 'V6.93 EZ' and got.dpi == 203
          and got.memory[tspl.FLASH] == (4000000, 4000000 - 50000)
          and got.card_installed is False, got)
    tspl.test_print(printer, 'Big.TTF')
    tspl.test_print(printer, 'LOGO.BMP', bpp=8)
    time.sleep(0.3)
    check("test_print: one label each, in the font and with the image",
          len(fake.labels) == 2
          and any('"Big.TTF",0,24,24' in line for line in fake.labels[0])
          and 'PUTBMP 20,60,"LOGO.BMP",8,80' in fake.labels[1], fake.labels)
    check("test_print refuses a file that is neither font nor image",
          raises(ValueError, tspl.test_print, printer, 'RUN.BAS'))
    tspl.move_to_flash(printer)
    time.sleep(0.3)
    check("MOVE: what was in DRAM is in flash",
          'LOGO.BMP' in fake.files['flash'] and not fake.files['dram'])
    tspl.delete(printer, 'LOGO.BMP', (tspl.DRAM, tspl.FLASH))
    time.sleep(0.3)
    check("delete: KILL from each memory given", tspl.list_files(printer)
          == ['Big.TTF'])
finally:
    fake.close()

mute = FakePrinter(answers=False)
try:
    quiet = Connection.network('127.0.0.1', mute.port)
    check("a printer that says nothing: list_files and query_info say None",
          tspl.list_files(quiet, timeout=0.5) is None
          and tspl.query_info(quiet, timeout=0.5) is None)
finally:
    mute.close()
check("an address nobody listens on: None, not an exception",
      tspl.list_files(Connection.network('127.0.0.1', 9), timeout=1) is None)

finish()

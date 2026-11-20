"""The GTK window and its two upload dialogs, against the fake printer: the
same checks as test_qt.py. Needs a display; tests/run.sh gives it xvfb."""
import os
import tempfile
import time

from _check import check, finish

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
from PIL import Image

from fake_printer import FakePrinter
from tsccore import fonts, images, manager, settings, tspl
from tsccore.connection import Connection
import gtkui.window as gtk_window
from gtkui.upload_font import UploadFontDialog
from gtkui.upload_image import UploadImageDialog, MM
from gtkui.util import is_error


def pump():
    while Gtk.events_pending():
        Gtk.main_iteration_do(False)


def wait_until(cond, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        pump()
        if cond():
            return True
        time.sleep(0.02)
    pump()
    return cond()


def idle(window):
    return wait_until(lambda: not window.busy.running)


def count(window):
    return len(window.store)


scratch = tempfile.mkdtemp()
FONT = fonts.probe_font()
PICTURE = os.path.join(scratch, 'Logo Big.png')
Image.new('RGB', (400, 200), 'white').save(PICTURE)
NOT_A_FONT = os.path.join(scratch, 'notes.ttf')
with open(NOT_A_FONT, 'w') as f:
    f.write("not a font")

fake = FakePrinter()
fake.files['flash']['OLD.TTF'] = b'f' * 9000
printer = Connection.network('127.0.0.1', fake.port)
window = gtk_window.MainWindow(printer)
window.show_all()

check("a saved printer is connected to on opening",
      wait_until(lambda: window.printer == printer) and idle(window))
check("the printer line and memory line say what it answered",
      window.printer_line.get_text().startswith("MB241 at 127.0.0.1")
      and window.memory_line.get_text().startswith(
          "DRAM 8.0 MB free of 8.0 MB"),
      (window.printer_line.get_text(), window.memory_line.get_text()))
check("its files are listed, with their kind",
      count(window) == 1 and tuple(window.store[0]) == ('OLD.TTF', 'Font')
      and window.files_status.get_text() == "1 file on the printer.")
check("connecting saved the printer", settings.load_printer() == printer)
check("only the network rows show, after the window's show_all",
      wait_until(window.rows.address_entry.get_mapped)
      and not window.rows.usb_combo.get_mapped())
window.rows.usb_radio.set_active(True)
check("choosing USB shows the USB row in their place",
      wait_until(window.rows.usb_combo.get_mapped)
      and not window.rows.address_entry.get_mapped())
window.rows.network_radio.set_active(True)
pump()
check("with nothing chosen: no Delete or Test Print; nothing in DRAM: no "
      "Move", window.buttons['upload_font'].get_sensitive()
      and not window.buttons['delete'].get_sensitive()
      and not window.buttons['test_print'].get_sensitive()
      and not window.buttons['move_to_flash'].get_sensitive())
window.select('OLD.TTF')
check("a font chosen: Delete and Test Print",
      window.buttons['delete'].get_sensitive()
      and window.buttons['test_print'].get_sensitive())

# --- Upload Font --------------------------------------------------------
font_dialog = UploadFontDialog(window, window.loaded.info, ['OLD.TTF'])
check("Upload Font opens with nothing to upload",
      not font_dialog.upload_btn.get_sensitive()
      and font_dialog.memory_combo.get_active_id() == tspl.FLASH)
font_dialog.set_file(NOT_A_FONT)
check("a file that is no font cannot be uploaded",
      font_dialog.family_label.get_text() == "Not a TrueType font"
      and not font_dialog.upload_btn.get_sensitive())
font_dialog.set_file(FONT)
check("a font: its family, a preview, and a suggested name",
      font_dialog.family_label.get_text() == fonts.family_for_file(FONT)
      and font_dialog.preview.get_pixbuf() is not None
      and font_dialog.name_entry.get_text() == tspl.suggest_name(
          FONT, '.ttf', ['OLD.TTF'])
      and font_dialog.upload_btn.get_sensitive())
font_dialog.name_entry.set_text('bad"name.TTF')
check("a name with a quote is refused, in red",
      not font_dialog.upload_btn.get_sensitive()
      and 'quote' in font_dialog.note.get_text() and is_error(font_dialog.note))
font_dialog.name_entry.set_text('OLD.TTF')
check("an existing name may be used, and the note says it replaces it",
      font_dialog.upload_btn.get_sensitive()
      and "replaces the OLD.TTF" in font_dialog.note.get_text())
font_dialog.set_file(FONT)
check("a name typed by hand is kept when the file changes",
      font_dialog.name_entry.get_text() == 'OLD.TTF')
font_dialog.destroy()


class FontDialogStandIn(UploadFontDialog):
    def run(self):
        self.set_file(FONT)
        self.name_entry.set_text('Open.ttf')
        self.memory_combo.set_active_id(tspl.DRAM)
        return Gtk.ResponseType.OK


gtk_window.UploadFontDialog = FontDialogStandIn
window.buttons['upload_font'].clicked()
check("Upload Font stores the font in the memory chosen, as named",
      idle(window) and fake.files['dram'].get('Open.ttf')
      == open(FONT, 'rb').read())
check("then the list is read again and the message says so",
      wait_until(lambda: count(window) == 2) and idle(window)
      and window.message.get_text() == "Stored Open.ttf in DRAM.",
      window.message.get_text())
check("something in DRAM now: Move can be pressed",
      window.buttons['move_to_flash'].get_sensitive())

# --- Upload Image -------------------------------------------------------
image_dialog = UploadImageDialog(window, window.loaded.info, [])
image_dialog.set_file(PICTURE)
check("Upload Image: the picture's size, and a BMP name from its file name",
      image_dialog.original_label.get_text() == "400 × 200 pixels"
      and image_dialog.width_spin.get_value() == 400
      and image_dialog.height_spin.get_value() == 200
      and image_dialog.name_entry.get_text() == 'LOGOBIG.BMP'
      and image_dialog.upload_btn.get_sensitive())
image_dialog.width_spin.set_value(100)
check("a new width keeps the proportions",
      image_dialog.height_spin.get_value() == 50
      and image_dialog._prepared.preview.size == (100, 50))
image_dialog.unit_combo.set_active_id(MM)
check("in mm: the same size, at the printer's dpi",
      abs(image_dialog.width_spin.get_value() - 12.5) < 0.1
      and image_dialog.size_note.get_text().startswith("100 × 50 dots"),
      image_dialog.width_spin.get_value())
image_dialog.width_spin.set_value(25.4)
check("25.4 mm at 203 dpi is 203 dots wide, the height in proportion",
      image_dialog._size[0] == 203 and image_dialog._size[1] in (101, 102),
      image_dialog._size)
image_dialog.format_combo.set_active_id(images.PNG)
check("PNG: the name follows, and black and white still applies",
      image_dialog.name_entry.get_text() == 'LOGOBIG.PNG'
      and image_dialog._prepared.data[:4] == b'\x89PNG'
      and image_dialog.dither_radio.get_sensitive())
image_dialog.format_combo.set_active_id(images.BMP_8BIT)
check("grey BMP: no black and white choice, and the needs are shown",
      not image_dialog.dither_radio.get_sensitive()
      and "V6.91" in image_dialog.needs_label.get_text())
image_dialog.name_entry.set_text('LOGO.PNG')
check("a name whose extension does not match the format is refused",
      not image_dialog.upload_btn.get_sensitive()
      and ".BMP" in image_dialog.note.get_text())
image_dialog.set_file(NOT_A_FONT)
check("a file that is no picture cannot be uploaded",
      not image_dialog.upload_btn.get_sensitive()
      and "Cannot read" in image_dialog.note.get_text())
image_dialog.destroy()


class ImageDialogStandIn(UploadImageDialog):
    def run(self):
        self.set_file(PICTURE)
        self.format_combo.set_active_id(images.BMP_8BIT)
        return Gtk.ResponseType.OK


gtk_window.UploadImageDialog = ImageDialogStandIn
window.buttons['upload_image'].clicked()
check("Upload Image stores the BMP, in flash by default",
      idle(window) and fake.files['flash'].get('LOGOBIG.BMP', b'')[:2]
      == b'BM')
wait_until(lambda: count(window) == 3)
idle(window)

# --- Test Print, Delete, Move ---------------------------------------------
window.select('LOGOBIG.BMP')
window.buttons['test_print'].clicked()
check("Test Print of a BMP sent in grey prints it with bpp 8",
      idle(window) and wait_until(lambda: len(fake.labels) == 1)
      and any('PUTBMP 20,60,"LOGOBIG.BMP",8,80' in line
              for line in fake.labels[0]), fake.labels)
window.select('Open.ttf')
window.buttons['test_print'].clicked()
check("Test Print of a font prints the sample in it",
      idle(window) and wait_until(lambda: len(fake.labels) == 2)
      and any('"Open.ttf",0,24,24' in line for line in fake.labels[1]))

window.buttons['move_to_flash'].clicked()
check("Move DRAM to Flash: DRAM's files are in flash",
      idle(window) and wait_until(lambda: 'Open.ttf' in fake.files['flash'])
      and not fake.files['dram'])
idle(window)
check("and with DRAM empty again, Move cannot be pressed",
      wait_until(lambda: not window.buttons['move_to_flash'].get_sensitive()))

window.select('OLD.TTF')
window.buttons['delete'].clicked()
check("Delete kills the file from DRAM and flash, and the list follows",
      idle(window) and wait_until(lambda: 'OLD.TTF' not in fake.all_names())
      and 'KILL "OLD.TTF"' in fake.received
      and 'KILL F,"OLD.TTF"' in fake.received
      and wait_until(lambda: count(window) == 2)
      and idle(window) and window.message.get_text() == "Deleted OLD.TTF.",
      window.message.get_text())
fake.close()

# --- when something is wrong -------------------------------------------
window.rows.address_entry.set_text('')
window.connect_btn.clicked()
check("Connect with no address says so, in red, and asks nothing",
      window.message.get_text() == "Printer address cannot be empty."
      and is_error(window.message) and not window.busy.running)

mute = FakePrinter(answers=False)
quiet_window = gtk_window.MainWindow(
    Connection.network('127.0.0.1', mute.port), autoconnect=False)
quiet_window.show_all()
quiet_window.connect_btn.clicked()
check("a printer that says nothing: the message says what to check",
      wait_until(lambda: not quiet_window.busy.running, 15)
      and quiet_window.message.get_text() == manager.NO_ANSWER
      and quiet_window.printer is None
      and not quiet_window.buttons['upload_font'].get_sensitive())
mute.close()

nobody = gtk_window.MainWindow(Connection.network('127.0.0.1', 9),
                               autoconnect=False)
nobody.connect_btn.clicked()
check("an address nobody answers on: told so",
      wait_until(lambda: not nobody.busy.running, 10)
      and nobody.message.get_text() == manager.NO_ANSWER,
      nobody.message.get_text())

for w in (window, quiet_window, nobody):
    w.destroy()
finish()

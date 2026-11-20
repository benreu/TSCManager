"""The Qt window and its two upload dialogs, offscreen, against the fake
printer: connect, list, upload a font and an image, test-print, delete,
move, and the messages when something is wrong."""
import os
import tempfile
import time

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from _check import check, finish

from PIL import Image
from PySide2.QtWidgets import QApplication, QDialog

app = QApplication([])

from fake_printer import FakePrinter
from tsccore import fonts, images, manager, settings, tspl
from tsccore.connection import Connection
import qtui.window as qt_window
from qtui.upload_font import UploadFontDialog
from qtui.upload_image import UploadImageDialog, MM


def wait_until(cond, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.02)
    app.processEvents()
    return cond()


def idle(window):
    return wait_until(lambda: not window.busy.running)


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
window = qt_window.MainWindow(printer)
window.show()

check("a saved printer is connected to on opening",
      wait_until(lambda: window.printer == printer) and idle(window))
check("the printer line and memory line say what it answered",
      window.printer_line.text().startswith("MB241 at 127.0.0.1")
      and window.memory_line.text().startswith("DRAM 8.0 MB free of 8.0 MB"),
      (window.printer_line.text(), window.memory_line.text()))
check("its files are listed, with their kind",
      window.files.topLevelItemCount() == 1
      and window.files.topLevelItem(0).text(0) == 'OLD.TTF'
      and window.files.topLevelItem(0).text(1) == 'Font'
      and window.files_status.text() == "1 file on the printer.")
check("connecting saved the printer", settings.load_printer() == printer)
check("with nothing chosen: no Delete or Test Print; nothing in DRAM: no "
      "Move", window.buttons['upload_font'].isEnabled()
      and not window.buttons['delete'].isEnabled()
      and not window.buttons['test_print'].isEnabled()
      and not window.buttons['move_to_flash'].isEnabled())
window.files.setCurrentItem(window.files.topLevelItem(0))
check("a font chosen: Delete and Test Print",
      window.buttons['delete'].isEnabled()
      and window.buttons['test_print'].isEnabled())

# --- Upload Font --------------------------------------------------------
font_dialog = UploadFontDialog(window, window.loaded.info, ['OLD.TTF'])
check("Upload Font opens with nothing to upload",
      not font_dialog.upload_btn.isEnabled()
      and font_dialog.memory_combo.currentData() == tspl.FLASH)
font_dialog.set_file(NOT_A_FONT)
check("a file that is no font cannot be uploaded",
      font_dialog.family_label.text() == "Not a TrueType font"
      and not font_dialog.upload_btn.isEnabled())
font_dialog.set_file(FONT)
check("a font: its family, a preview, and a suggested name",
      font_dialog.family_label.text() == fonts.family_for_file(FONT)
      and font_dialog.preview.pixmap() is not None
      and font_dialog.name_edit.text() == tspl.suggest_name(
          FONT, '.ttf', ['OLD.TTF'])
      and font_dialog.upload_btn.isEnabled(), font_dialog.name_edit.text())
font_dialog.name_edit.setText('bad"name.TTF')
font_dialog.name_edit.textEdited.emit('bad"name.TTF')
check("a name with a quote is refused, in red",
      not font_dialog.upload_btn.isEnabled()
      and 'quote' in font_dialog.note.text()
      and font_dialog.note.styleSheet() != "")
font_dialog.name_edit.setText('OLD.TTF')
font_dialog.name_edit.textEdited.emit('OLD.TTF')
check("an existing name may be used, and the note says it replaces it",
      font_dialog.upload_btn.isEnabled()
      and "replaces the OLD.TTF" in font_dialog.note.text())
font_dialog.set_file(FONT)
check("a name typed by hand is kept when the file changes",
      font_dialog.name_edit.text() == 'OLD.TTF')
font_dialog.deleteLater()


class FontDialogStandIn(UploadFontDialog):
    def exec_(self):
        self.set_file(FONT)
        self.name_edit.setText('Open.ttf')
        self.memory_combo.setCurrentIndex(
            self.memory_combo.findData(tspl.DRAM))
        return QDialog.Accepted


qt_window.UploadFontDialog = FontDialogStandIn
window.buttons['upload_font'].click()
check("Upload Font stores the font in the memory chosen, as named",
      idle(window) and fake.files['dram'].get('Open.ttf')
      == open(FONT, 'rb').read())
check("then the list is read again and the message says so",
      wait_until(lambda: window.files.topLevelItemCount() == 2)
      and idle(window)
      and window.message.text() == "Stored Open.ttf in DRAM.",
      window.message.text())
check("something in DRAM now: Move can be pressed",
      window.buttons['move_to_flash'].isEnabled())

# --- Upload Image -------------------------------------------------------
image_dialog = UploadImageDialog(window, window.loaded.info, [])
image_dialog.set_file(PICTURE)
check("Upload Image: the picture's size, and a BMP name from its file name",
      image_dialog.original_label.text() == "400 × 200 pixels"
      and image_dialog.width_spin.value() == 400
      and image_dialog.height_spin.value() == 200
      and image_dialog.name_edit.text() == 'LOGOBIG.BMP'
      and image_dialog.upload_btn.isEnabled())
image_dialog.width_spin.setValue(100)
check("a new width keeps the proportions",
      image_dialog.height_spin.value() == 50
      and image_dialog._prepared.preview.size == (100, 50))
image_dialog.unit_combo.setCurrentIndex(image_dialog.unit_combo.findData(MM))
check("in mm: the same size, at the printer's dpi",
      abs(image_dialog.width_spin.value() - 12.5) < 0.1
      and image_dialog.size_note.text().startswith("100 × 50 dots"),
      image_dialog.width_spin.value())
image_dialog.width_spin.setValue(25.4)
check("25.4 mm at 203 dpi is 203 dots wide, the height in proportion",
      image_dialog._size[0] == 203 and image_dialog._size[1] in (101, 102),
      image_dialog._size)
image_dialog.format_combo.setCurrentIndex(
    image_dialog.format_combo.findData(images.PNG))
check("PNG: the name follows, and black and white still applies",
      image_dialog.name_edit.text() == 'LOGOBIG.PNG'
      and image_dialog._prepared.data[:4] == b'\x89PNG'
      and image_dialog.dither_radio.isEnabled())
image_dialog.format_combo.setCurrentIndex(
    image_dialog.format_combo.findData(images.BMP_8BIT))
check("grey BMP: no black and white choice, and the needs are shown",
      not image_dialog.dither_radio.isEnabled()
      and "V6.91" in image_dialog.needs_label.text())
image_dialog.name_edit.setText('LOGO.PNG')
image_dialog.name_edit.textEdited.emit('LOGO.PNG')
check("a name whose extension does not match the format is refused",
      not image_dialog.upload_btn.isEnabled()
      and ".BMP" in image_dialog.note.text())
image_dialog.set_file(NOT_A_FONT)
check("a file that is no picture cannot be uploaded",
      not image_dialog.upload_btn.isEnabled()
      and "Cannot read" in image_dialog.note.text())
image_dialog.deleteLater()


class ImageDialogStandIn(UploadImageDialog):
    def exec_(self):
        self.set_file(PICTURE)
        self.format_combo.setCurrentIndex(
            self.format_combo.findData(images.BMP_8BIT))
        return QDialog.Accepted


qt_window.UploadImageDialog = ImageDialogStandIn
window.buttons['upload_image'].click()
check("Upload Image stores the BMP, in flash by default",
      idle(window) and fake.files['flash'].get('LOGOBIG.BMP', b'')[:2]
      == b'BM')
wait_until(lambda: window.files.topLevelItemCount() == 3)
idle(window)

# --- Test Print, Delete, Move ---------------------------------------------
def choose(name):
    for i in range(window.files.topLevelItemCount()):
        if window.files.topLevelItem(i).text(0) == name:
            window.files.setCurrentItem(window.files.topLevelItem(i))
            return True
    return False


choose('LOGOBIG.BMP')
window.buttons['test_print'].click()
check("Test Print of a BMP sent in grey prints it with bpp 8",
      idle(window) and wait_until(lambda: len(fake.labels) == 1)
      and any('PUTBMP 20,60,"LOGOBIG.BMP",8,80' in line
              for line in fake.labels[0]), fake.labels)
choose('Open.ttf')
window.buttons['test_print'].click()
check("Test Print of a font prints the sample in it",
      idle(window) and wait_until(lambda: len(fake.labels) == 2)
      and any('"Open.ttf",0,24,24' in line for line in fake.labels[1]))

window.buttons['move_to_flash'].click()
check("Move DRAM to Flash: DRAM's files are in flash",
      idle(window) and wait_until(lambda: 'Open.ttf' in fake.files['flash'])
      and not fake.files['dram'])
idle(window)
check("and with DRAM empty again, Move cannot be pressed",
      wait_until(lambda: not window.buttons['move_to_flash'].isEnabled()))

choose('OLD.TTF')
window.buttons['delete'].click()
check("Delete kills the file from DRAM and flash, and the list follows",
      idle(window) and wait_until(lambda: 'OLD.TTF' not in fake.all_names())
      and 'KILL "OLD.TTF"' in fake.received
      and 'KILL F,"OLD.TTF"' in fake.received
      and wait_until(lambda: window.files.topLevelItemCount() == 2)
      and idle(window) and window.message.text() == "Deleted OLD.TTF.",
      window.message.text())
fake.close()

# --- when something is wrong -------------------------------------------
window.rows.address_edit.setText('')
window.connect_btn.click()
check("Connect with no address says so, in red, and asks nothing",
      window.message.text() == "Printer address cannot be empty."
      and window.message.styleSheet() != "" and not window.busy.running)

mute = FakePrinter(answers=False)
quiet_window = qt_window.MainWindow(
    Connection.network('127.0.0.1', mute.port), autoconnect=False)
quiet_window.show()
quiet_window.connect_btn.click()
check("a printer that says nothing: the message says what to check",
      wait_until(lambda: not quiet_window.busy.running, 15)
      and quiet_window.message.text() == manager.NO_ANSWER
      and quiet_window.printer is None
      and not quiet_window.buttons['upload_font'].isEnabled())
mute.close()

nobody = qt_window.MainWindow(Connection.network('127.0.0.1', 9),
                              autoconnect=False)
nobody.connect_btn.click()
check("an address nobody answers on: told so",
      wait_until(lambda: not nobody.busy.running, 10)
      and nobody.message.text() == manager.NO_ANSWER, nobody.message.text())

for w in (window, quiet_window, nobody):
    w.close()
finish()

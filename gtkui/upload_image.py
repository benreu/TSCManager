"""Upload Image: pick a picture, size it in dots or mm, choose how it becomes
a printer file, see exactly what will be sent, name it, choose a memory.
The GTK twin of qtui/upload_image.py."""

import os
from typing import Optional, Sequence, Tuple

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
from PIL import Image

from tsccore import images, manager, settings, tspl
from tsccore.tspl import FLASH

from .util import add_row, note_label, pixbuf, say

DOTS, MM = 'dots', 'mm'
PREVIEW_SIZE = (360, 220)
DEFAULT_INCHES = 4
PATTERNS = ("*.png", "*.jpg", "*.jpeg", "*.bmp", "*.gif", "*.tif", "*.tiff",
            "*.webp", "*.PNG", "*.JPG", "*.JPEG", "*.BMP", "*.GIF", "*.TIF",
            "*.TIFF")


class UploadImageDialog(Gtk.Dialog):
    def __init__(self, parent, info: Optional[tspl.Info],
                 names: Sequence[str] = ()):
        super().__init__(title="Upload Image", transient_for=parent,
                         modal=True)
        self.set_name("upload_image_dialog")
        self._info = info
        self._names = list(names)
        self._dpi = (info.dpi if info and info.dpi else 203)
        self._source = ''
        self._grey: Optional[Image.Image] = None
        self._size = (0, 0)              # in dots
        self._prepared: Optional[images.Prepared] = None
        self._name_edited = False
        self._filling = False
        self._updating = False

        self.add_button("_Cancel", Gtk.ResponseType.CANCEL)
        self.upload_btn = self.add_button("_Upload", Gtk.ResponseType.OK)
        self.upload_btn.set_name("upload")
        self.set_default_response(Gtk.ResponseType.OK)

        area = self.get_content_area()
        area.set_border_width(12)
        area.set_spacing(8)
        grid = Gtk.Grid(column_spacing=12, row_spacing=6)
        area.pack_start(grid, True, True, 0)

        file_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.file_entry = Gtk.Entry()
        self.file_entry.set_name("file")
        self.file_entry.set_editable(False)
        self.file_entry.set_placeholder_text("No picture chosen")
        file_box.pack_start(self.file_entry, True, True, 0)
        self.choose_btn = Gtk.Button.new_with_mnemonic("_Choose…")
        self.choose_btn.set_name("choose_file")
        file_box.pack_start(self.choose_btn, False, False, 0)
        add_row(grid, "Picture:", file_box, self.choose_btn)

        self.original_label = note_label("original")
        add_row(grid, "Original:", self.original_label)

        size_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.width_spin = Gtk.SpinButton.new_with_range(1, 10000, 1)
        self.width_spin.set_name("width")
        self.height_spin = Gtk.SpinButton.new_with_range(1, 10000, 1)
        self.height_spin.set_name("height")
        self.unit_combo = Gtk.ComboBoxText()
        self.unit_combo.set_name("unit")
        self.unit_combo.append(DOTS, "dots")
        self.unit_combo.append(MM, "mm")
        self.unit_combo.set_active(0)
        size_box.pack_start(self.width_spin, False, False, 0)
        size_box.pack_start(Gtk.Label(label="×"), False, False, 0)
        size_box.pack_start(self.height_spin, False, False, 0)
        size_box.pack_start(self.unit_combo, False, False, 0)
        add_row(grid, "_Size:", size_box, self.width_spin)
        self.size_note = note_label("size_note")
        add_row(grid, "", self.size_note)

        self.format_combo = Gtk.ComboBoxText()
        self.format_combo.set_name("format")
        for fmt, label, _extension, _needs in images.FORMATS:
            self.format_combo.append(fmt, label)
        self.format_combo.set_active(0)
        add_row(grid, "_Format:", self.format_combo)
        self.needs_label = note_label("format_needs")
        add_row(grid, "", self.needs_label)

        bw_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.dither_radio = Gtk.RadioButton.new_with_mnemonic_from_widget(
            None, "_Dither")
        self.dither_radio.set_name("dither")
        self.dither_radio.set_tooltip_text("Keep a photo's shading as a "
                                           "pattern of dots.")
        self.threshold_radio = Gtk.RadioButton.new_with_mnemonic_from_widget(
            self.dither_radio, "_Threshold")
        self.threshold_radio.set_name("threshold")
        self.threshold_radio.set_tooltip_text("Every pixel darker than the "
                                              "level prints black: crisp "
                                              "logos and text.")
        self.threshold_spin = Gtk.SpinButton.new_with_range(1, 254, 1)
        self.threshold_spin.set_name("threshold_level")
        self.threshold_spin.set_value(128)
        bw_box.pack_start(self.dither_radio, False, False, 0)
        bw_box.pack_start(self.threshold_radio, False, False, 0)
        bw_box.pack_start(self.threshold_spin, False, False, 0)
        add_row(grid, "Black and white:", bw_box, self.dither_radio)

        frame = Gtk.Frame()
        self.preview = Gtk.Image()
        self.preview.set_name("preview")
        self.preview.set_size_request(*PREVIEW_SIZE)
        frame.add(self.preview)
        add_row(grid, "Preview:", frame)

        self.name_entry = Gtk.Entry()
        self.name_entry.set_name("printer_name")
        self.name_entry.set_activates_default(True)
        self.name_entry.set_tooltip_text("The name the picture is stored "
                                         "under. PUTBMP and PUTPNG use it, "
                                         "so it is case sensitive.")
        add_row(grid, "_Name on printer:", self.name_entry)

        self.memory_combo = Gtk.ComboBoxText()
        self.memory_combo.set_name("memory")
        for memory, label in manager.memory_choices(info):
            self.memory_combo.append(memory, label)
        self.memory_combo.set_active(0)
        add_row(grid, "_Memory:", self.memory_combo)

        self.note = note_label("note")
        area.pack_start(self.note, False, False, 0)

        self.choose_btn.connect("clicked", self._on_choose)
        self.width_spin.connect("value-changed", self._on_width)
        self.height_spin.connect("value-changed", self._on_height)
        self.unit_combo.connect("changed", self._show_size)
        self.format_combo.connect("changed", self._on_format)
        self.dither_radio.connect("toggled", self._remake)
        self.threshold_spin.connect("value-changed", self._remake)
        self.name_entry.connect("changed", self._on_name_changed)
        self.memory_combo.connect("changed", self._update_note)
        self._enable_size(False)
        self._on_format()
        area.show_all()

    # --- choosing ---------------------------------------------------------

    def _on_choose(self, _button) -> None:
        chooser = Gtk.FileChooserDialog(
            title="Choose a Picture", transient_for=self,
            action=Gtk.FileChooserAction.OPEN)
        chooser.add_buttons("_Cancel", Gtk.ResponseType.CANCEL,
                            "_Open", Gtk.ResponseType.ACCEPT)
        pictures = Gtk.FileFilter()
        pictures.set_name("Pictures")
        for pattern in PATTERNS:
            pictures.add_pattern(pattern)
        chooser.add_filter(pictures)
        everything = Gtk.FileFilter()
        everything.set_name("All files")
        everything.add_pattern("*")
        chooser.add_filter(everything)
        chooser.set_current_folder(settings.load_folder(
            'images', os.path.expanduser('~')))
        path = (chooser.get_filename()
                if chooser.run() == Gtk.ResponseType.ACCEPT else None)
        chooser.destroy()
        if path:
            settings.save_folder('images', os.path.dirname(path))
            self.set_file(path)

    def set_file(self, path: str) -> None:
        """Show `path` as the picture to upload."""
        try:
            with Image.open(path) as picture:
                picture.load()
                self._grey = images.flatten(picture)
        except (OSError, ValueError, Image.DecompressionBombError) as e:
            self._grey = None
            self.file_entry.set_text(path)
            self.original_label.set_text("Not a picture this app can read")
            self._enable_size(False)
            self._prepared = None
            self.preview.clear()
            say(self.note, f"Cannot read {os.path.basename(path)}: {e}", True)
            self.upload_btn.set_sensitive(False)
            return
        self._source = path
        self.file_entry.set_text(path)
        w, h = self._grey.size
        self.original_label.set_text(f"{w} × {h} pixels")
        widest = self._dpi * DEFAULT_INCHES
        self._size = images.fit_size((w, h), width=min(w, widest))
        self._enable_size(True)
        self._show_size()
        self._remake()

    def _enable_size(self, on: bool) -> None:
        for widget in (self.width_spin, self.height_spin, self.unit_combo):
            widget.set_sensitive(on)

    # --- size -----------------------------------------------------------

    def unit(self) -> str:
        return self.unit_combo.get_active_id() or DOTS

    def _show_size(self, _widget=None) -> None:
        """Put the size in dots into the spins, in the unit chosen."""
        self._updating = True
        try:
            mm = self.unit() == MM
            for spin, count in ((self.width_spin, self._size[0]),
                                (self.height_spin, self._size[1])):
                spin.set_digits(1 if mm else 0)
                spin.set_increments(1 if mm else 8, 10 if mm else 80)
                spin.set_value(images.millimetres(count, self._dpi) if mm
                               else count)
        finally:
            self._updating = False
        w, h = self._size
        self.size_note.set_text(
            f"{w} × {h} dots: {images.millimetres(w, self._dpi):.1f} × "
            f"{images.millimetres(h, self._dpi):.1f} mm at {self._dpi} dpi")

    def _to_dots(self, value: float) -> int:
        return (images.dots(value, self._dpi) if self.unit() == MM
                else max(1, round(value)))

    def _on_width(self, spin) -> None:
        if self._updating or self._grey is None:
            return
        self._size = images.fit_size(self._grey.size,
                                     width=self._to_dots(spin.get_value()))
        self._show_size()
        self._remake()

    def _on_height(self, spin) -> None:
        if self._updating or self._grey is None:
            return
        self._size = images.fit_size(self._grey.size,
                                     height=self._to_dots(spin.get_value()))
        self._show_size()
        self._remake()

    # --- format and preview ----------------------------------------------

    def fmt(self) -> str:
        return self.format_combo.get_active_id() or images.BMP_1BIT

    def _on_format(self, _widget=None) -> None:
        for fmt, _label, _extension, needs in images.FORMATS:
            if fmt == self.fmt():
                self.needs_label.set_text(f"Prints on {needs}.")
        black_and_white = self.fmt() != images.BMP_8BIT
        for widget in (self.dither_radio, self.threshold_radio,
                       self.threshold_spin):
            widget.set_sensitive(black_and_white)
        self._remake()

    def _remake(self, _widget=None) -> None:
        """Make the file again from the current choices, and show it."""
        if self._grey is None:
            self.upload_btn.set_sensitive(False)
            say(self.note, "Choose a picture.")
            return
        self.threshold_spin.set_sensitive(
            self.fmt() != images.BMP_8BIT and self.threshold_radio.get_active())
        self._prepared = images.prepare(
            self._grey, self._size, self.fmt(),
            dither=self.dither_radio.get_active(),
            threshold=int(self.threshold_spin.get_value()))
        self.preview.set_from_pixbuf(pixbuf(self._prepared.preview,
                                            *PREVIEW_SIZE))
        if not self._name_edited:
            self._filling = True
            self.name_entry.set_text(tspl.suggest_name(
                self._source, self._prepared.extension, self._names))
            self._filling = False
        self._update_note()

    def _on_name_changed(self, _entry) -> None:
        if not self._filling:
            self._name_edited = True
        self._update_note()

    def memory(self) -> str:
        return self.memory_combo.get_active_id() or FLASH

    def _update_note(self, _widget=None) -> None:
        if self._prepared is None:
            self.upload_btn.set_sensitive(False)
            return
        name = self.name_entry.get_text().strip()
        size = len(self._prepared.data)
        problem = manager.upload_problem(name, size, self.memory(), self._info)
        if problem is None and not name.upper().endswith(
                self._prepared.extension):
            problem = (f"The name should end in {self._prepared.extension}: "
                       f"the printer picks PUTBMP or PUTPNG by it.")
        say(self.note, problem or manager.upload_note(
            name, size, self.memory(), self._info, self._names),
            problem is not None)
        self.upload_btn.set_sensitive(problem is None)

    def result_value(self) -> Tuple[str, bytes, str, str]:
        """(name on the printer, the file's bytes, memory, format)."""
        return (self.name_entry.get_text().strip(), self._prepared.data,
                self.memory(), self.fmt())

"""Upload Font: pick a TrueType file, see it, name it, choose a memory.
The GTK twin of qtui/upload_font.py."""

import os
from typing import Optional, Sequence, Tuple

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

from tsccore import fonts, manager, settings, tspl
from tsccore.tspl import FLASH

from .util import add_row, note_label, pixbuf, say

SAMPLE = "The quick brown fox 0123456789"


class UploadFontDialog(Gtk.Dialog):
    def __init__(self, parent, info: Optional[tspl.Info],
                 names: Sequence[str] = ()):
        super().__init__(title="Upload Font", transient_for=parent,
                         modal=True)
        self.set_name("upload_font_dialog")
        self.set_default_size(520, -1)
        self._info = info
        self._names = list(names)
        self._path = ''
        self._data = b''
        self._name_edited = False
        self._filling = False

        self.add_button("_Cancel", Gtk.ResponseType.CANCEL)
        self.upload_btn = self.add_button("_Upload", Gtk.ResponseType.OK)
        self.upload_btn.set_name("upload")
        self.set_default_response(Gtk.ResponseType.OK)

        area = self.get_content_area()
        area.set_border_width(12)
        area.set_spacing(8)
        grid = Gtk.Grid(column_spacing=12, row_spacing=6)
        area.pack_start(grid, False, False, 0)

        file_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.file_entry = Gtk.Entry()
        self.file_entry.set_name("file")
        self.file_entry.set_editable(False)
        self.file_entry.set_placeholder_text("No font chosen")
        file_box.pack_start(self.file_entry, True, True, 0)
        self.choose_btn = Gtk.Button.new_with_mnemonic("_Choose…")
        self.choose_btn.set_name("choose_file")
        file_box.pack_start(self.choose_btn, False, False, 0)
        add_row(grid, "Font file:", file_box, self.choose_btn)

        self.family_label = note_label("family")
        add_row(grid, "Family:", self.family_label)

        self.preview = Gtk.Image()
        self.preview.set_name("preview")
        self.preview.set_halign(Gtk.Align.START)
        self.preview.set_size_request(-1, 48)
        add_row(grid, "Preview:", self.preview)

        self.name_entry = Gtk.Entry()
        self.name_entry.set_name("printer_name")
        self.name_entry.set_activates_default(True)
        self.name_entry.set_tooltip_text("The name the font is stored under. "
                                         "TEXT commands use it, so it is "
                                         "case sensitive.")
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
        self.name_entry.connect("changed", self._on_name_changed)
        self.memory_combo.connect("changed", self._update)
        self._update()
        area.show_all()

    def _on_choose(self, _button) -> None:
        chooser = Gtk.FileChooserDialog(
            title="Choose a TrueType Font", transient_for=self,
            action=Gtk.FileChooserAction.OPEN)
        chooser.add_buttons("_Cancel", Gtk.ResponseType.CANCEL,
                            "_Open", Gtk.ResponseType.ACCEPT)
        fonts_filter = Gtk.FileFilter()
        fonts_filter.set_name("TrueType fonts")
        for pattern in ("*.ttf", "*.TTF", "*.ttc", "*.TTC"):
            fonts_filter.add_pattern(pattern)
        chooser.add_filter(fonts_filter)
        everything = Gtk.FileFilter()
        everything.set_name("All files")
        everything.add_pattern("*")
        chooser.add_filter(everything)
        chooser.set_current_folder(settings.load_folder('fonts',
                                                        '/usr/share/fonts'))
        path = (chooser.get_filename()
                if chooser.run() == Gtk.ResponseType.ACCEPT else None)
        chooser.destroy()
        if path:
            settings.save_folder('fonts', os.path.dirname(path))
            self.set_file(path)

    def set_file(self, path: str) -> None:
        """Show `path` as the font to upload."""
        family = fonts.family_for_file(path)
        try:
            with open(path, 'rb') as f:
                data = f.read()
        except OSError as e:
            family, data = None, b''
            say(self.note, f"Cannot read {path}: {e.strerror or e}", True)
        self._path, self._data = path, data if family else b''
        self.file_entry.set_text(path)
        if family is None:
            self.family_label.set_text("Not a TrueType font")
            self.preview.clear()
        else:
            self.family_label.set_text(family)
            image = fonts.preview_image(path, SAMPLE, 28)
            if image is not None:
                self.preview.set_from_pixbuf(pixbuf(image, 460, 60))
        if not self._name_edited:
            self._filling = True
            self.name_entry.set_text(tspl.suggest_name(
                path, os.path.splitext(path)[1] or '.TTF', self._names)
                if family else '')
            self._filling = False
        self._update()

    def _on_name_changed(self, _entry) -> None:
        if not self._filling:
            self._name_edited = True
        self._update()

    def memory(self) -> str:
        return self.memory_combo.get_active_id() or FLASH

    def _update(self, _widget=None) -> None:
        name = self.name_entry.get_text().strip()
        if not self._data:
            say(self.note, "Choose a TrueType font (.ttf) file.")
            self.upload_btn.set_sensitive(False)
            return
        problem = manager.upload_problem(name, len(self._data), self.memory(),
                                         self._info)
        say(self.note, manager.upload_note(name, len(self._data),
                                           self.memory(), self._info,
                                           self._names), problem is not None)
        self.upload_btn.set_sensitive(problem is None)

    def result_value(self) -> Tuple[str, bytes, str]:
        """(name on the printer, the file's bytes, memory)."""
        return self.name_entry.get_text().strip(), self._data, self.memory()

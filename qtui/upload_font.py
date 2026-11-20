"""Upload Font: pick a TrueType file, see it, name it, choose a memory."""

import os
from typing import Optional, Sequence, Tuple

from PySide2.QtWidgets import (QComboBox, QDialog, QDialogButtonBox,
                               QFileDialog, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QVBoxLayout)

from tsccore import fonts, manager, settings, tspl
from tsccore.tspl import FLASH

from .util import pixmap, say

SAMPLE = "The quick brown fox 0123456789"
FONT_FILTER = "TrueType fonts (*.ttf *.TTF *.ttc *.TTC);;All files (*)"


class UploadFontDialog(QDialog):
    def __init__(self, parent, info: Optional[tspl.Info],
                 names: Sequence[str] = ()):
        super().__init__(parent)
        self.setWindowTitle("Upload Font")
        self.setObjectName("upload_font_dialog")
        self.resize(520, 0)
        self._info = info
        self._names = list(names)
        self._path = ''
        self._data = b''
        self._name_edited = False

        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)

        file_row = QHBoxLayout()
        self.file_edit = QLineEdit()
        self.file_edit.setObjectName("file")
        self.file_edit.setReadOnly(True)
        self.file_edit.setPlaceholderText("No font chosen")
        file_row.addWidget(self.file_edit, 1)
        self.choose_btn = QPushButton("&Choose…")
        self.choose_btn.setObjectName("choose_file")
        file_row.addWidget(self.choose_btn)
        form.addRow("Font file:", file_row)

        self.family_label = QLabel()
        self.family_label.setObjectName("family")
        form.addRow("Family:", self.family_label)

        self.preview = QLabel()
        self.preview.setObjectName("preview")
        self.preview.setMinimumHeight(48)
        form.addRow("Preview:", self.preview)

        self.name_edit = QLineEdit()
        self.name_edit.setObjectName("printer_name")
        self.name_edit.setToolTip("The name the font is stored under. TEXT "
                                  "commands use it, so it is case sensitive.")
        name_label = QLabel("&Name on printer:")
        name_label.setBuddy(self.name_edit)
        form.addRow(name_label, self.name_edit)

        self.memory_combo = QComboBox()
        self.memory_combo.setObjectName("memory")
        for memory, label in manager.memory_choices(info):
            self.memory_combo.addItem(label, memory)
        memory_label = QLabel("&Memory:")
        memory_label.setBuddy(self.memory_combo)
        form.addRow(memory_label, self.memory_combo)

        self.note = QLabel()
        self.note.setObjectName("note")
        self.note.setWordWrap(True)
        layout.addWidget(self.note)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok
                                        | QDialogButtonBox.Cancel)
        self.upload_btn = self.buttons.button(QDialogButtonBox.Ok)
        self.upload_btn.setText("&Upload")
        self.upload_btn.setObjectName("upload")
        layout.addWidget(self.buttons)

        self.choose_btn.clicked.connect(self._on_choose)
        self.name_edit.textEdited.connect(self._on_name_edited)
        self.memory_combo.currentIndexChanged.connect(self._update)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self._update()

    def _on_choose(self) -> None:
        folder = settings.load_folder('fonts', '/usr/share/fonts')
        path, _ = QFileDialog.getOpenFileName(self, "Choose a TrueType Font",
                                              folder, FONT_FILTER)
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
        self.file_edit.setText(path)
        if family is None:
            self.family_label.setText("Not a TrueType font")
            self.preview.clear()
        else:
            self.family_label.setText(family)
            image = fonts.preview_image(path, SAMPLE, 28)
            if image is not None:
                self.preview.setPixmap(pixmap(image, 460, 60))
        if not self._name_edited:
            self.name_edit.setText(tspl.suggest_name(
                path, os.path.splitext(path)[1] or '.TTF', self._names)
                if family else '')
        self._update()

    def _on_name_edited(self, _text) -> None:
        self._name_edited = True
        self._update()

    def memory(self) -> str:
        return self.memory_combo.currentData() or FLASH

    def _update(self, _index=None) -> None:
        name = self.name_edit.text().strip()
        if not self._data:
            say(self.note, "Choose a TrueType font (.ttf) file.")
            self.upload_btn.setEnabled(False)
            return
        problem = manager.upload_problem(name, len(self._data), self.memory(),
                                         self._info)
        say(self.note, manager.upload_note(name, len(self._data),
                                           self.memory(), self._info,
                                           self._names), problem is not None)
        self.upload_btn.setEnabled(problem is None)

    def result_value(self) -> Tuple[str, bytes, str]:
        """(name on the printer, the file's bytes, memory)."""
        return self.name_edit.text().strip(), self._data, self.memory()

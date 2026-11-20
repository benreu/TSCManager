"""Upload Image: pick a picture, size it in dots or mm, choose how it becomes
a printer file, see exactly what will be sent, name it, choose a memory."""

import os
from typing import Optional, Sequence, Tuple

from PIL import Image
from PySide2.QtCore import Qt
from PySide2.QtWidgets import (QButtonGroup, QComboBox, QDialog,
                               QDialogButtonBox, QDoubleSpinBox, QFileDialog,
                               QFormLayout, QFrame, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QRadioButton, QSpinBox,
                               QVBoxLayout)

from tsccore import images, manager, settings, tspl
from tsccore.tspl import FLASH

from .util import pixmap, say

IMAGE_FILTER = ("Pictures (*.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff "
                "*.webp *.PNG *.JPG *.JPEG *.BMP *.GIF *.TIF *.TIFF);;"
                "All files (*)")
DOTS, MM = 'dots', 'mm'
PREVIEW_SIZE = (360, 220)
# A picture comes in no wider than this many inches unless it is smaller.
DEFAULT_INCHES = 4


class UploadImageDialog(QDialog):
    def __init__(self, parent, info: Optional[tspl.Info],
                 names: Sequence[str] = ()):
        super().__init__(parent)
        self.setWindowTitle("Upload Image")
        self.setObjectName("upload_image_dialog")
        self._info = info
        self._names = list(names)
        self._dpi = (info.dpi if info and info.dpi else 203)
        self._source = ''
        self._grey: Optional[Image.Image] = None
        self._size = (0, 0)              # in dots
        self._prepared: Optional[images.Prepared] = None
        self._name_edited = False
        self._updating = False

        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)

        file_row = QHBoxLayout()
        self.file_edit = QLineEdit()
        self.file_edit.setObjectName("file")
        self.file_edit.setReadOnly(True)
        self.file_edit.setPlaceholderText("No picture chosen")
        file_row.addWidget(self.file_edit, 1)
        self.choose_btn = QPushButton("&Choose…")
        self.choose_btn.setObjectName("choose_file")
        file_row.addWidget(self.choose_btn)
        form.addRow("Picture:", file_row)

        self.original_label = QLabel()
        self.original_label.setObjectName("original")
        form.addRow("Original:", self.original_label)

        size_row = QHBoxLayout()
        self.width_spin = QDoubleSpinBox()
        self.width_spin.setObjectName("width")
        self.height_spin = QDoubleSpinBox()
        self.height_spin.setObjectName("height")
        for spin in (self.width_spin, self.height_spin):
            spin.setRange(1, 10000)
            spin.setKeyboardTracking(False)
        self.unit_combo = QComboBox()
        self.unit_combo.setObjectName("unit")
        self.unit_combo.addItem("dots", DOTS)
        self.unit_combo.addItem("mm", MM)
        size_row.addWidget(self.width_spin)
        size_row.addWidget(QLabel("×"))
        size_row.addWidget(self.height_spin)
        size_row.addWidget(self.unit_combo)
        size_row.addStretch(1)
        size_label = QLabel("&Size:")
        size_label.setBuddy(self.width_spin)
        form.addRow(size_label, size_row)
        self.size_note = QLabel()
        self.size_note.setObjectName("size_note")
        form.addRow("", self.size_note)

        self.format_combo = QComboBox()
        self.format_combo.setObjectName("format")
        for fmt, label, _extension, _needs in images.FORMATS:
            self.format_combo.addItem(label, fmt)
        format_label = QLabel("&Format:")
        format_label.setBuddy(self.format_combo)
        form.addRow(format_label, self.format_combo)
        self.needs_label = QLabel()
        self.needs_label.setObjectName("format_needs")
        self.needs_label.setWordWrap(True)
        form.addRow("", self.needs_label)

        bw_row = QHBoxLayout()
        self.dither_radio = QRadioButton("&Dither")
        self.dither_radio.setObjectName("dither")
        self.dither_radio.setToolTip("Keep a photo's shading as a pattern of "
                                     "dots.")
        self.threshold_radio = QRadioButton("&Threshold")
        self.threshold_radio.setObjectName("threshold")
        self.threshold_radio.setToolTip("Every pixel darker than the level "
                                        "prints black: crisp logos and text.")
        self.threshold_spin = QSpinBox()
        self.threshold_spin.setObjectName("threshold_level")
        self.threshold_spin.setRange(1, 254)
        self.threshold_spin.setValue(128)
        group = QButtonGroup(self)
        group.addButton(self.dither_radio)
        group.addButton(self.threshold_radio)
        self.dither_radio.setChecked(True)
        bw_row.addWidget(self.dither_radio)
        bw_row.addWidget(self.threshold_radio)
        bw_row.addWidget(self.threshold_spin)
        bw_row.addStretch(1)
        form.addRow("Black and white:", bw_row)

        self.preview = QLabel()
        self.preview.setObjectName("preview")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setFrameShape(QFrame.StyledPanel)
        self.preview.setMinimumSize(*PREVIEW_SIZE)
        form.addRow("Preview:", self.preview)

        self.name_edit = QLineEdit()
        self.name_edit.setObjectName("printer_name")
        self.name_edit.setToolTip("The name the picture is stored under. "
                                  "PUTBMP and PUTPNG use it, so it is case "
                                  "sensitive.")
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
        self.width_spin.valueChanged.connect(self._on_width)
        self.height_spin.valueChanged.connect(self._on_height)
        self.unit_combo.currentIndexChanged.connect(self._show_size)
        self.format_combo.currentIndexChanged.connect(self._on_format)
        self.dither_radio.toggled.connect(self._remake)
        self.threshold_spin.valueChanged.connect(self._remake)
        self.name_edit.textEdited.connect(self._on_name_edited)
        self.memory_combo.currentIndexChanged.connect(self._update_note)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self._enable_size(False)
        self._on_format()

    # --- choosing ---------------------------------------------------------

    def _on_choose(self) -> None:
        folder = settings.load_folder('images', os.path.expanduser('~'))
        path, _ = QFileDialog.getOpenFileName(self, "Choose a Picture", folder,
                                              IMAGE_FILTER)
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
            self.file_edit.setText(path)
            self.original_label.setText("Not a picture this app can read")
            self._enable_size(False)
            self._prepared = None
            self.preview.clear()
            say(self.note, f"Cannot read {os.path.basename(path)}: {e}", True)
            self.upload_btn.setEnabled(False)
            return
        self._source = path
        self.file_edit.setText(path)
        w, h = self._grey.size
        self.original_label.setText(f"{w} × {h} pixels")
        widest = self._dpi * DEFAULT_INCHES
        self._size = images.fit_size((w, h), width=min(w, widest))
        self._enable_size(True)
        self._show_size()
        self._remake()

    def _enable_size(self, on: bool) -> None:
        for widget in (self.width_spin, self.height_spin, self.unit_combo):
            widget.setEnabled(on)

    # --- size -----------------------------------------------------------

    def unit(self) -> str:
        return self.unit_combo.currentData() or DOTS

    def _show_size(self, _index=None) -> None:
        """Put the size in dots into the spins, in the unit chosen."""
        self._updating = True
        try:
            mm = self.unit() == MM
            for spin, count in ((self.width_spin, self._size[0]),
                                (self.height_spin, self._size[1])):
                spin.setDecimals(1 if mm else 0)
                spin.setSingleStep(1 if mm else 8)
                spin.setValue(images.millimetres(count, self._dpi) if mm
                              else count)
        finally:
            self._updating = False
        w, h = self._size
        self.size_note.setText(
            f"{w} × {h} dots: {images.millimetres(w, self._dpi):.1f} × "
            f"{images.millimetres(h, self._dpi):.1f} mm at {self._dpi} dpi")

    def _to_dots(self, value: float) -> int:
        return (images.dots(value, self._dpi) if self.unit() == MM
                else max(1, round(value)))

    def _on_width(self, value: float) -> None:
        if self._updating or self._grey is None:
            return
        self._size = images.fit_size(self._grey.size,
                                     width=self._to_dots(value))
        self._show_size()
        self._remake()

    def _on_height(self, value: float) -> None:
        if self._updating or self._grey is None:
            return
        self._size = images.fit_size(self._grey.size,
                                     height=self._to_dots(value))
        self._show_size()
        self._remake()

    # --- format and preview ----------------------------------------------

    def fmt(self) -> str:
        return self.format_combo.currentData() or images.BMP_1BIT

    def _on_format(self, _index=None) -> None:
        for fmt, _label, _extension, needs in images.FORMATS:
            if fmt == self.fmt():
                self.needs_label.setText(f"Prints on {needs}.")
        black_and_white = self.fmt() != images.BMP_8BIT
        for widget in (self.dither_radio, self.threshold_radio,
                       self.threshold_spin):
            widget.setEnabled(black_and_white)
        self._remake()

    def _remake(self, _value=None) -> None:
        """Make the file again from the current choices, and show it."""
        if self._grey is None:
            self.upload_btn.setEnabled(False)
            say(self.note, "Choose a picture.")
            return
        self.threshold_spin.setEnabled(self.fmt() != images.BMP_8BIT
                                       and self.threshold_radio.isChecked())
        self._prepared = images.prepare(
            self._grey, self._size, self.fmt(),
            dither=self.dither_radio.isChecked(),
            threshold=self.threshold_spin.value())
        self.preview.setPixmap(pixmap(self._prepared.preview, *PREVIEW_SIZE))
        if not self._name_edited:
            self.name_edit.setText(tspl.suggest_name(
                self._source, self._prepared.extension, self._names))
        self._update_note()

    def _on_name_edited(self, _text) -> None:
        self._name_edited = True
        self._update_note()

    def memory(self) -> str:
        return self.memory_combo.currentData() or FLASH

    def _update_note(self, _index=None) -> None:
        if self._prepared is None:
            self.upload_btn.setEnabled(False)
            return
        name = self.name_edit.text().strip()
        size = len(self._prepared.data)
        problem = manager.upload_problem(name, size, self.memory(), self._info)
        if problem is None and not name.upper().endswith(
                self._prepared.extension):
            problem = (f"The name should end in {self._prepared.extension}: "
                       f"the printer picks PUTBMP or PUTPNG by it.")
        say(self.note, problem or manager.upload_note(
            name, size, self.memory(), self._info, self._names),
            problem is not None)
        self.upload_btn.setEnabled(problem is None)

    def result_value(self) -> Tuple[str, bytes, str, str]:
        """(name on the printer, the file's bytes, memory, format)."""
        return (self.name_edit.text().strip(), self._prepared.data,
                self.memory(), self.fmt())

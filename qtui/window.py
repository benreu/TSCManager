"""
The main window: the printer at the top, its files below, and a row of
buttons that act on them. Every printer call goes through the busy bar, so
the window never freezes and every call can be cancelled.
"""

import sys
from typing import Optional

from PySide2.QtCore import Qt, QTimer
from PySide2.QtWidgets import (QAbstractItemView, QApplication, QDialog,
                               QGroupBox, QHBoxLayout, QHeaderView, QLabel,
                               QMainWindow, QPushButton, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

from tsccore import manager, printer_io, settings, tspl
from tsccore.connection import Connection, PortProblem
from tsccore.manager import Loaded, Row

from .busy import BusyBar
from .printer_rows import PrinterRows
from .upload_font import UploadFontDialog
from .upload_image import UploadImageDialog
from .util import ERROR_STYLE, say


def failure_text(error: Exception, printer: Connection) -> str:
    """A printer call's failure, for the message line."""
    if isinstance(error, PortProblem):
        return str(error)
    if isinstance(error, OSError):
        return (f"Could not reach {printer.where()}: "
                f"{error.strerror or error}")
    return str(error)


class MainWindow(QMainWindow):
    def __init__(self, printer: Optional[Connection] = None,
                 autoconnect: bool = True):
        super().__init__()
        self.setWindowTitle(manager.APP_NAME)
        self.resize(640, 600)
        self.printer: Optional[Connection] = None    # connected to
        self.loaded: Optional[Loaded] = None
        self.session = manager.Session()
        printer = printer or Connection()

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        printer_box = QGroupBox("Printer")
        printer_layout = QVBoxLayout(printer_box)
        self.rows = PrinterRows(printer)
        printer_layout.addWidget(self.rows.box)
        connect_row = QHBoxLayout()
        self.connect_btn = QPushButton("&Connect")
        self.connect_btn.setObjectName("connect")
        self.connect_btn.setToolTip("Ask this printer for its files and "
                                    "memory.")
        connect_row.addWidget(self.connect_btn)
        connect_row.addStretch(1)
        printer_layout.addLayout(connect_row)
        self.printer_line = QLabel(manager.NOT_CONNECTED)
        self.printer_line.setObjectName("printer_line")
        self.printer_line.setWordWrap(True)
        printer_layout.addWidget(self.printer_line)
        self.memory_line = QLabel()
        self.memory_line.setObjectName("memory_line")
        printer_layout.addWidget(self.memory_line)
        layout.addWidget(printer_box)

        files_box = QGroupBox("Files on the printer")
        files_layout = QVBoxLayout(files_box)
        self.files_status = QLabel(manager.NOT_CONNECTED)
        self.files_status.setObjectName("files_status")
        self.files_status.setWordWrap(True)
        files_layout.addWidget(self.files_status)
        self.files = QTreeWidget()
        self.files.setObjectName("files")
        self.files.setHeaderLabels(["Name", "Kind"])
        self.files.setRootIsDecorated(False)
        self.files.setSelectionMode(QAbstractItemView.SingleSelection)
        self.files.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.files.header().setStretchLastSection(False)
        files_layout.addWidget(self.files, 1)

        self.buttons = {}
        button_row = QHBoxLayout()
        for action in manager.ACTIONS:
            button = QPushButton(manager.ACTION_LABELS[action])
            button.setObjectName(action)
            button.setToolTip(manager.ACTION_TIPS[action])
            button_row.addWidget(button)
            self.buttons[action] = button
        button_row.addStretch(1)
        files_layout.addLayout(button_row)
        layout.addWidget(files_box, 1)

        bottom = QHBoxLayout()
        self.message = QLabel()
        self.message.setObjectName("message")
        self.message.setWordWrap(True)
        bottom.addWidget(self.message, 1)
        self.busy = BusyBar([self.connect_btn, *self.buttons.values()],
                            lambda text: say(self.message, text), self)
        bottom.addWidget(self.busy)
        layout.addLayout(bottom)

        self.connect_btn.clicked.connect(self.connect_printer)
        self.files.itemSelectionChanged.connect(self._update_buttons)
        self.buttons['refresh'].clicked.connect(self.refresh)
        self.buttons['upload_font'].clicked.connect(self.upload_font)
        self.buttons['upload_image'].clicked.connect(self.upload_image)
        self.buttons['delete'].clicked.connect(self.delete_file)
        self.buttons['test_print'].clicked.connect(self.test_print)
        self.buttons['move_to_flash'].clicked.connect(self.move_to_flash)
        self._update_buttons()

        if autoconnect and (printer.address or printer.is_usb):
            QTimer.singleShot(0, self.connect_printer)

    # --- connecting ---------------------------------------------------

    def connect_printer(self) -> None:
        printer, problem = self.rows.value()
        if printer is None:
            say(self.message, problem, True)
            return
        say(self.message, f"Asking {printer.where()}…")
        self._load(printer, saving=True)

    def refresh(self) -> None:
        """Read the printer again, keeping the message line as it is."""
        if self.printer is not None:
            self._load(self.printer, then=self.message.text(),
                       then_error=self.message.styleSheet() == ERROR_STYLE)

    def _load(self, printer: Connection, saving: bool = False,
              then: str = '', then_error: bool = False) -> None:
        def done(loaded, error):
            if isinstance(error, printer_io.Cancelled):
                say(self.message, "Cancelled.")
                return
            if error is not None:
                say(self.message, failure_text(error, printer), True)
                return
            if not loaded.answered:
                say(self.message, manager.NO_ANSWER, True)
                return
            self.printer = printer
            if saving:
                settings.save_printer(printer)
            self._show(loaded)
            say(self.message, then, then_error)

        self.busy.run(lambda cancel: manager.load(printer, cancel), done)

    def _show(self, loaded: Loaded) -> None:
        self.loaded = loaded
        info = loaded.info
        self.printer_line.setText(manager.printer_line(self.printer, info))
        self.memory_line.setText(manager.memory_line(info))
        self.files_status.setText(manager.files_status(loaded))
        chosen = self.selected()
        self.files.clear()
        for row in manager.rows(loaded.names):
            item = QTreeWidgetItem([row.name, row.kind_label])
            item.setData(0, Qt.UserRole, row)
            self.files.addTopLevelItem(item)
            if chosen is not None and row.name == chosen.name:
                self.files.setCurrentItem(item)
        self.files.resizeColumnToContents(1)
        self._update_buttons()

    # --- the list -------------------------------------------------------

    def selected(self) -> Optional[Row]:
        items = self.files.selectedItems()
        return items[0].data(0, Qt.UserRole) if items else None

    def _names(self):
        return list(self.loaded.names or []) if self.loaded else []

    def _info(self):
        return self.loaded.info if self.loaded else None

    def _update_buttons(self) -> None:
        if self.busy.running:
            return
        states = manager.enabled_actions(self.printer is not None,
                                         self.selected(), self._info())
        for action, on in states.items():
            self.buttons[action].setEnabled(on)

    # --- the actions ------------------------------------------------------

    def _run(self, work, success: str, refresh: bool = True) -> None:
        """Run `work(cancel)` on the busy bar; then say `success` and, if
        asked, read the printer again."""
        printer = self.printer

        def done(_result, error):
            if isinstance(error, printer_io.Cancelled):
                say(self.message, "Cancelled.")
            elif error is not None:
                say(self.message, failure_text(error, printer), True)
            else:
                say(self.message, success)
            if refresh and not isinstance(error, printer_io.Cancelled):
                self.refresh()

        self.busy.run(work, done)

    def _upload(self, name: str, data: bytes, memory: str) -> None:
        printer = self.printer
        say(self.message, f"Storing {name}…")
        self._run(lambda cancel: manager.upload(
            printer, name, data, memory, cancel=cancel,
            fraction=self.busy.report_fraction),
            f"Stored {name} in {tspl.MEMORY_NAMES[memory]}.")

    def upload_font(self) -> None:
        dialog = UploadFontDialog(self, self._info(), self._names())
        if dialog.exec_() != QDialog.Accepted:
            return
        name, data, memory = dialog.result_value()
        self._upload(name, data, memory)

    def upload_image(self) -> None:
        dialog = UploadImageDialog(self, self._info(), self._names())
        if dialog.exec_() != QDialog.Accepted:
            return
        name, data, memory, fmt = dialog.result_value()
        from tsccore import images
        if fmt == images.BMP_8BIT:
            self.session.grey.add(name)
        else:
            self.session.grey.discard(name)
        self._upload(name, data, memory)

    def delete_file(self) -> None:
        row = self.selected()
        if row is None:
            say(self.message, manager.PICK_A_FILE)
            return
        printer, memories = self.printer, manager.delete_memories(self._info())
        say(self.message, f"Deleting {row.name}…")
        self._run(lambda cancel: tspl.delete(printer, row.name, memories,
                                             cancel=cancel),
                  f"Deleted {row.name}.")

    def test_print(self) -> None:
        row = self.selected()
        if row is None:
            say(self.message, manager.PICK_A_FILE)
            return
        printer, options = self.printer, self.session.test_options(row.name)
        self._run(lambda cancel: tspl.test_print(printer, row.name,
                                                 cancel=cancel, **options),
                  f"Sent a test label for {row.name}.", refresh=False)

    def move_to_flash(self) -> None:
        printer = self.printer
        say(self.message, "Moving DRAM's files to flash…")
        self._run(lambda cancel: tspl.move_to_flash(printer, cancel=cancel),
                  "Moved the files in DRAM to flash.")

    def closeEvent(self, event) -> None:
        self.busy.abandon()
        super().closeEvent(event)


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(manager.APP_NAME)
    window = MainWindow(settings.load_printer())
    window.show()
    return app.exec_()

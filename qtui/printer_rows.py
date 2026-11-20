"""
The printer rows at the top of the window: Network or USB, then Address and
Port or the USB Printer list.

Adapted from LinuxZPL's qtui/dialogs.py _PrinterRows (commit 5e99b57),
without its DPI and Font memory rows, which are ZPL's. Only the rows for
the chosen connection are shown, but both halves are kept: the address
typed stays while USB is chosen, and the other way round.
"""

from typing import Optional, Tuple

from PySide2.QtWidgets import (QComboBox, QGridLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QRadioButton, QSpinBox,
                               QWidget)

from tsccore import connection
from tsccore.connection import Connection


class PrinterRows:
    def __init__(self, printer: Connection):
        self._printer = printer
        self.box = QWidget()
        # A grid rather than a form: a QFormLayout keeps the spacing of a row
        # it hides, and Network and USB each hide the other's rows.
        self.grid = QGridLayout(self.box)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setColumnStretch(1, 1)
        self._labels = {}

        kinds = QHBoxLayout()
        self.network_radio = QRadioButton("&Network")
        self.network_radio.setObjectName("connection_network")
        self.usb_radio = QRadioButton("&USB")
        self.usb_radio.setObjectName("connection_usb")
        kinds.addWidget(self.network_radio)
        kinds.addWidget(self.usb_radio)
        kinds.addStretch(1)
        self._add_row("Connection:", kinds, self.network_radio)

        self.address_edit = QLineEdit(printer.address)
        self.address_edit.setObjectName("address")
        self.address_edit.setPlaceholderText("192.168.1.50")
        self._add_row("&Address:", self.address_edit)

        self.port_spin = QSpinBox()
        self.port_spin.setObjectName("port")
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(printer.port)
        self.port_spin.setToolTip("The printer's raw printing port: 9100 on "
                                  "nearly every TSC printer.")
        self._add_row("&Port:", self.port_spin)

        self._usb_row = QHBoxLayout()
        self.usb_combo = QComboBox()
        self.usb_combo.setObjectName("usb_printer")
        self._usb_row.addWidget(self.usb_combo, 1)
        self.usb_refresh_btn = QPushButton("Re&fresh List")
        self.usb_refresh_btn.setObjectName("usb_refresh")
        self.usb_refresh_btn.setToolTip("Look again for printers plugged in "
                                        "by USB.")
        self._usb_row.addWidget(self.usb_refresh_btn)
        self._add_row("P&rinter:", self._usb_row, self.usb_combo)
        self._usb_entries = []
        self._list_usb(printer)

        self.usb_refresh_btn.clicked.connect(
            lambda: self._list_usb(self._chosen_usb() or self._printer))
        (self.usb_radio if printer.is_usb else self.network_radio).setChecked(
            True)
        self.network_radio.toggled.connect(self._show_kind)
        self._show_kind()

    def _add_row(self, text, field, buddy=None):
        label = QLabel(text)
        label.setBuddy(buddy or field)
        row = self.grid.rowCount()
        self.grid.addWidget(label, row, 0)
        if isinstance(field, QWidget):
            self.grid.addWidget(field, row, 1)
        else:
            self.grid.addLayout(field, row, 1)
        self._labels[id(field)] = label

    def value(self) -> Tuple[Optional[Connection], Optional[str]]:
        """(Connection, None) for the printer the rows describe, or (None,
        what is missing)."""
        address = self.address_edit.text().strip()
        port = self.port_spin.value()
        if self.usb_radio.isChecked():
            usb = self._chosen_usb()
            if usb is None:
                return None, connection.NO_USB_CHOSEN
            carried = (self._printer.as_network(address, port) if address
                       else self._printer)
            return carried.as_usb(usb.usb_serial, usb.usb_name), None
        if not address:
            return None, connection.NO_ADDRESS
        return self._printer.as_network(address, port), None

    def _chosen_usb(self) -> Optional[Connection]:
        index = self.usb_combo.currentIndex()
        if 0 <= index < len(self._usb_entries):
            return self._usb_entries[index]
        return None

    def _list_usb(self, keep: Connection) -> None:
        """Fill the USB Printer list afresh, on `keep` if it is there."""
        entries, index = connection.usb_choices(keep)
        self.usb_combo.clear()
        for label, _printer in entries:
            self.usb_combo.addItem(label)
        self._usb_entries = [printer for _label, printer in entries]
        self.usb_combo.setCurrentIndex(index)

    def _show_kind(self, _checked=None) -> None:
        network = self.network_radio.isChecked()
        for field, widgets, shown in (
                (self.address_edit, (self.address_edit,), network),
                (self.port_spin, (self.port_spin,), network),
                (self._usb_row, (self.usb_combo, self.usb_refresh_btn),
                 not network)):
            for widget in widgets + (self._labels[id(field)],):
                widget.setVisible(shown)

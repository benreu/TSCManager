"""
The printer rows at the top of the window: Network or USB, then Address and
Port or the USB Printer list. The GTK twin of qtui/printer_rows.py.

Adapted from LinuxZPL's gtkui/window.py _PrinterRows (commit 5e99b57),
without its DPI and Font memory rows. The rows for one connection are
shown once, then kept out of the window's show_all(), which would
otherwise show both kinds at once.
"""

from typing import Optional, Tuple

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

from tsccore import connection
from tsccore.connection import Connection

from .util import add_row


class PrinterRows:
    def __init__(self, printer: Connection):
        self._printer = printer
        self.box = Gtk.Grid(column_spacing=12, row_spacing=6)

        kinds = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.network_radio = Gtk.RadioButton.new_with_mnemonic_from_widget(
            None, "_Network")
        self.network_radio.set_name("connection_network")
        self.usb_radio = Gtk.RadioButton.new_with_mnemonic_from_widget(
            self.network_radio, "_USB")
        self.usb_radio.set_name("connection_usb")
        kinds.pack_start(self.network_radio, False, False, 0)
        kinds.pack_start(self.usb_radio, False, False, 0)
        add_row(self.box, "Connection:", kinds, self.network_radio)

        self.address_entry = Gtk.Entry()
        self.address_entry.set_name("address")
        self.address_entry.set_text(printer.address)
        self.address_entry.set_placeholder_text("192.168.1.50")
        self._address_label = add_row(self.box, "_Address:",
                                      self.address_entry)

        self.port_spin = Gtk.SpinButton.new_with_range(1, 65535, 1)
        self.port_spin.set_name("port")
        self.port_spin.set_value(printer.port)
        self.port_spin.set_tooltip_text("The printer's raw printing port: "
                                        "9100 on nearly every TSC printer.")
        self._port_label = add_row(self.box, "_Port:", self.port_spin)

        self._usb_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,
                                spacing=8)
        self.usb_combo = Gtk.ComboBoxText()
        self.usb_combo.set_name("usb_printer")
        self._usb_box.pack_start(self.usb_combo, True, True, 0)
        self.usb_refresh_btn = Gtk.Button.new_with_mnemonic("Re_fresh List")
        self.usb_refresh_btn.set_name("usb_refresh")
        self.usb_refresh_btn.set_tooltip_text("Look again for printers "
                                              "plugged in by USB.")
        self._usb_box.pack_start(self.usb_refresh_btn, False, False, 0)
        self._usb_label = add_row(self.box, "P_rinter:", self._usb_box,
                                  self.usb_combo)
        self._usb_entries = []
        self._list_usb(printer)

        # Shown once, inside, then left to _show_kind.
        for widget in self._kind_widgets():
            widget.show_all()
            widget.set_no_show_all(True)
        (self.usb_radio if printer.is_usb else self.network_radio).set_active(
            True)
        self.network_radio.connect("toggled", self._show_kind)
        self.usb_refresh_btn.connect(
            "clicked",
            lambda _b: self._list_usb(self._chosen_usb() or self._printer))
        self._show_kind()

    def _kind_widgets(self):
        return (self._address_label, self.address_entry, self._port_label,
                self.port_spin, self._usb_label, self._usb_box)

    def value(self) -> Tuple[Optional[Connection], Optional[str]]:
        """(Connection, None) for the printer the rows describe, or (None,
        what is missing)."""
        address = self.address_entry.get_text().strip()
        port = int(self.port_spin.get_value())
        if self.usb_radio.get_active():
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
        index = self.usb_combo.get_active()
        if 0 <= index < len(self._usb_entries):
            return self._usb_entries[index]
        return None

    def _list_usb(self, keep: Connection) -> None:
        """Fill the USB Printer list afresh, on `keep` if it is there."""
        entries, index = connection.usb_choices(keep)
        self.usb_combo.remove_all()
        for label, _printer in entries:
            self.usb_combo.append_text(label)
        self._usb_entries = [printer for _label, printer in entries]
        self.usb_combo.set_active(index)

    def _show_kind(self, _radio=None) -> None:
        network = self.network_radio.get_active()
        for widget in (self._address_label, self.address_entry,
                       self._port_label, self.port_spin):
            widget.set_visible(network)
        for widget in (self._usb_label, self._usb_box):
            widget.set_visible(not network)

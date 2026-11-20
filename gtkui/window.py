"""
The main window: the printer at the top, its files below, and a row of
buttons that act on them. The GTK twin of qtui/window.py: the same rows,
buttons and messages, all from tsccore.manager.
"""

from typing import Optional

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GLib, Gtk

from tsccore import images, manager, printer_io, settings, tspl
from tsccore.connection import Connection, PortProblem
from tsccore.manager import Loaded, Row

from .busy import BusyBar
from .printer_rows import PrinterRows
from .upload_font import UploadFontDialog
from .upload_image import UploadImageDialog
from .util import is_error, note_label, say


def failure_text(error: Exception, printer: Connection) -> str:
    """A printer call's failure, for the message line."""
    if isinstance(error, PortProblem):
        return str(error)
    if isinstance(error, OSError):
        return (f"Could not reach {printer.where()}: "
                f"{error.strerror or error}")
    return str(error)


def _mnemonic(label: str) -> str:
    """A button label with its first letter as the access key."""
    return "_" + label


class MainWindow(Gtk.Window):
    def __init__(self, printer: Optional[Connection] = None,
                 autoconnect: bool = True):
        super().__init__(title=manager.APP_NAME)
        self.set_default_size(680, 600)
        self.printer: Optional[Connection] = None    # connected to
        self.loaded: Optional[Loaded] = None
        self.session = manager.Session()
        self._rows = []                              # Row per list line
        printer = printer or Connection()

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        outer.set_border_width(12)
        self.add(outer)

        printer_frame = Gtk.Frame(label="Printer")
        printer_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        printer_box.set_border_width(8)
        printer_frame.add(printer_box)
        self.rows = PrinterRows(printer)
        printer_box.pack_start(self.rows.box, False, False, 0)
        connect_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.connect_btn = Gtk.Button.new_with_mnemonic("_Connect")
        self.connect_btn.set_name("connect")
        self.connect_btn.set_tooltip_text("Ask this printer for its files "
                                          "and memory.")
        connect_row.pack_start(self.connect_btn, False, False, 0)
        printer_box.pack_start(connect_row, False, False, 0)
        self.printer_line = note_label("printer_line")
        self.printer_line.set_text(manager.NOT_CONNECTED)
        printer_box.pack_start(self.printer_line, False, False, 0)
        self.memory_line = note_label("memory_line")
        printer_box.pack_start(self.memory_line, False, False, 0)
        outer.pack_start(printer_frame, False, False, 0)

        files_frame = Gtk.Frame(label="Files on the printer")
        files_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        files_box.set_border_width(8)
        files_frame.add(files_box)
        self.files_status = note_label("files_status")
        self.files_status.set_text(manager.NOT_CONNECTED)
        files_box.pack_start(self.files_status, False, False, 0)
        self.store = Gtk.ListStore(str, str)
        self.files = Gtk.TreeView(model=self.store)
        self.files.set_name("files")
        for column_number, title in enumerate(("Name", "Kind")):
            column = Gtk.TreeViewColumn(title, Gtk.CellRendererText(),
                                        text=column_number)
            column.set_expand(column_number == 0)
            self.files.append_column(column)
        self.files.get_selection().set_mode(Gtk.SelectionMode.SINGLE)
        scroller = Gtk.ScrolledWindow()
        scroller.set_shadow_type(Gtk.ShadowType.IN)
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.add(self.files)
        files_box.pack_start(scroller, True, True, 0)

        self.buttons = {}
        button_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        for action in manager.ACTIONS:
            button = Gtk.Button.new_with_mnemonic(
                _mnemonic(manager.ACTION_LABELS[action]))
            button.set_name(action)
            button.set_tooltip_text(manager.ACTION_TIPS[action])
            button_row.pack_start(button, False, False, 0)
            self.buttons[action] = button
        files_box.pack_start(button_row, False, False, 0)
        outer.pack_start(files_frame, True, True, 0)

        bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.message = note_label("message")
        bottom.pack_start(self.message, True, True, 0)
        self.busy = BusyBar([self.connect_btn, *self.buttons.values()],
                            lambda text: say(self.message, text))
        bottom.pack_end(self.busy, False, False, 0)
        outer.pack_start(bottom, False, False, 0)

        self.connect_btn.connect("clicked", lambda _b: self.connect_printer())
        self.files.get_selection().connect(
            "changed", lambda _s: self._update_buttons())
        handlers = {'refresh': self.refresh, 'upload_font': self.upload_font,
                    'upload_image': self.upload_image,
                    'delete': self.delete_file, 'test_print': self.test_print,
                    'move_to_flash': self.move_to_flash}
        for action, handler in handlers.items():
            self.buttons[action].connect("clicked",
                                         lambda _b, h=handler: h())
        self.connect("delete-event", self._on_delete_event)
        self._update_buttons()

        if autoconnect and (printer.address or printer.is_usb):
            GLib.idle_add(self._autoconnect)

    def _autoconnect(self) -> bool:
        self.connect_printer()
        return False

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
            self._load(self.printer, then=self.message.get_text(),
                       then_error=is_error(self.message))

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
        self.printer_line.set_text(manager.printer_line(self.printer, info))
        self.memory_line.set_text(manager.memory_line(info))
        self.files_status.set_text(manager.files_status(loaded))
        chosen = self.selected()
        self.store.clear()
        self._rows = manager.rows(loaded.names)
        for row in self._rows:
            self.store.append([row.name, row.kind_label])
        if chosen is not None:
            for index, row in enumerate(self._rows):
                if row.name == chosen.name:
                    self.files.get_selection().select_path(
                        Gtk.TreePath(index))
        self._update_buttons()

    # --- the list -------------------------------------------------------

    def selected(self) -> Optional[Row]:
        _model, tree_iter = self.files.get_selection().get_selected()
        if tree_iter is None:
            return None
        index = self.store.get_path(tree_iter).get_indices()[0]
        return self._rows[index] if index < len(self._rows) else None

    def select(self, name: str) -> bool:
        """Choose the file called `name` in the list."""
        for index, row in enumerate(self._rows):
            if row.name == name:
                self.files.get_selection().select_path(Gtk.TreePath(index))
                return True
        return False

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
            self.buttons[action].set_sensitive(on)

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
        accepted = dialog.run() == Gtk.ResponseType.OK
        value = dialog.result_value() if accepted else None
        dialog.destroy()
        if value:
            self._upload(*value)

    def upload_image(self) -> None:
        dialog = UploadImageDialog(self, self._info(), self._names())
        accepted = dialog.run() == Gtk.ResponseType.OK
        value = dialog.result_value() if accepted else None
        dialog.destroy()
        if not value:
            return
        name, data, memory, fmt = value
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

    def _on_delete_event(self, _window, _event) -> bool:
        self.busy.abandon()
        return False


def main() -> int:
    GLib.set_application_name(manager.APP_NAME)
    window = MainWindow(settings.load_printer())
    window.connect("destroy", Gtk.main_quit)
    window.show_all()
    Gtk.main()
    return 0

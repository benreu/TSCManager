"""Small GTK helpers the window and dialogs share: the twins of
qtui/util.py, plus a labelled row on a Gtk.Grid."""

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import GdkPixbuf, GLib, Gtk

ERROR_COLOUR = '#b00020'


def pixbuf(image, max_width: int = 0, max_height: int = 0):
    """A GdkPixbuf of a PIL image, scaled down (never up) to fit within the
    limits given. Scaled without smoothing, so a 1-bit picture still shows
    its dots."""
    rgb = image.convert('RGB')
    w, h = rgb.size
    result = GdkPixbuf.Pixbuf.new_from_bytes(
        GLib.Bytes.new(rgb.tobytes()), GdkPixbuf.Colorspace.RGB, False, 8,
        w, h, w * 3)
    scale = 1.0
    if max_width and w > max_width:
        scale = min(scale, max_width / w)
    if max_height and h > max_height:
        scale = min(scale, max_height / h)
    if scale < 1.0:
        result = result.scale_simple(max(1, round(w * scale)),
                                     max(1, round(h * scale)),
                                     GdkPixbuf.InterpType.NEAREST)
    return result


def say(label: Gtk.Label, text: str, error: bool = False) -> None:
    """Put a message on a label, in red when it is a failure."""
    label.is_error = error
    if error:
        label.set_markup(f"<span foreground='{ERROR_COLOUR}'>"
                         f"{GLib.markup_escape_text(text)}</span>")
    else:
        label.set_text(text)


def is_error(label: Gtk.Label) -> bool:
    return getattr(label, 'is_error', False)


def add_row(grid: Gtk.Grid, text: str, field: Gtk.Widget,
            mnemonic_widget: Gtk.Widget = None) -> Gtk.Label:
    """`text` in the first column, `field` in the second, on a new row. A
    `_` in the text marks the key that focuses `mnemonic_widget` (or the
    field itself)."""
    row = len([c for c in grid.get_children()
               if grid.child_get_property(c, 'left-attach') == 0])
    label = Gtk.Label.new_with_mnemonic(text)
    label.set_halign(Gtk.Align.START)
    label.set_mnemonic_widget(mnemonic_widget or field)
    grid.attach(label, 0, row, 1, 1)
    field.set_hexpand(True)
    grid.attach(field, 1, row, 1, 1)
    return label


def note_label(name: str = '') -> Gtk.Label:
    """A left-aligned label that wraps."""
    label = Gtk.Label()
    if name:
        label.set_name(name)
    label.set_halign(Gtk.Align.START)
    label.set_xalign(0)
    label.set_line_wrap(True)
    return label

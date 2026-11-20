"""The two frontends side by side: the same named widgets, buttons, labels,
tooltips and choices in the window and in both upload dialogs, so a change
made in one and forgotten in the other fails here.

Qt goes through the offscreen plugin and GTK needs a display, so
tests/run.sh runs this under xvfb.
"""
import os
import re

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from _check import check, finish

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
from PySide2.QtWidgets import (QAbstractButton, QApplication, QComboBox,
                               QWidget)

app = QApplication([])

from tsccore import manager, tspl
import gtkui.upload_font
import gtkui.upload_image
import gtkui.window
import qtui.upload_font
import qtui.upload_image
import qtui.window

NAME = re.compile(r'^[a-z][a-z0-9_]*$')
INFO = tspl.Info(model='MB241', dpi=203, card_installed=True,
                 memory={tspl.DRAM: (8192, 8192), tspl.FLASH: (212352, 211710),
                         tspl.CARD: (31000, 31000)})


def plain(text):
    """A label without its access-key marker (& in Qt, _ in GTK)."""
    return (text or '').replace('&', '').replace('_', '')


# --- Qt -----------------------------------------------------------------
def qt_widgets(top):
    found = {}
    for widget in [top] + top.findChildren(QWidget):
        name = widget.objectName()
        if NAME.match(name) and not name.startswith('qt_'):
            found[name] = widget
    return found


def qt_describe(top):
    described = {}
    for name, widget in qt_widgets(top).items():
        entry = {'tip': widget.toolTip()}
        if isinstance(widget, QAbstractButton):
            entry['label'] = plain(widget.text())
        if isinstance(widget, QComboBox):
            entry['items'] = [widget.itemText(i) for i in range(widget.count())]
        described[name] = entry
    return described


# --- GTK ----------------------------------------------------------------
def gtk_widgets(top):
    found = {}

    def walk(widget):
        name = widget.get_name()
        if NAME.match(name):
            found[name] = widget
        if isinstance(widget, Gtk.Container):
            for child in widget.get_children():
                walk(child)
    walk(top)
    return found


def gtk_combo_items(combo):
    model = combo.get_model()
    return [row[0] for row in model]


def gtk_describe(top):
    described = {}
    for name, widget in gtk_widgets(top).items():
        entry = {'tip': widget.get_tooltip_text() or ''}
        if isinstance(widget, Gtk.Button) and not isinstance(
                widget, Gtk.ComboBox):
            entry['label'] = plain(widget.get_label())
        if isinstance(widget, Gtk.ComboBoxText):
            entry['items'] = gtk_combo_items(widget)
        described[name] = entry
    return described


def compare(what, qt, gtk):
    check(f"{what}: the same named widgets",
          set(qt) == set(gtk),
          {'only in Qt': sorted(set(qt) - set(gtk)),
           'only in GTK': sorted(set(gtk) - set(qt))})
    for name in sorted(set(qt) & set(gtk)):
        for key in ('label', 'tip', 'items'):
            if key in qt[name] or key in gtk[name]:
                if qt[name].get(key) != gtk[name].get(key):
                    check(f"{what}: {name}'s {key} is the same", False,
                          (qt[name].get(key), gtk[name].get(key)))


# --- the main window --------------------------------------------------------
qt_main = qtui.window.MainWindow(autoconnect=False)
gtk_main = gtkui.window.MainWindow(autoconnect=False)
qt_names, gtk_names = qt_describe(qt_main), gtk_describe(gtk_main)
compare("main window", qt_names, gtk_names)
check("main window: every action is a button in both, labelled alike",
      all(qt_names.get(a, {}).get('label') == gtk_names.get(a, {}).get('label')
          == manager.ACTION_LABELS[a] for a in manager.ACTIONS))
check("main window: the same title",
      qt_main.windowTitle() == gtk_main.get_title() == manager.APP_NAME)
check("main window: the list has the same columns",
      [qt_main.files.headerItem().text(i) for i in range(2)]
      == [c.get_title() for c in gtk_main.files.get_columns()])
check("main window: the same opening text",
      qt_main.printer_line.text() == gtk_main.printer_line.get_text()
      and qt_main.files_status.text() == gtk_main.files_status.get_text())

# --- the upload dialogs (with a card, so every memory is offered) -----------
for title, qt_class, gtk_class in (
        ("Upload Font", qtui.upload_font.UploadFontDialog,
         gtkui.upload_font.UploadFontDialog),
        ("Upload Image", qtui.upload_image.UploadImageDialog,
         gtkui.upload_image.UploadImageDialog)):
    qt_dialog = qt_class(qt_main, INFO, [])
    gtk_dialog = gtk_class(gtk_main, INFO, [])
    compare(title, qt_describe(qt_dialog), gtk_describe(gtk_dialog))
    check(f"{title}: the same title",
          qt_dialog.windowTitle() == gtk_dialog.get_title() == title)
    check(f"{title}: the same opening note, and Upload withheld in both",
          qt_dialog.note.text() == gtk_dialog.note.get_text()
          and not qt_dialog.upload_btn.isEnabled()
          and not gtk_dialog.upload_btn.get_sensitive())
    gtk_dialog.destroy()

gtk_main.destroy()
finish()

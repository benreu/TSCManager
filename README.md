# TSC Manager

Store, list, delete and test-print fonts and images on a TSC label printer,
in TSC's own printer language, TSPL2.

It is a companion to [LinuxZPL](https://github.com/benreu/LinuxZPL), kept apart from it so that
LinuxZPL stays a ZPL designer. The printer connection code (network and USB)
was copied from LinuxZPL at commit 5e99b57.

Two windows sit on one core: GTK 3 and PySide2/Qt 5. They have the same
rows, buttons and messages (`tests/test_conformance.py` holds them to it);
which one opens is only a question of which toolkit is installed, or which
you prefer.

Checked on a TSC MB241 (firmware 1.28.002) on the network: TrueType
fonts, black-and-white and grayscale BMPs and PNGs store, list, print,
move and delete as they should.

## Installing

It needs Python 3.8 or later, Pillow, and one of the two toolkits. On
Debian, Ubuntu or Mint:

    sudo apt install python3-pil
    sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0     # GTK
    sudo apt install python3-pyside2.qtcore python3-pyside2.qtgui \
                     python3-pyside2.qtwidgets                     # or Qt

or with pip: `pip install -r requirements-gtk.txt` (or
`requirements-qt.txt`).

For a printer on USB, your user needs to be in the `lp` group
(`sudo usermod -aG lp $USER`, then log in again).

## Running it

    ./run.sh              # or: python3 tscmanager.py [--qt | --gtk]

With no option it opens the GTK window when PyGObject is installed, and the
Qt window otherwise.

Type the printer's address (or choose USB and the printer) and press
Connect. The window shows the model, firmware, resolution and free memory,
and the files stored on the printer. The printer you connect to is
remembered for next time, in `~/.config/tscmanager/settings.ini`.

- **Upload Font…** stores a TrueType (.ttf) file. It suggests a name of up
  to eight capitals; names are case sensitive, and a label's TEXT command
  uses that name exactly.
- **Upload Image…** turns a picture into a file the printer can print,
  sized in dots or millimetres: a black-and-white BMP (any TSPL printer), a
  grayscale BMP (newer printers, direct thermal only) or a black-and-white
  PNG (newer printers; smaller than a BMP). Black and white is made by
  dithering, for photos, or a threshold, for logos and text. The preview is
  exactly what will be sent.
- **Delete** removes the chosen file. The printer's file list does not say
  which memory a file is in, so Delete removes it from every memory.
- **Test Print** prints a label in the chosen font, or showing the chosen
  image, on whatever labels the printer is set up for. It never changes the
  printer's label size.
- **Move DRAM to Flash** keeps what is in DRAM after the printer is
  switched off.

### Memory

- **DRAM** is fast to write and emptied when the printer is switched off.
- **Flash** keeps its files; uploads go there unless you choose otherwise.
- A **memory card**, on printers that take one, is offered when installed.

## The printer must take TSPL

Many TSC printers can also emulate ZPL or EPL. These commands are TSPL, so
the printer's language setting has to be TSPL (or automatic detection),
not ZPL emulation.

## Checking a printer

    ./tscmanager.py --probe 192.168.1.50            # asks, changes nothing
    ./tscmanager.py --probe 192.168.1.50 --probe-write

The first asks the printer for its model, memory and file list, and prints
each raw reply next to what was made of it. `--probe-write` also stores a
few test files in DRAM and flash, prints three test labels, and deletes
the files again.

## Tests

    tests/run.sh

Every suite is a plain Python script. The Qt suites run offscreen; the GTK
suite and the comparison of the two windows need a display, and run under
`xvfb-run` (`sudo apt install xvfb`) so that their windows stay off your
screen. A pretend printer (`tests/fake_printer.py`) answers the way the
MB241 did, so no printer is needed.

## The manual

`tspl_manual.pdf` is TSC's TSPL/TSPL2 Programming Manual 3.0, from
fs.tscprinters.com.

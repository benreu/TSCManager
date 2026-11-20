# TSC Manager

Store, list, delete and test-print fonts and images on a TSC label printer,
in TSC's own printer language, TSPL2.

It is a companion to [LinuxZPL](../LinuxZPL), kept apart from it so that
LinuxZPL stays a ZPL designer. The printer connection code (network and USB)
was copied from LinuxZPL at commit 5e99b57.

**Status:** the Qt window works; the GTK window comes next.

Checked on a TSC MB241 (firmware 1.28.002) on the network: TrueType
fonts, black-and-white and grayscale BMPs and PNGs store, list, print and
delete as they should.

## Running it

    ./run.sh              # or: python3 tscmanager.py [--qt | --gtk]

It needs Python 3.8 or later, Pillow, and PySide2 for the Qt window (see
`requirements-qt.txt` for the apt packages).

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

## The manual

`tspl_manual.pdf` is TSC's TSPL/TSPL2 Programming Manual 3.0, from
fs.tscprinters.com.

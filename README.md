# TSC Manager

Store, list, delete and test-print fonts and images on a TSC label printer,
in TSC's own printer language, TSPL2.

It is a companion to [LinuxZPL](../LinuxZPL), kept apart from it so that
LinuxZPL stays a ZPL designer. The printer connection code (network and USB)
was copied from LinuxZPL at commit 5e99b57.

**Status:** the core and a probe exist; the Qt and GTK windows come next.

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

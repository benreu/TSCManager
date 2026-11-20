#!/usr/bin/env python3
"""
TSC Manager - store, list, delete and test-print fonts and images on a TSC
label printer, in TSC's own TSPL2.

--probe asks a printer everything the app relies on and prints each raw
reply next to what was made of it: the way to check a printer, or a
firmware, against what the manual says.
"""

import argparse
import socket
import sys
import time


def parse_host(text: str):
    host, _, port = text.partition(':')
    return host, int(port or 9100)


# How long each probe question listens for its whole answer (--probe-wait).
WAIT = 3.0


def raw_exchange(host: str, port: int, request: bytes, wait: float = None):
    """Send `request` and record every chunk of the reply with the time it
    came, for `wait` seconds or until the printer closes - no early stop on
    a quiet spell, so a slow reply shows up as one."""
    wait = WAIT if wait is None else wait
    chunks = []
    sock = socket.create_connection((host, port), timeout=5)
    try:
        t0 = time.monotonic()
        sock.sendall(request)
        while True:
            left = wait - (time.monotonic() - t0)
            if left <= 0:
                break
            sock.settimeout(left)
            try:
                data = sock.recv(4096)
            except (socket.timeout, TimeoutError):
                break
            if not data:
                break
            chunks.append((time.monotonic() - t0, data))
    finally:
        sock.close()
    return chunks


def show_reply(title: str, request: bytes, chunks) -> bytes:
    reply = b''.join(data for _t, data in chunks)
    print(f"\n== {title}: sent {request!r}")
    if not chunks:
        print("   no reply")
        return reply
    for t, data in chunks:
        print(f"   +{t:5.2f}s  {data!r}")
    gaps = [b[0] - a[0] for a, b in zip(chunks, chunks[1:])]
    if gaps and max(gaps) > 0.5:
        print(f"   NOTE: a gap of {max(gaps):.2f}s inside the reply - longer "
              "than the transport's 0.5 s quiet window")
    return reply


def probe_inquiries(host: str, port: int):
    from tsccore import tspl
    model = show_reply("~!T model", tspl.MODEL,
                       raw_exchange(host, port, tspl.MODEL))
    print(f"   parsed: {tspl.info_from(model, None, {}).model!r}")
    free = show_reply("~!A free memory", tspl.FREE_MEMORY,
                      raw_exchange(host, port, tspl.FREE_MEMORY))
    print(f"   parsed: {tspl.parse_free(free)!r}  (KB per memory, or bytes)")
    listing = None
    for attempt in (1, 2):
        listing = show_reply(f"~!F file list (asking #{attempt})",
                             tspl.LIST_FILES,
                             raw_exchange(host, port, tspl.LIST_FILES))
        print(f"   parsed: {tspl.parse_file_list(listing)!r}"
              + ("" if tspl.END_OF_LIST in listing
                 else "   (no 0x1A at the end)"))
    show_reply("~!I code page", b'~!I', raw_exchange(host, port, b'~!I'))
    show_reply("<ESC>!? status byte", b'\x1b!?',
               raw_exchange(host, port, b'\x1b!?'))
    request = tspl.build_settings_request()
    settings = show_reply("OUT GETSETTING$ batch", request,
                          raw_exchange(host, port, request, wait=WAIT + 1))
    parsed = tspl.parse_settings(settings)
    print(f"   parsed: {parsed!r}")
    info = tspl.info_from(model, free, parsed)
    print(f"\n== Info: {info}")
    return info


def probe_write(host: str, port: int) -> int:
    from tsccore import fonts, images, tspl
    from tsccore.connection import Connection
    printer = Connection.network(host, port)

    font = fonts.probe_font()
    pattern = images.test_pattern()
    bmp = images.prepare(pattern, pattern.size, images.BMP_1BIT).data
    grey = images.gradient()
    files = [
        # (name, data, memory, what it settles)
        ('PROBE.BMP', bmp, tspl.DRAM, "8.3 capitals, DRAM"),
        ('probe2.bmp', bmp, tspl.DRAM, "lower case"),
        ('PROBELONGNAME.BMP', bmp, tspl.DRAM, "longer than 8.3"),
        ('PROBEF.BMP', bmp, tspl.FLASH, "in flash"),
        ('PROBEG.BMP', images.prepare(grey, grey.size, images.BMP_8BIT).data,
         tspl.DRAM, "8-bit grey"),
        ('PROBE.PNG', images.prepare(pattern, pattern.size, images.PNG).data,
         tspl.DRAM, "PNG"),
    ]
    if font:
        with open(font, 'rb') as f:
            files.insert(0, ('PROBE.TTF', f.read(), tspl.DRAM,
                             f"TrueType ({font})"))
    print("\n== Storing")
    for name, data, memory, why in files:
        tspl.upload(printer, name, data, memory)
        print(f"   {name:18} {len(data):7} bytes to {tspl.MEMORY_NAMES[memory]}"
              f"  ({why})")
    time.sleep(min(1, WAIT))
    for attempt in (1, 2):
        listing = show_reply(f"~!F with the files stored (asking #{attempt})",
                             tspl.LIST_FILES,
                             raw_exchange(host, port, tspl.LIST_FILES))
        print(f"   parsed: {tspl.parse_file_list(listing)!r}")
    show_reply("~!A with the files stored", tspl.FREE_MEMORY,
               raw_exchange(host, port, tspl.FREE_MEMORY))
    request = tspl.build_settings_request()
    show_reply("GETSETTING$ with the files stored", request,
               raw_exchange(host, port, request, wait=WAIT + 1))

    print("\n== Printing three labels")
    if font:
        tspl.test_print(printer, 'PROBE.TTF')
        print("   1: PROBE.TTF test label")
    bmp_label = ["CLS"]
    one_bit = ('PROBE.BMP', 'probe2.bmp', 'PROBELONGNAME.BMP', 'PROBEF.BMP')
    for i, name in enumerate(one_bit):
        x, y = 10 + (i % 2) * 130, 10 + (i // 2) * 100
        bmp_label += [f'TEXT {x},{y},"1",0,1,1,"{name}"',
                      f'PUTBMP {x},{y + 20},"{name}"']
    bmp_label.append("PRINT 1,1")
    printer_label = ("\r\n".join(bmp_label) + "\r\n").encode('ascii')
    from tsccore import connection
    connection.send(printer, printer_label, 15)
    print("   2: the four 1-bit BMPs, two by two: check each prints, the "
          "square is top left and the arrow points right")
    extra = ("\r\n".join([
        "CLS",
        'TEXT 10,10,"1",0,1,1,"PROBEG.BMP bpp 8"',
        'PUTBMP 10,30,"PROBEG.BMP",8,80',
        'TEXT 160,10,"1",0,1,1,"PROBE.PNG"',
        'PUTPNG 160,30,"PROBE.PNG"',
        "PRINT 1,1"]) + "\r\n").encode('ascii')
    connection.send(printer, extra, 15)
    print("   3: the grey BMP (a black-to-white ramp) and the PNG")

    print("\n== Deleting")
    for name, _data, memory, _why in files:
        tspl.delete(printer, name, (memory,))
        print(f"   KILL {name} from {tspl.MEMORY_NAMES[memory]}")
    time.sleep(min(1, WAIT))
    listing = show_reply("~!F after deleting", tspl.LIST_FILES,
                         raw_exchange(host, port, tspl.LIST_FILES))
    print(f"   parsed: {tspl.parse_file_list(listing)!r}")
    return 0


def probe(target: str, write: bool) -> int:
    try:
        host, port = parse_host(target)
    except ValueError:
        print(f"Not HOST[:PORT]: {target}", file=sys.stderr)
        return 1
    try:
        probe_inquiries(host, port)
        if write:
            probe_write(host, port)
    except OSError as e:
        print(f"\nProbe failed: {e}", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    global WAIT
    parser = argparse.ArgumentParser(
        description=__doc__.strip().split('\n')[0])
    parser.add_argument('--probe', metavar='HOST[:PORT]',
                        help="ask a networked TSC printer (port 9100 unless "
                             "given) everything the app relies on, print the "
                             "raw replies, and exit")
    parser.add_argument('--probe-write', action='store_true',
                        help="with --probe: also store test files in DRAM "
                             "and flash, print three test labels, then "
                             "delete the files again")
    parser.add_argument('--probe-wait', metavar='SECONDS', type=float,
                        default=WAIT,
                        help="with --probe: how long to listen for each "
                             f"answer (default {WAIT:g})")
    args = parser.parse_args()
    WAIT = args.probe_wait
    if args.probe:
        return probe(args.probe, args.probe_write)
    if args.probe_write:
        parser.error("--probe-write needs --probe")
    parser.print_help()
    return 0


if __name__ == '__main__':
    sys.exit(main())

"""The transport copied from LinuxZPL: a network printer or a USB one.

Adapted from the checks in LinuxZPL's tests/test_core.py. A local TCP
listener stands in for a network printer, a FIFO for a USB node that only
takes bytes, and a pty for one that answers.
"""
import configparser
import errno
import os
import pty
import socket
import tempfile
import threading
import time
import tty
from pathlib import Path

from _check import check, finish

from tsccore import connection, local_port, printer_io
from tsccore.connection import Connection


def listener(received, reply=b''):
    """A one-connection TCP printer: records what it is sent, and answers
    `reply` once something has arrived."""
    srv = socket.socket()
    srv.bind(('127.0.0.1', 0))
    srv.listen(1)

    def serve():
        conn, _ = srv.accept()
        conn.settimeout(3)
        try:
            while True:
                data = conn.recv(65536)
                if not data:
                    break
                received.append(data)
                if reply:
                    conn.sendall(reply)
        except OSError:
            pass
        conn.close()
        srv.close()
    th = threading.Thread(target=serve, daemon=True)
    th.start()
    return srv.getsockname()[1], th


def fifo_reader(fifo, received):
    def drain():
        with open(fifo, 'rb') as f:
            while True:
                data = f.read(4096)
                if not data:
                    break
                received.append(data)
    th = threading.Thread(target=drain, daemon=True)
    th.start()
    return th


# --- Connection: what the user chose --------------------------------------
net = Connection.network('192.168.1.50', 9100)
usb = Connection.usb('A1B2C3', 'TSC TE210')
check("Connection.where(): an address and port, or the USB printer's name",
      (net.where(), net.where(with_port=False), usb.where(),
       Connection.usb('SN9').where())
      == ('192.168.1.50:9100', '192.168.1.50', 'TSC TE210 (USB)',
          'USB printer SN9'))
both = net.as_usb('A1B2C3', 'TSC TE210')
check("choosing USB keeps the network address, and back again keeps the USB "
      "printer", both.is_usb and both.address == '192.168.1.50'
      and both.as_network('10.0.0.2', 9200).usb_serial == 'A1B2C3'
      and not both.as_network('10.0.0.2', 9200).is_usb)
check("Connection.key(): only the chosen half says which printer it is",
      both.key() == usb.key() != net.key())


def round_trip(printer):
    parser = configparser.ConfigParser()
    parser.read_string("[printer]\nother = kept\nusb_serial = OLD\n")
    printer.write(parser)
    return Connection.read(parser, Connection()), dict(parser['printer'])


back_net, keys_net = round_trip(net)
back_usb, keys_usb = round_trip(both)
check("Connection.write/read: each kind comes back as it went, beside the "
      "section's other keys",
      back_net == net and back_usb == both and keys_net['other'] == 'kept'
      and 'usb_serial' not in keys_net and keys_usb['connection'] == 'usb',
      (keys_net, keys_usb))

# --- finding USB printers ---------------------------------------------------
with tempfile.TemporaryDirectory() as d:
    root = Path(d)
    (root / 'dev' / 'usb').mkdir(parents=True)
    for name, device_id, serial in (
            ('lp1', 'MFG:Brother;MDL:HL-2140 series;', None),
            ('lp2', 'MFG:TSC;MDL:TE210;', 'A1B2C3\n')):
        (root / 'dev' / 'usb' / name).touch()
        dev = root / 'sys' / 'class' / 'usbmisc' / name / 'device'
        dev.mkdir(parents=True)
        (dev / 'ieee1284_id').write_text(device_id)
        if serial:
            (dev.parent / 'serial').write_text(serial)
    found = local_port.list_printers(str(root / 'dev'), str(root / 'sys'))
    check("list_printers: each node's description and serial number",
          [(Path(f.path).name, f.description, f.serial) for f in found]
          == [('lp1', 'Brother HL-2140 series', ''),
              ('lp2', 'TSC TE210', 'A1B2C3')], found)

real_list, real_detached = local_port.list_printers, local_port.list_detached
present, detached = [], []
local_port.list_printers = lambda *a: list(present)
local_port.list_detached = lambda *a: list(detached)
try:
    present[:] = [local_port.UsbPrinter('/dev/usb/lp1', 'TSC TE210', 'OTHER'),
                  local_port.UsbPrinter('/dev/usb/lp3', 'TSC TE210', 'A1B2C3')]
    check("resolve: a USB printer is found by its serial number, not by a "
          "same-model neighbour",
          connection.resolve(usb) == local_port.LocalPort('/dev/usb/lp3'))
    check("usb_choices: each printer named with its node, the one in use "
          "selected", connection.usb_choices(both)
          == ([('TSC TE210 (lp1)', Connection.usb('OTHER', 'TSC TE210')),
               ('TSC TE210 (lp3)', usb)], 1))
    present[:] = []
    try:
        connection.resolve(usb)
        outcome = 'returned'
    except connection.PortProblem as e:
        outcome = (e.errno, str(e))
    check("resolve: one not plugged in is a PortProblem saying so",
          outcome == (errno.ENODEV, "TSC TE210 (serial number A1B2C3) is not "
                      "connected by USB."), outcome)
    check("usb_choices: with none at all, one entry says so and carries None",
          connection.usb_choices(net) == ([(connection.NO_USB_PRINTERS,
                                            None)], 0))
finally:
    local_port.list_printers = real_list

# --- sending ----------------------------------------------------------------
got = []
port, th = listener(got)
connection.send(Connection.network('127.0.0.1', port), b'CLS\r\n', 5)
th.join(3)
check("connection.send: a network printer gets the payload over TCP",
      b''.join(got) == b'CLS\r\n', got)

got = []
port, th = listener(got, reply=b'TE210\r')
answer = connection.send(Connection.network('127.0.0.1', port), b'~!T', 3,
                         read_reply=True)
check("connection.send with read_reply: the answer comes back, ending on "
      "the quiet after it", answer == b'TE210\r' and got == [b'~!T'],
      (answer, got))

blob = bytes(range(256)) * 300
got, progress = [], []
port, th = listener(got)
connection.send_stream(Connection.network('127.0.0.1', port),
                       (blob[i:i + 16384] for i in range(0, len(blob), 16384)),
                       len(blob), 5, progress=lambda a, b: progress.append((a, b)))
th.join(3)
check("send_stream: the bytes arrive whole and progress rises to the total",
      b''.join(got) == blob and progress[-1] == (len(blob), len(blob))
      and len(progress) > 1)

token = printer_io.CancelToken()
token.cancel()
try:
    printer_io.send('127.0.0.1', 9, b'x', 1, cancel=token)
    outcome = 'returned'
except printer_io.Cancelled:
    outcome = 'Cancelled'
check("a send given a cancelled token raises Cancelled, not OSError",
      outcome == 'Cancelled', outcome)

with tempfile.TemporaryDirectory() as d:
    fifo = Path(d) / 'lp7'
    os.mkfifo(fifo)
    local_port.list_printers = lambda *a: [
        local_port.UsbPrinter(str(fifo), 'TSC TE210', 'A1B2C3')]
    try:
        got = []
        th = fifo_reader(fifo, got)
        connection.send(usb, b'PRINT 1\r\n', 5)
        th.join(3)
        check("connection.send: a USB printer gets it down the node its "
              "serial number has", b''.join(got) == b'PRINT 1\r\n', got)

        class Busy:
            def __init__(self, refusals):
                self.refusals = refusals

            def __getattr__(self, name):
                return getattr(os, name)

            def open(self, *args, **kwargs):
                if self.refusals:
                    self.refusals -= 1
                    raise OSError(errno.EBUSY, 'Device or resource busy')
                return os.open(*args, **kwargs)

        local_port.os = Busy(2)
        got = []
        th = fifo_reader(fifo, got)
        t0 = time.monotonic()
        try:
            connection.send(usb, b'after', 5)
        finally:
            local_port.os = os
        th.join(3)
        check("a node another program holds is waited for, then sent to",
              b''.join(got) == b'after'
              and time.monotonic() - t0 >= 2 * local_port.TICK)
    finally:
        local_port.list_printers = real_list

# A late reply waits on the node for whoever opens it next; it is thrown away
# rather than read as the start of this request's answer.
master, slave = pty.openpty()
tty.setraw(slave)
os.write(master, b'late end of an earlier reply\r\x1a')
heard = []


def answer_model():
    heard.append(os.read(master, 64))
    os.write(master, b'TE210\r')


th = threading.Thread(target=answer_model, daemon=True)
th.start()
local_port.list_printers = lambda *a: [
    local_port.UsbPrinter(os.ttyname(slave), 'TSC TE210', 'A1B2C3')]
try:
    reply = connection.send(usb, b'~!T', 2, read_reply=True)
finally:
    local_port.list_printers = real_list
    local_port.list_detached = real_detached
th.join(3)
os.close(master)
os.close(slave)
check("over USB, a reply left from an earlier request is not read as this "
      "one's", heard == [b'~!T'] and reply == b'TE210\r', (heard, reply))

finish()

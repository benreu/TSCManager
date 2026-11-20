"""
A pretend TSC printer on a local TCP port, answering TSPL the way the
manual describes it: enough for the tests to store, list, delete and print
without a printer.

It keeps its files per memory, and records every label it is asked to
print. Its replies copy a TSC MB241's (firmware 1.28.002), as the probe
recorded them on 2026-11-20: ~!F lists DRAM then flash with nothing to say
which is which, ~!A gives a line per memory, and memory is counted in KB,
a file taking whole 4 KB blocks.
"""

import re
import socket
import threading

_DOWNLOAD = re.compile(rb'DOWNLOAD (F,|E,)?"([^"]*)",(\d+),')
_KILL = re.compile(rb'KILL (F,|E,)?\s*"([^"]*)"')
_SETTING = re.compile(rb'OUT "([^"]*)";GETSETTING\$\("([^"]*)","([^"]*)","([^"]*)"\)')
_MEMORY = {None: 'dram', b'F,': 'flash', b'E,': 'card'}


class FakePrinter:
    def __init__(self, model='MB241', version='1.28.002', dpi=203,
                 card=False, answers=True):
        self.model, self.version, self.dpi = model, version, dpi
        self.card = card
        self.answers = answers          # False: takes everything, says nothing
        self.files = {'dram': {}, 'flash': {}, 'card': {}}
        self.labels = []                # each a list of command lines
        self.received = []              # every command, in order
        self._label = []
        self._srv = socket.socket()
        self._srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._srv.bind(('127.0.0.1', 0))
        self._srv.listen(5)
        self.port = self._srv.getsockname()[1]
        self._stop = False
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def close(self):
        self._stop = True
        try:
            socket.create_connection(('127.0.0.1', self.port), 1).close()
        except OSError:
            pass
        self._thread.join(2)
        self._srv.close()

    def all_names(self):
        with self._lock:
            return [n for memory in ('dram', 'flash', 'card')
                    for n in self.files[memory]]

    # --- the conversation ---------------------------------------------

    def _serve(self):
        while not self._stop:
            try:
                conn, _ = self._srv.accept()
            except OSError:
                return
            if self._stop:
                conn.close()
                return
            conn.settimeout(0.3)
            buf = b''
            try:
                while True:
                    try:
                        data = conn.recv(65536)
                    except (socket.timeout, TimeoutError):
                        continue
                    if not data:
                        break
                    buf += data
                    buf = self._consume(buf, conn)
            except OSError:
                pass
            conn.close()

    def _reply(self, conn, data: bytes):
        if self.answers:
            conn.sendall(data)

    def _consume(self, buf: bytes, conn) -> bytes:
        while buf:
            if buf.startswith((b'~!', b'\x1b!')):
                if len(buf) < 3:
                    return buf
                command, buf = buf[:3], buf[3:]
                self._immediate(command, conn)
                continue
            if buf.startswith(b'DOWNLOAD'):
                found = _DOWNLOAD.match(buf)
                if not found:
                    if b'\r\n' in buf:      # not a data file: ignore the line
                        buf = buf.split(b'\r\n', 1)[1]
                        continue
                    return buf
                size = int(found.group(3))
                start = found.end()
                if len(buf) < start + size:
                    return buf
                memory = _MEMORY[found.group(1)]
                name = found.group(2).decode('latin-1')
                with self._lock:
                    self.files[memory][name] = buf[start:start + size]
                    self.received.append(f'DOWNLOAD {memory} {name}')
                buf = buf[start + size:]
                continue
            if b'\r\n' not in buf:
                return buf
            line, buf = buf.split(b'\r\n', 1)
            self._line(line, conn)
        return buf

    def _immediate(self, command: bytes, conn):
        with self._lock:
            self.received.append(command.decode('latin-1'))
            if command == b'~!T':
                self._reply(conn, self.model.encode())   # no CR, as the MB241
            elif command == b'~!A':
                self._reply(conn, f"DRAM:{self._available('DRAM')}\r"
                            f"FLASH:{self._available('FLASH')}\r".encode())
            elif command == b'~!F':
                names = b''.join(n.encode('latin-1') + b'\r'
                                 for memory in ('dram', 'flash', 'card')
                                 for n in self.files[memory])
                self._reply(conn, names + b'\x1a')
            elif command == b'\x1b!?':
                self._reply(conn, b'\x00')

    SIZES_KB = {'DRAM': 8192, 'FLASH': 212352, 'CARD': 0}

    def _capacity(self, sec):
        return 31000 if sec == 'CARD' and self.card else self.SIZES_KB[sec]

    def _available(self, sec):
        used = sum(-(-len(d) // 4096) * 4
                   for d in self.files[sec.lower()].values())
        return self._capacity(sec) - used

    def _setting(self, app, sec, key):
        if app == 'SYSTEM':
            return {'MODEL': self.model, 'VERSION': self.version,
                    'DPI': str(self.dpi), 'SERIAL': 'FAKE123'}.get(key, '')
        if key == 'INSTALLED':
            return '1' if self.card else '0'
        if key == 'CAPACITY':
            return str(self._capacity(sec))
        if key == 'AVAILABLE':
            return str(self._available(sec))
        return ''

    def _line(self, line: bytes, conn):
        text = line.decode('latin-1')
        with self._lock:
            self.received.append(text)
            setting = _SETTING.match(line)
            if setting:
                tag, app, sec, key = (g.decode() for g in setting.groups())
                self._reply(conn, f"{tag}{self._setting(app, sec, key)}\r\n"
                            .encode())
                return
            killed = _KILL.match(line)
            if killed:
                memory = _MEMORY[killed.group(1)]
                pattern = killed.group(2).decode('latin-1').strip()
                for name in list(self.files[memory]):
                    if pattern == '*' or name == pattern:
                        del self.files[memory][name]
                return
            if text == 'MOVE':
                self.files['flash'].update(self.files['dram'])
                self.files['dram'].clear()
                return
            if text == 'CLS':
                self._label = []
            self._label.append(text)
            if text.startswith('PRINT'):
                self.labels.append(self._label)
                self._label = []

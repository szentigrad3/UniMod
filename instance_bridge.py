"""Per-user, single-window local NXM forwarding (Linux only).

URLs are delivered only over an owner-only AF_UNIX socket, never written to
logs/config/lock files. The server verifies SO_PEERCRED and passes messages
into a thread-safe queue; the Tk thread alone handles GUI updates.
"""
import fcntl
import json
import os
from pathlib import Path
import queue
import socket
import stat
import struct
import threading
import time

from nexus_integration import parse_nxm_link

MAX_BYTES = 4096


def private_directory(base=None):
    if base is None:
        candidate = Path(os.environ.get('XDG_RUNTIME_DIR', '')) if os.environ.get('XDG_RUNTIME_DIR') else None
        if candidate and candidate.is_dir() and candidate.stat().st_uid == os.getuid():
            base = candidate / 'unimod'
        else:
            base = Path.home() / '.cache' / 'unimod' / 'runtime'
    folder = Path(base).expanduser()
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    info = folder.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
        raise PermissionError('UniMod runtime directory must belong to the current user')
    folder.chmod(0o700)
    return folder


def _peer_uid(connection):
    if not hasattr(socket, 'SO_PEERCRED'):
        raise RuntimeError('Peer credentials unavailable on this platform')
    credentials = connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize('3i'))
    return struct.unpack('3i', credentials)[1]


def send_to_running(folder, uri=None, timeout=3.5):
    if uri is not None:
        parse_nxm_link(uri)
    payload = json.dumps({'action': 'nxm' if uri is not None else 'present', 'uri': uri}).encode()
    if len(payload) > MAX_BYTES:
        raise ValueError('Nexus link is too long')
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(0.5)
                client.connect(str(Path(folder) / 'instance.sock'))
                if _peer_uid(client) != os.getuid():
                    raise PermissionError('UniMod instance belongs to another user')
                client.sendall(payload + b'\n')
                reply = client.recv(128)
                if reply == b'OK\n':
                    return True
                if reply == b'INVALID\n':
                    raise ValueError('Invalid Nexus link')
        except (FileNotFoundError, ConnectionRefusedError, socket.timeout, BrokenPipeError):
            pass
        time.sleep(0.06)
    return False


class SingleInstance:
    def __init__(self, base=None):
        self.folder = private_directory(base)
        self.sockpath = self.folder / 'instance.sock'
        self.events = queue.Queue()
        self.sock = None
        self.lock_fd = None
        self._closed = threading.Event()

    def acquire(self):
        if self.lock_fd is not None:
            return True
        flags = os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0)
        fd = os.open(self.folder / 'instance.lock', flags, 0o600)
        try:
            if os.fstat(fd).st_uid != os.getuid():
                raise PermissionError('Invalid UniMod lock owner')
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                os.close(fd)
                return False
        except Exception:
            try: os.close(fd)
            except OSError: pass
            raise
        self.lock_fd = fd
        return True

    def start(self):
        if self.lock_fd is None:
            raise RuntimeError('Instance lock must be acquired first')
        # Only the instance holding the lock may unlink a stale socket.
        self.sockpath.unlink(missing_ok=True)
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            self.sock.bind(str(self.sockpath))
            self.sockpath.chmod(0o600)
            self.sock.listen(16)
            self.sock.settimeout(0.25)
        except Exception:
            self.close()
            raise
        threading.Thread(target=self._listen, name='unimod-link-receiver', daemon=True).start()

    def _listen(self):
        while not self._closed.is_set():
            try:
                connection, _ = self.sock.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            with connection:
                try:
                    connection.settimeout(2)
                    if _peer_uid(connection) != os.getuid():
                        continue
                    buf = bytearray()
                    while len(buf) < MAX_BYTES + 1 and b'\n' not in buf:
                        piece = connection.recv(min(512, MAX_BYTES + 1 - len(buf)))
                        if not piece: break
                        buf.extend(piece)
                    if len(buf) > MAX_BYTES or not buf.endswith(b'\n'):
                        connection.sendall(b'INVALID\n')
                        continue
                    data = json.loads(buf[:-1].decode('utf-8'))
                    if not isinstance(data, dict):
                        raise ValueError('Invalid message')
                    if data.get('action') == 'present' and data.get('uri') is None:
                        action = ('present', None)
                    elif data.get('action') == 'nxm':
                        parse_nxm_link(data.get('uri'))
                        action = ('nxm', data['uri'])
                    else:
                        raise ValueError('Invalid message')
                    self.events.put(action)
                    connection.sendall(b'OK\n')
                except (ValueError, UnicodeError, json.JSONDecodeError, TypeError):
                    try: connection.sendall(b'INVALID\n')
                    except OSError: pass
                except OSError:
                    continue

    def close(self):
        self._closed.set()
        if self.sock is not None:
            try: self.sock.close()
            except OSError: pass
            self.sock = None
        if self.lock_fd is not None:
            self.sockpath.unlink(missing_ok=True)
            fcntl.flock(self.lock_fd, fcntl.LOCK_UN)
            os.close(self.lock_fd)
            self.lock_fd = None

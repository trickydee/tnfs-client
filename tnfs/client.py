"""TNFS client session implementation."""

from __future__ import annotations

import socket
import struct
import threading
from dataclasses import dataclass
from typing import Optional

from tnfs.protocol import (
    CMD_CLOSE,
    CMD_CLOSEDIR,
    CMD_FREE,
    CMD_MKDIR,
    CMD_MOUNT,
    CMD_OPEN,
    CMD_OPENDIR,
    CMD_READ,
    CMD_READDIR,
    CMD_RMDIR,
    CMD_SIZE,
    CMD_STAT,
    CMD_UMOUNT,
    CMD_UNLINK,
    CMD_WRITE,
    MAX_READ_TCP,
    MAX_READ_UDP,
    MAX_WRITE_UDP,
    O_CREAT,
    O_RDONLY,
    O_TRUNC,
    O_WRONLY,
    S_IFDIR,
    S_IFMT,
    S_IFREG,
    TNFS_EOF,
    TNFS_PORT,
    close_request,
    closedir_request,
    mount_request,
    normalize_path,
    opendir_request,
    open_request,
    pack_header,
    path_request,
    read_cstr,
    read_request,
    readdir_request,
    write_request,
)


class TNFSError(Exception):
    """TNFS protocol error."""

    def __init__(self, code: int, message: str = ""):
        self.code = code
        super().__init__(message or f"TNFS error 0x{code:02X}")


@dataclass
class DirEntry:
    name: str
    is_dir: bool = False
    size: int = 0
    mtime: int = 0


@dataclass
class FileStat:
    mode: int
    uid: int
    gid: int
    size: int
    atime: int
    mtime: int
    ctime: int

    @property
    def is_dir(self) -> bool:
        return (self.mode & S_IFMT) == S_IFDIR

    @property
    def is_file(self) -> bool:
        return (self.mode & S_IFMT) == S_IFREG

    @property
    def permissions(self) -> int:
        return self.mode & 0o7777


class TNFSClient:
    """Client for a TNFS server over UDP or TCP."""

    def __init__(
        self,
        host: str,
        port: int = TNFS_PORT,
        transport: Optional[str] = None,
        mount_path: str = "/",
        timeout: float = 30.0,
    ):
        self.host = host
        self.port = port
        self.mount_path = mount_path
        self.timeout = timeout
        self.session_id: Optional[int] = None
        self.sequence = 0
        self._lock = threading.Lock()
        self.version: Optional[str] = None
        self._sock: Optional[socket.socket] = None
        self._address: Optional[tuple[str, int]] = None
        self.transport = self._connect(transport)

    @property
    def max_read_size(self) -> int:
        return MAX_READ_UDP if self.transport == "udp" else MAX_READ_TCP

    @property
    def max_write_size(self) -> int:
        return MAX_WRITE_UDP

    def _connect(self, transport: Optional[str]) -> str:
        if transport in (None, "tcp"):
            try:
                return self._open_tcp()
            except OSError:
                if transport == "tcp":
                    raise
        return self._open_udp()

    def _open_tcp(self) -> str:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        sock.connect((self.host, self.port))
        self._sock = sock
        self._address = (self.host, self.port)
        self.transport = "tcp"
        self._mount()
        return "tcp"

    def _open_udp(self) -> str:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(self.timeout)
        resolved = socket.gethostbyname(self.host)
        self._sock = sock
        self._address = (resolved, self.port)
        self.transport = "udp"
        self._mount()
        return "udp"

    def close(self) -> None:
        if self.session_id is not None and self._sock is not None:
            try:
                self._exchange(CMD_UMOUNT, b"")
            except OSError:
                pass
            self.session_id = None
        if self._sock is not None:
            self._sock.close()
            self._sock = None

    def __enter__(self) -> "TNFSClient":
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def _exchange(self, command: int, payload: bytes) -> bytes:
        if self._sock is None or self._address is None:
            raise RuntimeError("Not connected")

        with self._lock:
            conn_id = self.session_id or 0
            packet = pack_header(conn_id, self.sequence, command) + payload
            seq = self.sequence
            self.sequence = (self.sequence + 1) % 256

            if self.transport == "tcp":
                self._sock.sendall(packet)
                data = self._recv_tcp()
            else:
                self._sock.sendto(packet, self._address)
                data, _ = self._sock.recvfrom(65535)

        resp_conn, resp_seq, resp_cmd = struct.unpack("<HBB", data[:4])
        if resp_seq != seq:
            raise TNFSError(0xFF, f"Sequence mismatch: expected {seq}, got {resp_seq}")
        if resp_cmd != command:
            raise TNFSError(0xFF, f"Command mismatch: expected 0x{command:02X}, got 0x{resp_cmd:02X}")

        if command == CMD_MOUNT and struct.unpack("B", data[4:5])[0] == 0:
            self.session_id = resp_conn

        return data

    def _recv_tcp(self) -> bytes:
        assert self._sock is not None
        chunks = []
        while True:
            chunk = self._sock.recv(65535)
            if not chunk:
                break
            chunks.append(chunk)
            if len(chunk) < 65535:
                break
        return b"".join(chunks)

    def _status(self, data: bytes, context: str) -> int:
        status = data[4]
        if status != 0:
            raise TNFSError(status, context)
        return status

    def _mount(self) -> None:
        data = self._exchange(CMD_MOUNT, mount_request(self.mount_path))
        self._status(data, f"Mount failed for {self.mount_path!r}")
        ver_min, ver_maj = struct.unpack("BB", data[5:7])
        self.version = f"{ver_maj}.{ver_min}"

    def listdir(self, path: str = "/") -> list[DirEntry]:
        """List directory contents at the given absolute path."""
        path = normalize_path(path)
        data = self._exchange(CMD_OPENDIR, opendir_request(path))
        self._status(data, f"OPENDIR failed for {path!r}")
        handle = data[5]
        entries: list[DirEntry] = []

        try:
            while True:
                data = self._exchange(CMD_READDIR, readdir_request(handle))
                status = data[4]
                if status == TNFS_EOF:
                    break
                if status != 0:
                    raise TNFSError(status, f"READDIR failed for {path!r}")

                name, _ = read_cstr(data, 5)
                if name is None:
                    break
                entries.append(DirEntry(name=name))
        finally:
            self._exchange(CMD_CLOSEDIR, closedir_request(handle))

        return entries

    def stat(self, path: str) -> FileStat:
        """Return metadata for a remote file or directory."""
        path = normalize_path(path)
        data = self._exchange(CMD_STAT, path_request(path))
        self._status(data, f"STAT failed for {path!r}")
        mode, uid, gid, size, atime, mtime, ctime = struct.unpack("<HHHIIII", data[5:27])
        return FileStat(
            mode=mode,
            uid=uid,
            gid=gid,
            size=size,
            atime=atime,
            mtime=mtime,
            ctime=ctime,
        )

    def open_file(self, path: str, flags: int = O_RDONLY, mode: int = 0o644) -> int:
        """Open a remote file and return its file descriptor."""
        path = normalize_path(path)
        data = self._exchange(CMD_OPEN, open_request(path, flags, mode))
        self._status(data, f"OPEN failed for {path!r}")
        return data[5]

    def close_file(self, fd: int) -> None:
        data = self._exchange(CMD_CLOSE, close_request(fd))
        self._status(data, f"CLOSE failed for fd {fd}")

    def read_file(self, path: str) -> bytes:
        """Read the full contents of a remote file."""
        path = normalize_path(path)
        fd = self.open_file(path, O_RDONLY)
        chunks: list[bytes] = []
        try:
            while True:
                data = self._exchange(CMD_READ, read_request(fd, self.max_read_size))
                status = data[4]
                if status == TNFS_EOF:
                    break
                if status != 0:
                    raise TNFSError(status, f"READ failed for {path!r}")
                nbytes = struct.unpack("<H", data[5:7])[0]
                chunks.append(data[7 : 7 + nbytes])
                if nbytes == 0:
                    break
        finally:
            self.close_file(fd)
        return b"".join(chunks)

    def write_file(self, path: str, content: bytes, mode: int = 0o644) -> int:
        """Write content to a remote file, creating or truncating it."""
        path = normalize_path(path)
        fd = self.open_file(path, O_WRONLY | O_CREAT | O_TRUNC, mode)
        written = 0
        try:
            offset = 0
            while offset < len(content):
                chunk = content[offset : offset + self.max_write_size]
                data = self._exchange(CMD_WRITE, write_request(fd, chunk))
                self._status(data, f"WRITE failed for {path!r}")
                nbytes = struct.unpack("<H", data[5:7])[0]
                written += nbytes
                offset += nbytes
                if nbytes == 0:
                    break
        finally:
            self.close_file(fd)
        return written

    def mkdir(self, path: str) -> None:
        path = normalize_path(path)
        data = self._exchange(CMD_MKDIR, path_request(path))
        self._status(data, f"MKDIR failed for {path!r}")

    def rmdir(self, path: str) -> None:
        path = normalize_path(path)
        data = self._exchange(CMD_RMDIR, path_request(path))
        self._status(data, f"RMDIR failed for {path!r}")

    def unlink(self, path: str) -> None:
        path = normalize_path(path)
        data = self._exchange(CMD_UNLINK, path_request(path))
        self._status(data, f"UNLINK failed for {path!r}")

    def filesystem_size(self) -> int:
        data = self._exchange(CMD_SIZE, b"")
        self._status(data, "SIZE failed")
        return struct.unpack("<I", data[5:9])[0]

    def filesystem_free(self) -> int:
        data = self._exchange(CMD_FREE, b"")
        self._status(data, "FREE failed")
        return struct.unpack("<I", data[5:9])[0]

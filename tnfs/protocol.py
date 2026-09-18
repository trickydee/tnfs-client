"""TNFS wire protocol constants and helpers."""

from __future__ import annotations

import struct

TNFS_PORT = 16384
TNFS_VERSION = (1, 2)
MAX_READ_UDP = 512
MAX_WRITE_UDP = 512
MAX_READ_TCP = 32768

# Command IDs
CMD_MOUNT = 0x00
CMD_UMOUNT = 0x01
CMD_OPENDIR = 0x10
CMD_READDIR = 0x11
CMD_CLOSEDIR = 0x12
CMD_MKDIR = 0x13
CMD_RMDIR = 0x14
CMD_OPENDIRX = 0x17
CMD_READDIRX = 0x18
CMD_READ = 0x21
CMD_WRITE = 0x22
CMD_CLOSE = 0x23
CMD_STAT = 0x24
CMD_UNLINK = 0x26
CMD_OPEN = 0x29
CMD_SIZE = 0x30
CMD_FREE = 0x31

# Error codes
TNFS_EOF = 0x21

# OPEN flags
O_RDONLY = 0x0001
O_WRONLY = 0x0002
O_RDWR = 0x0003
O_CREAT = 0x0100
O_TRUNC = 0x0200

# POSIX file type bits
S_IFMT = 0o170000
S_IFDIR = 0o040000
S_IFREG = 0o100000

# READDIRX flags
DIRENTRY_DIR = 0x01
DIRENTRY_HIDDEN = 0x02
DIRENTRY_SPECIAL = 0x04
DIRSTATUS_EOF = 0x01


def pack_header(conn_id: int, seq: int, command: int) -> bytes:
    return struct.pack("<HBB", conn_id, seq & 0xFF, command)


def parse_header(data: bytes) -> tuple[int, int, int]:
    return struct.unpack("<HBB", data[:4])


def read_cstr(data: bytes, offset: int = 0) -> tuple[str | None, int]:
    end = data.find(b"\0", offset)
    if end == -1:
        return None, offset
    return data[offset:end].decode("utf-8", errors="replace"), end + 1


def normalize_path(path: str) -> str:
    path = path.replace("\\", "/")
    if not path.startswith("/"):
        path = "/" + path
    parts: list[str] = []
    for part in path.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    return "/" + "/".join(parts) if parts else "/"


def mount_request(path: str, user: str = "", password: str = "") -> bytes:
    ver_min, ver_maj = TNFS_VERSION
    body = struct.pack("BB", ver_min, ver_maj)
    body += path.encode("utf-8") + b"\0"
    body += user.encode("utf-8") + b"\0"
    body += password.encode("utf-8") + b"\0"
    return body


def path_request(path: str) -> bytes:
    return path.encode("utf-8") + b"\0"


def opendir_request(path: str) -> bytes:
    return path_request(path)


def readdir_request(handle: int) -> bytes:
    return struct.pack("B", handle)


def closedir_request(handle: int) -> bytes:
    return struct.pack("B", handle)


def open_request(path: str, flags: int, mode: int = 0o644) -> bytes:
    return struct.pack("<HH", flags, mode) + path_request(path)


def read_request(fd: int, size: int) -> bytes:
    return struct.pack("<BH", fd, size)


def write_request(fd: int, data: bytes) -> bytes:
    return struct.pack("<BH", fd, len(data)) + data


def close_request(fd: int) -> bytes:
    return struct.pack("B", fd)

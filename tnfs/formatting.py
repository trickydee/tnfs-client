"""Shared formatting helpers."""

from __future__ import annotations

import datetime

from tnfs.client import FileStat, TNFSClient, TNFSError
from tnfs.protocol import normalize_path


def format_size(size: int) -> str:
    if size < 1024:
        return str(size)
    if size < 1024 * 1024:
        return f"{size / 1024:.1f}K"
    if size < 1024 * 1024 * 1024:
        return f"{size / (1024 * 1024):.1f}M"
    return f"{size / (1024 * 1024 * 1024):.1f}G"


def format_mtime(timestamp: int) -> str:
    if not timestamp:
        return ""
    return datetime.datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")


def format_stat(info: FileStat, path: str) -> str:
    kind = "directory" if info.is_dir else "file" if info.is_file else "other"
    lines = [
        f"Path:        {path}",
        f"Type:        {kind}",
        f"Size:        {info.size} ({format_size(info.size)})",
        f"Mode:        {info.permissions:04o}",
        f"UID/GID:     {info.uid}/{info.gid}",
    ]
    if info.mtime:
        lines.append(f"Modified:    {datetime.datetime.fromtimestamp(info.mtime)}")
    if info.atime:
        lines.append(f"Accessed:    {datetime.datetime.fromtimestamp(info.atime)}")
    return "\n".join(lines)


def print_listing(
    client: TNFSClient,
    path: str,
    *,
    long: bool = False,
) -> None:
    entries = client.listdir(path)
    names = sorted((entry.name for entry in entries), key=str.lower)

    if not long:
        for name in names:
            print(name)
        return

    for name in names:
        if name in (".", ".."):
            print(f"{'d':>1} {'':>8}  {'':16}  {name}")
            continue
        child_path = normalize_path(f"{path.rstrip('/')}/{name}")
        try:
            info = client.stat(child_path)
            kind = "d" if info.is_dir else "-"
            print(f"{kind} {format_size(info.size):>8}  {format_mtime(info.mtime):>16}  {name}")
        except TNFSError:
            print(f"? {'?':>8}  {'':16}  {name}")

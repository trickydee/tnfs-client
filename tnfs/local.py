"""Local filesystem helpers for the TUI."""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class LocalEntry:
    name: str
    path: Path
    is_dir: bool
    size: int = 0
    mtime: float = 0.0


class LocalBrowser:
    """Navigate a directory on the local machine."""

    def __init__(self, start_dir: Path | None = None):
        self.cwd = (start_dir or Path.cwd()).resolve()

    def resolve(self, path: str | Path) -> Path:
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = self.cwd / candidate
        return candidate.resolve()

    def chdir(self, path: str | Path) -> Path:
        target = self.resolve(path)
        if not target.is_dir():
            raise NotADirectoryError(f"Not a directory: {target}")
        self.cwd = target
        return self.cwd

    def parent_dir(self) -> Path:
        parent = self.cwd.parent
        return parent if parent != self.cwd else self.cwd

    def list_entries(self) -> list[LocalEntry]:
        entries: list[LocalEntry] = []
        try:
            children = list(self.cwd.iterdir())
        except OSError:
            return entries

        for child in sorted(children, key=lambda p: p.name.lower()):
            try:
                stat = child.stat()
            except OSError:
                entries.append(LocalEntry(name=child.name, path=child, is_dir=child.is_dir()))
                continue

            entries.append(
                LocalEntry(
                    name=child.name,
                    path=child,
                    is_dir=child.is_dir(),
                    size=stat.st_size if child.is_file() else 0,
                    mtime=stat.st_mtime,
                )
            )

        entries.sort(key=lambda entry: (not entry.is_dir, entry.name.lower()))
        return entries

    def format_details(self, entry: LocalEntry) -> str:
        kind = "directory" if entry.is_dir else "file"
        lines = [
            f"Path:        {entry.path}",
            f"Type:        {kind}",
            f"Size:        {entry.size} bytes",
        ]
        if entry.mtime:
            lines.append(f"Modified:    {datetime.fromtimestamp(entry.mtime)}")
        return "\n".join(lines)

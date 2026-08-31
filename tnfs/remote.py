"""Remote filesystem session with working-directory tracking."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tnfs.client import FileStat, TNFSClient, TNFSError
from tnfs.protocol import normalize_path


@dataclass
class RemoteEntry:
    name: str
    path: str
    is_dir: bool
    size: int = 0
    mtime: int = 0


class RemoteSession:
    """Stateful wrapper around a TNFS client connection."""

    def __init__(
        self,
        host: str,
        port: int = 16384,
        transport: str | None = None,
        mount_path: str = "/",
        timeout: float = 30.0,
    ):
        self.host = host
        self.port = port
        self.mount_path = mount_path
        self.client = TNFSClient(
            host=host,
            port=port,
            transport=transport,
            mount_path=mount_path,
            timeout=timeout,
        )
        self.cwd = "/"

    @property
    def version(self) -> str | None:
        return self.client.version

    @property
    def transport(self) -> str:
        return self.client.transport

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "RemoteSession":
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def resolve(self, path: str) -> str:
        path = path.strip()
        if not path or path == ".":
            return self.cwd
        if path.startswith("/"):
            return normalize_path(path)
        return normalize_path(f"{self.cwd.rstrip('/')}/{path}")

    def chdir(self, path: str) -> str:
        target = self.resolve(path)
        info = self.client.stat(target)
        if not info.is_dir:
            raise TNFSError(0xFF, f"Not a directory: {target}")
        self.cwd = target
        return self.cwd

    def parent_dir(self) -> str:
        if self.cwd == "/":
            return "/"
        parts = [part for part in self.cwd.split("/") if part]
        if not parts:
            return "/"
        return "/" + "/".join(parts[:-1]) if len(parts) > 1 else "/"

    def list_entries(self, path: str | None = None) -> list[RemoteEntry]:
        directory = self.resolve(path) if path else self.cwd
        entries: list[RemoteEntry] = []
        for item in self.client.listdir(directory):
            if item.name in (".", ".."):
                continue
            child_path = normalize_path(f"{directory.rstrip('/')}/{item.name}")
            try:
                info = self.client.stat(child_path)
                entries.append(
                    RemoteEntry(
                        name=item.name,
                        path=child_path,
                        is_dir=info.is_dir,
                        size=info.size,
                        mtime=info.mtime,
                    )
                )
            except TNFSError:
                entries.append(
                    RemoteEntry(
                        name=item.name,
                        path=child_path,
                        is_dir=item.is_dir,
                    )
                )
        entries.sort(key=lambda entry: (not entry.is_dir, entry.name.lower()))
        return entries

    def stat(self, path: str) -> tuple[str, FileStat]:
        resolved = self.resolve(path)
        return resolved, self.client.stat(resolved)

    def read_file(self, path: str) -> bytes:
        return self.client.read_file(self.resolve(path))

    def write_file(self, path: str, content: bytes) -> int:
        return self.client.write_file(self.resolve(path), content)

    def mkdir(self, path: str) -> str:
        resolved = self.resolve(path)
        self.client.mkdir(resolved)
        return resolved

    def rmdir(self, path: str) -> str:
        resolved = self.resolve(path)
        self.client.rmdir(resolved)
        return resolved

    def unlink(self, path: str) -> str:
        resolved = self.resolve(path)
        self.client.unlink(resolved)
        return resolved

    def filesystem_usage(self) -> tuple[int, int, int]:
        total = self.client.filesystem_size()
        free = self.client.filesystem_free()
        used = total - free if total >= free else 0
        return total, free, used

    def download(self, remote: str, local: str | Path) -> tuple[str, Path, int]:
        resolved = self.resolve(remote)
        data = self.client.read_file(resolved)
        destination = Path(local)
        destination.write_bytes(data)
        return resolved, destination, len(data)

    def upload(self, local: str | Path, remote: str | None = None) -> tuple[Path, str, int]:
        source = Path(local)
        if not source.is_file():
            raise FileNotFoundError(f"Local file not found: {source}")
        target = self.resolve(remote or source.name)
        written = self.client.write_file(target, source.read_bytes())
        return source, target, written

"""Remote filesystem session with working-directory tracking."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from tnfs.client import FileStat, TNFSClient, TNFSError
from tnfs.protocol import normalize_path

ProgressCallback = Callable[[str, int], None]


@dataclass
class RemoteEntry:
    name: str
    path: str
    is_dir: bool
    size: int = 0
    mtime: int = 0


@dataclass
class TransferSummary:
    """Result of a file or recursive directory transfer."""

    files: int = 0
    directories: int = 0
    bytes_transferred: int = 0
    source: str = ""
    destination: str = ""
    paths: list[str] = field(default_factory=list)


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

    def list_entries(self, path: str | None = None, *, include_parent: bool = True) -> list[RemoteEntry]:
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
        if include_parent and directory != "/":
            entries.insert(
                0,
                RemoteEntry(name="..", path=self.parent_dir(), is_dir=True),
            )
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

    def ensure_dir(self, path: str) -> str:
        """Create a remote directory if it does not already exist."""
        resolved = self.resolve(path)
        try:
            info = self.client.stat(resolved)
        except TNFSError:
            self.client.mkdir(resolved)
            return resolved
        if info.is_dir:
            return resolved
        raise TNFSError(0xFF, f"Path exists and is not a directory: {resolved}")

    def rmdir(self, path: str) -> str:
        resolved = self.resolve(path)
        self.client.rmdir(resolved)
        return resolved

    def unlink(self, path: str) -> str:
        resolved = self.resolve(path)
        self.client.unlink(resolved)
        return resolved

    def remove(
        self,
        path: str,
        *,
        recursive: bool = False,
    ) -> TransferSummary:
        """Remove a file or directory.

        Directories require ``recursive=True`` when they contain entries.
        Empty directories are removed with RMDIR even without ``recursive``.
        """
        resolved, info = self.stat(path)
        summary = TransferSummary(source=resolved, destination="")

        if info.is_file or not info.is_dir:
            self.client.unlink(resolved)
            summary.files = 1
            summary.paths.append(resolved)
            return summary

        children = self.list_entries(resolved, include_parent=False)
        if children and not recursive:
            raise TNFSError(
                0xFF,
                f"{resolved!r} is a non-empty directory; use rm -r / rmdir after emptying it",
            )

        def walk(directory: str) -> None:
            for entry in self.list_entries(directory, include_parent=False):
                if entry.is_dir:
                    walk(entry.path)
                    self.client.rmdir(entry.path)
                    summary.directories += 1
                    summary.paths.append(entry.path)
                else:
                    self.client.unlink(entry.path)
                    summary.files += 1
                    summary.paths.append(entry.path)

        if recursive:
            walk(resolved)
        self.client.rmdir(resolved)
        summary.directories += 1
        summary.paths.append(resolved)
        return summary

    def filesystem_usage(self) -> tuple[int, int, int]:
        total = self.client.filesystem_size()
        free = self.client.filesystem_free()
        used = total - free if total >= free else 0
        return total, free, used

    def download(self, remote: str, local: str | Path) -> tuple[str, Path, int]:
        resolved = self.resolve(remote)
        data = self.client.read_file(resolved)
        destination = Path(local)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        return resolved, destination, len(data)

    def upload(self, local: str | Path, remote: str | None = None) -> tuple[Path, str, int]:
        source = Path(local)
        if not source.is_file():
            raise FileNotFoundError(f"Local file not found: {source}")
        target = self.resolve(remote or source.name)
        written = self.client.write_file(target, source.read_bytes())
        return source, target, written

    def download_tree(
        self,
        remote: str,
        local: str | Path,
        *,
        progress: ProgressCallback | None = None,
    ) -> TransferSummary:
        """Download a remote file or recursively download a directory tree."""
        resolved, info = self.stat(remote)
        destination = Path(local)

        if not info.is_dir:
            _, dest, size = self.download(resolved, destination)
            if progress:
                progress(resolved, size)
            return TransferSummary(
                files=1,
                bytes_transferred=size,
                source=resolved,
                destination=str(dest),
                paths=[str(dest)],
            )

        if destination.exists() and destination.is_dir():
            destination = destination / Path(resolved).name
        destination.mkdir(parents=True, exist_ok=True)

        summary = TransferSummary(
            directories=1,
            source=resolved,
            destination=str(destination),
            paths=[str(destination)],
        )

        def walk(remote_dir: str, local_dir: Path) -> None:
            for entry in self.list_entries(remote_dir, include_parent=False):
                if entry.is_dir:
                    child_local = local_dir / entry.name
                    child_local.mkdir(parents=True, exist_ok=True)
                    summary.directories += 1
                    summary.paths.append(str(child_local))
                    walk(entry.path, child_local)
                else:
                    data = self.client.read_file(entry.path)
                    child_local = local_dir / entry.name
                    child_local.write_bytes(data)
                    summary.files += 1
                    summary.bytes_transferred += len(data)
                    summary.paths.append(str(child_local))
                    if progress:
                        progress(entry.path, len(data))

        walk(resolved, destination)
        return summary

    def upload_tree(
        self,
        local: str | Path,
        remote: str | None = None,
        *,
        progress: ProgressCallback | None = None,
    ) -> TransferSummary:
        """Upload a local file or recursively upload a directory tree."""
        source = Path(local)
        if not source.exists():
            raise FileNotFoundError(f"Local path not found: {source}")

        if source.is_file():
            src, target, size = self.upload(source, remote)
            if progress:
                progress(str(src), size)
            return TransferSummary(
                files=1,
                bytes_transferred=size,
                source=str(src),
                destination=target,
                paths=[target],
            )

        if not source.is_dir():
            raise NotADirectoryError(f"Not a file or directory: {source}")

        target_root = self.resolve(remote or source.name)
        self.ensure_dir(target_root)
        summary = TransferSummary(
            directories=1,
            source=str(source),
            destination=target_root,
            paths=[target_root],
        )

        for path in sorted(source.rglob("*")):
            relative = path.relative_to(source).as_posix()
            remote_path = normalize_path(f"{target_root.rstrip('/')}/{relative}")
            if path.is_dir():
                self.ensure_dir(remote_path)
                summary.directories += 1
                summary.paths.append(remote_path)
                continue
            if not path.is_file():
                continue
            parent_remote = normalize_path(str(Path(remote_path).parent).replace("\\", "/"))
            if parent_remote not in ("", "/"):
                self.ensure_dir(parent_remote)
            data = path.read_bytes()
            written = self.client.write_file(remote_path, data)
            summary.files += 1
            summary.bytes_transferred += written
            summary.paths.append(remote_path)
            if progress:
                progress(str(path), written)

        return summary

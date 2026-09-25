"""Interactive command-line shell for TNFS."""

from __future__ import annotations

import shlex
import sys
from pathlib import Path

from tnfs.client import TNFSError
from tnfs.formatting import format_size, format_stat, print_listing
from tnfs.remote import RemoteSession

HELP_TEXT = """Available commands:
  ls [-l] [path]          List directory entries
  cd <path>               Change remote working directory
  pwd                     Print current remote directory
  stat <path>             Show file or directory metadata
  cat <path>              Print a remote file
  get [-r] <remote> [local] Download a file or directory (-r for dirs)
  put [-r] <local> [remote] Upload a file or directory (-r for dirs)
  mkdir <path>            Create a directory
  rmdir <path>            Remove an empty directory
  rm [-r] <path>          Delete a file or directory (-r for non-empty trees)
  df                      Show filesystem usage
  help                    Show this help
  quit, exit              Disconnect and leave the shell

Paths are resolved relative to the current remote directory unless absolute."""


class InteractiveShell:
    def __init__(self, session: RemoteSession):
        self.session = session

    @property
    def prompt(self) -> str:
        return f"tnfs://{self.session.host}{self.session.cwd}> "

    def run(self) -> int:
        print(
            f"Connected to {self.session.host}:{self.session.port} "
            f"via {self.session.transport} (TNFS {self.session.version})"
        )
        print("Type 'help' for commands, 'quit' to exit.")

        while True:
            try:
                line = input(self.prompt)
            except (EOFError, KeyboardInterrupt):
                print()
                break

            line = line.strip()
            if not line:
                continue

            try:
                should_exit = self.execute(line)
                if should_exit:
                    break
            except TNFSError as exc:
                print(f"TNFS error: {exc}", file=sys.stderr)
            except FileNotFoundError as exc:
                print(exc, file=sys.stderr)
            except OSError as exc:
                print(f"Connection error: {exc}", file=sys.stderr)

        print("Disconnected.")
        return 0

    def execute(self, line: str) -> bool:
        parts = shlex.split(line)
        command = parts[0].lower()
        args = parts[1:]

        if command in {"quit", "exit"}:
            return True

        if command == "help":
            print(HELP_TEXT)
            return False

        if command == "pwd":
            print(self.session.cwd)
            return False

        if command == "ls":
            long = False
            path = None
            for arg in args:
                if arg in {"-l", "--long"}:
                    long = True
                else:
                    path = arg
            directory = self.session.resolve(path) if path else self.session.cwd
            print_listing(self.session.client, directory, long=long)
            return False

        if command == "cd":
            if not args:
                self.session.chdir("/")
            else:
                self.session.chdir(args[0])
            return False

        if command == "stat":
            if not args:
                raise ValueError("usage: stat <path>")
            path, info = self.session.stat(args[0])
            print(format_stat(info, path))
            return False

        if command == "cat":
            if not args:
                raise ValueError("usage: cat <path>")
            data = self.session.read_file(args[0])
            sys.stdout.buffer.write(data)
            if data and not data.endswith(b"\n"):
                sys.stdout.buffer.write(b"\n")
            return False

        if command == "get":
            recursive = False
            paths = []
            for arg in args:
                if arg in {"-r", "--recursive"}:
                    recursive = True
                else:
                    paths.append(arg)
            if not paths:
                raise ValueError("usage: get [-r] <remote> [local]")
            remote = paths[0]
            local = paths[1] if len(paths) > 1 else Path(remote).name
            _, info = self.session.stat(remote)
            if info.is_dir and not recursive:
                raise ValueError(f"{remote!r} is a directory; use: get -r {remote}")
            summary = self.session.download_tree(remote, local)
            print(
                f"Downloaded {summary.files} file(s), {summary.directories} dir(s), "
                f"{summary.bytes_transferred} bytes to {summary.destination}"
            )
            return False

        if command == "put":
            recursive = False
            paths = []
            for arg in args:
                if arg in {"-r", "--recursive"}:
                    recursive = True
                else:
                    paths.append(arg)
            if not paths:
                raise ValueError("usage: put [-r] <local> [remote]")
            local = Path(paths[0])
            remote = paths[1] if len(paths) > 1 else None
            if local.is_dir() and not recursive:
                raise ValueError(f"{local} is a directory; use: put -r {local}")
            summary = self.session.upload_tree(local, remote)
            print(
                f"Uploaded {summary.files} file(s), {summary.directories} dir(s), "
                f"{summary.bytes_transferred} bytes to {summary.destination}"
            )
            return False

        if command == "mkdir":
            if not args:
                raise ValueError("usage: mkdir <path>")
            created = self.session.mkdir(args[0])
            print(f"Created directory {created}")
            return False

        if command == "rmdir":
            if not args:
                raise ValueError("usage: rmdir <path>")
            removed = self.session.rmdir(args[0])
            print(f"Removed directory {removed}")
            return False

        if command == "rm":
            recursive = False
            paths = []
            for arg in args:
                if arg in {"-r", "--recursive"}:
                    recursive = True
                else:
                    paths.append(arg)
            if not paths:
                raise ValueError("usage: rm [-r] <path>")
            summary = self.session.remove(paths[0], recursive=recursive)
            if summary.directories and not summary.files:
                print(f"Removed directory {summary.source}")
            elif summary.directories:
                print(
                    f"Removed {summary.files} file(s) and {summary.directories} dir(s) "
                    f"under {summary.source}"
                )
            else:
                print(f"Removed file {summary.source}")
            return False

        if command == "df":
            total, free, used = self.session.filesystem_usage()
            print(f"Filesystem size: {format_size(total)} ({total} bytes)")
            print(f"Free space:      {format_size(free)} ({free} bytes)")
            print(f"Used space:      {format_size(used)} ({used} bytes)")
            return False

        raise ValueError(f"Unknown command: {command}. Type 'help' for available commands.")


def run_shell(
    host: str,
    port: int = 16384,
    transport: str | None = None,
    mount_path: str = "/",
) -> int:
    with RemoteSession(host=host, port=port, transport=transport, mount_path=mount_path) as session:
        return InteractiveShell(session).run()

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
  get <remote> [local]    Download a file
  put <local> [remote]    Upload a file
  mkdir <path>            Create a directory
  rmdir <path>            Remove a directory
  rm <path>               Delete a file
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
            if not args:
                raise ValueError("usage: get <remote> [local]")
            remote = args[0]
            local = args[1] if len(args) > 1 else Path(remote).name
            resolved, destination, size = self.session.download(remote, local)
            print(f"Downloaded {size} bytes from {resolved} to {destination}")
            return False

        if command == "put":
            if not args:
                raise ValueError("usage: put <local> [remote]")
            local = args[0]
            remote = args[1] if len(args) > 1 else None
            source, target, size = self.session.upload(local, remote)
            print(f"Uploaded {size} bytes from {source} to {target}")
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
            if not args:
                raise ValueError("usage: rm <path>")
            removed = self.session.unlink(args[0])
            print(f"Removed file {removed}")
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

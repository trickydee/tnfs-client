#!/usr/bin/env python3
"""Command-line utility for TNFS servers."""

from __future__ import annotations

import argparse
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from tnfs.client import TNFSClient, TNFSError
from tnfs.formatting import format_size, format_stat, print_listing
from tnfs.protocol import normalize_path
from tnfs.remote import RemoteSession
from tnfs.shell import run_shell


@contextmanager
def connect(args: argparse.Namespace, quiet: bool = False) -> Iterator[TNFSClient]:
    client = TNFSClient(
        host=args.host,
        port=args.port,
        transport=args.transport,
        mount_path=args.mount,
    )
    try:
        if not quiet:
            print(f"Connected via {client.transport} (TNFS {client.version})")
        yield client
    finally:
        client.close()


def handle_errors(func):
    def wrapper(args: argparse.Namespace) -> int:
        try:
            return func(args)
        except TNFSError as exc:
            print(f"TNFS error: {exc}", file=sys.stderr)
            return 1
        except OSError as exc:
            print(f"Connection error: {exc}", file=sys.stderr)
            return 1

    return wrapper


@handle_errors
def cmd_ls(args: argparse.Namespace) -> int:
    path = normalize_path(args.path)
    with connect(args) as client:
        print_listing(client, path, long=args.long)
    return 0


@handle_errors
def cmd_stat(args: argparse.Namespace) -> int:
    path = normalize_path(args.path)
    with connect(args, quiet=True) as client:
        print(format_stat(client.stat(path), path))
    return 0


@handle_errors
def cmd_cat(args: argparse.Namespace) -> int:
    path = normalize_path(args.path)
    with connect(args, quiet=True) as client:
        data = client.read_file(path)
        sys.stdout.buffer.write(data)
        if data and not data.endswith(b"\n"):
            sys.stdout.buffer.write(b"\n")
    return 0


@handle_errors
def cmd_get(args: argparse.Namespace) -> int:
    with RemoteSession(
        host=args.host,
        port=args.port,
        transport=args.transport,
        mount_path=args.mount,
    ) as session:
        _, destination, size = session.download(args.remote, args.local or Path(args.remote).name)
        print(f"Downloaded {size} bytes to {destination}")
    return 0


@handle_errors
def cmd_put(args: argparse.Namespace) -> int:
    with RemoteSession(
        host=args.host,
        port=args.port,
        transport=args.transport,
        mount_path=args.mount,
    ) as session:
        _, target, size = session.upload(args.local, args.remote)
        print(f"Uploaded {size} bytes to {target}")
    return 0


@handle_errors
def cmd_mkdir(args: argparse.Namespace) -> int:
    with RemoteSession(
        host=args.host,
        port=args.port,
        transport=args.transport,
        mount_path=args.mount,
    ) as session:
        created = session.mkdir(args.path)
        print(f"Created directory {created}")
    return 0


@handle_errors
def cmd_rmdir(args: argparse.Namespace) -> int:
    with RemoteSession(
        host=args.host,
        port=args.port,
        transport=args.transport,
        mount_path=args.mount,
    ) as session:
        removed = session.rmdir(args.path)
        print(f"Removed directory {removed}")
    return 0


@handle_errors
def cmd_rm(args: argparse.Namespace) -> int:
    with RemoteSession(
        host=args.host,
        port=args.port,
        transport=args.transport,
        mount_path=args.mount,
    ) as session:
        removed = session.unlink(args.path)
        print(f"Removed file {removed}")
    return 0


@handle_errors
def cmd_df(args: argparse.Namespace) -> int:
    with RemoteSession(
        host=args.host,
        port=args.port,
        transport=args.transport,
        mount_path=args.mount,
    ) as session:
        total, free, used = session.filesystem_usage()
        print(f"Filesystem size: {format_size(total)} ({total} bytes)")
        print(f"Free space:      {format_size(free)} ({free} bytes)")
        print(f"Used space:      {format_size(used)} ({used} bytes)")
    return 0


def cmd_shell(args: argparse.Namespace) -> int:
    try:
        return run_shell(
            host=args.host,
            port=args.port,
            transport=args.transport,
            mount_path=args.mount,
        )
    except TNFSError as exc:
        print(f"TNFS error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Connection error: {exc}", file=sys.stderr)
        return 1


def cmd_tui(args: argparse.Namespace) -> int:
    try:
        from tnfs.tui import run_tui
    except ImportError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    try:
        return run_tui(
            host=args.host,
            port=args.port,
            transport=args.transport,
            mount_path=args.mount,
            local_dir=args.local_dir,
        )
    except TNFSError as exc:
        print(f"TNFS error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Connection error: {exc}", file=sys.stderr)
        return 1


def add_connection_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--host", default="localhost", help="TNFS server hostname")
    parser.add_argument("--port", type=int, default=16384, help="TNFS server port")
    parser.add_argument("--mount", default="/", help="Mount path on the server")
    parser.add_argument(
        "--transport",
        choices=["udp", "tcp"],
        default=None,
        help="Force UDP or TCP (default: try TCP, fall back to UDP)",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tnfscli",
        description="Client utility for TNFS servers (FujiNet, Spectranet, etc.)",
    )
    add_connection_args(parser)

    subparsers = parser.add_subparsers(dest="command", required=True)

    ls_parser = subparsers.add_parser("ls", help="List files on the remote server")
    ls_parser.add_argument("path", nargs="?", default="/", help="Directory path to list")
    ls_parser.add_argument("-l", "--long", action="store_true", help="Long listing format")
    ls_parser.set_defaults(func=cmd_ls)

    stat_parser = subparsers.add_parser("stat", help="Show file or directory metadata")
    stat_parser.add_argument("path", help="Remote path")
    stat_parser.set_defaults(func=cmd_stat)

    cat_parser = subparsers.add_parser("cat", help="Print a remote file to stdout")
    cat_parser.add_argument("path", help="Remote file path")
    cat_parser.set_defaults(func=cmd_cat)

    get_parser = subparsers.add_parser("get", help="Download a remote file")
    get_parser.add_argument("remote", help="Remote file path")
    get_parser.add_argument("local", nargs="?", help="Local destination path")
    get_parser.set_defaults(func=cmd_get)

    put_parser = subparsers.add_parser("put", help="Upload a local file")
    put_parser.add_argument("local", help="Local file path")
    put_parser.add_argument("remote", help="Remote destination path")
    put_parser.set_defaults(func=cmd_put)

    mkdir_parser = subparsers.add_parser("mkdir", help="Create a remote directory")
    mkdir_parser.add_argument("path", help="Remote directory path")
    mkdir_parser.set_defaults(func=cmd_mkdir)

    rmdir_parser = subparsers.add_parser("rmdir", help="Remove a remote directory")
    rmdir_parser.add_argument("path", help="Remote directory path")
    rmdir_parser.set_defaults(func=cmd_rmdir)

    rm_parser = subparsers.add_parser("rm", help="Delete a remote file")
    rm_parser.add_argument("path", help="Remote file path")
    rm_parser.set_defaults(func=cmd_rm)

    df_parser = subparsers.add_parser("df", help="Show filesystem size and free space")
    df_parser.set_defaults(func=cmd_df)

    shell_parser = subparsers.add_parser("shell", help="Start an interactive remote shell")
    shell_parser.set_defaults(func=cmd_shell)

    tui_parser = subparsers.add_parser("tui", help="Browse the remote filesystem in a TUI")
    tui_parser.add_argument(
        "--local-dir",
        default=None,
        help="Starting directory for the local pane (default: current working directory)",
    )
    tui_parser.set_defaults(func=cmd_tui)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

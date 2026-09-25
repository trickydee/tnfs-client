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
        remote = args.remote
        local = Path(args.local) if args.local else Path(Path(remote).name)
        _, info = session.stat(remote)
        if info.is_dir and not args.recursive:
            print(
                f"Remote path {remote!r} is a directory. Re-run with -r/--recursive to download it.",
                file=sys.stderr,
            )
            return 1

        if args.recursive or info.is_dir:
            summary = session.download_tree(
                remote,
                local,
                progress=lambda path, size: print(f"  {path} ({size} bytes)"),
            )
            print(
                f"Downloaded {summary.files} file(s), {summary.directories} dir(s), "
                f"{summary.bytes_transferred} bytes to {summary.destination}"
            )
        else:
            _, destination, size = session.download(remote, local)
            print(f"Downloaded {size} bytes to {destination}")
    return 0


@handle_errors
def cmd_put(args: argparse.Namespace) -> int:
    source = Path(args.local)
    if not source.exists():
        print(f"Local path not found: {source}", file=sys.stderr)
        return 1

    with RemoteSession(
        host=args.host,
        port=args.port,
        transport=args.transport,
        mount_path=args.mount,
    ) as session:
        if source.is_dir() and not args.recursive:
            print(
                f"Local path {source} is a directory. Re-run with -r/--recursive to upload it.",
                file=sys.stderr,
            )
            return 1

        if args.recursive or source.is_dir():
            summary = session.upload_tree(
                source,
                args.remote,
                progress=lambda path, size: print(f"  {path} ({size} bytes)"),
            )
            print(
                f"Uploaded {summary.files} file(s), {summary.directories} dir(s), "
                f"{summary.bytes_transferred} bytes to {summary.destination}"
            )
        else:
            _, target, size = session.upload(source, args.remote)
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
        summary = session.remove(args.path, recursive=args.recursive)
        if summary.directories and not summary.files:
            print(f"Removed directory {summary.source}")
        elif summary.directories:
            print(
                f"Removed {summary.files} file(s) and {summary.directories} dir(s) "
                f"under {summary.source}"
            )
        else:
            print(f"Removed file {summary.source}")
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


def add_connection_args(
    parser: argparse.ArgumentParser,
    *,
    suppress_defaults: bool = False,
) -> None:
    # When the same options exist on both the top-level parser and a
    # subparser, subparser defaults would overwrite values set before the
    # subcommand. Use SUPPRESS on subparsers so that only explicitly passed
    # flags override the top-level values.
    default = argparse.SUPPRESS if suppress_defaults else None
    parser.add_argument(
        "--host",
        default="localhost" if default is None else default,
        help="TNFS server hostname",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=16384 if default is None else default,
        help="TNFS server port",
    )
    parser.add_argument(
        "--mount",
        default="/" if default is None else default,
        help="Mount path on the server",
    )
    parser.add_argument(
        "--transport",
        choices=["udp", "tcp"],
        default=default,
        help="Force UDP or TCP (default: try TCP, fall back to UDP)",
    )


def build_parser() -> argparse.ArgumentParser:
    connection_parser = argparse.ArgumentParser(add_help=False)
    add_connection_args(connection_parser)

    sub_connection_parser = argparse.ArgumentParser(add_help=False)
    add_connection_args(sub_connection_parser, suppress_defaults=True)

    parser = argparse.ArgumentParser(
        prog="tnfscli",
        description="Client utility for TNFS servers (FujiNet, Spectranet, etc.)",
        parents=[connection_parser],
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    ls_parser = subparsers.add_parser(
        "ls",
        help="List files on the remote server",
        parents=[sub_connection_parser],
    )
    ls_parser.add_argument("path", nargs="?", default="/", help="Directory path to list")
    ls_parser.add_argument("-l", "--long", action="store_true", help="Long listing format")
    ls_parser.set_defaults(func=cmd_ls)

    stat_parser = subparsers.add_parser(
        "stat",
        help="Show file or directory metadata",
        parents=[sub_connection_parser],
    )
    stat_parser.add_argument("path", help="Remote path")
    stat_parser.set_defaults(func=cmd_stat)

    cat_parser = subparsers.add_parser(
        "cat",
        help="Print a remote file to stdout",
        parents=[sub_connection_parser],
    )
    cat_parser.add_argument("path", help="Remote file path")
    cat_parser.set_defaults(func=cmd_cat)

    get_parser = subparsers.add_parser(
        "get",
        help="Download a remote file or directory",
        parents=[sub_connection_parser],
    )
    get_parser.add_argument("remote", help="Remote file or directory path")
    get_parser.add_argument("local", nargs="?", help="Local destination path")
    get_parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="Download directories recursively",
    )
    get_parser.set_defaults(func=cmd_get)

    put_parser = subparsers.add_parser(
        "put",
        help="Upload a local file or directory",
        parents=[sub_connection_parser],
    )
    put_parser.add_argument("local", help="Local file or directory path")
    put_parser.add_argument("remote", nargs="?", help="Remote destination path")
    put_parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="Upload directories recursively",
    )
    put_parser.set_defaults(func=cmd_put)

    mkdir_parser = subparsers.add_parser(
        "mkdir",
        help="Create a remote directory",
        parents=[sub_connection_parser],
    )
    mkdir_parser.add_argument("path", help="Remote directory path")
    mkdir_parser.set_defaults(func=cmd_mkdir)

    rmdir_parser = subparsers.add_parser(
        "rmdir",
        help="Remove a remote directory",
        parents=[sub_connection_parser],
    )
    rmdir_parser.add_argument("path", help="Remote directory path")
    rmdir_parser.set_defaults(func=cmd_rmdir)

    rm_parser = subparsers.add_parser(
        "rm",
        help="Delete a remote file or directory",
        parents=[sub_connection_parser],
    )
    rm_parser.add_argument("path", help="Remote file or directory path")
    rm_parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="Recursively delete directories and their contents",
    )
    rm_parser.set_defaults(func=cmd_rm)

    df_parser = subparsers.add_parser(
        "df",
        help="Show filesystem size and free space",
        parents=[sub_connection_parser],
    )
    df_parser.set_defaults(func=cmd_df)

    shell_parser = subparsers.add_parser(
        "shell",
        help="Start an interactive remote shell",
        parents=[sub_connection_parser],
    )
    shell_parser.set_defaults(func=cmd_shell)

    tui_parser = subparsers.add_parser(
        "tui",
        help="Browse the remote filesystem in a TUI",
        parents=[sub_connection_parser],
    )
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

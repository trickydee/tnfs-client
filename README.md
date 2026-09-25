# TNFS Client

A Python client for [TNFS](https://github.com/FujiNetWIFI/spectranet/blob/master/tnfs/tnfs-protocol.md) servers used by FujiNet, Spectranet, and similar retro networking projects.

Three ways to use it:

| Mode | Entry point | Best for |
|------|-------------|----------|
| One-shot CLI | `./scripts/tnfs <cmd>` | Scripts and quick tasks |
| Interactive shell | `./scripts/tnfs-shell` | Persistent remote session with `cd` |
| Dual-pane TUI | `./scripts/tnfs-tui` | Browsing and transferring files visually |

## Requirements

- Python 3.10+
- Stdlib only for CLI and shell
- [Textual](https://textual.textualize.io/) for the TUI (installed via the setup script)

## Install

```bash
./scripts/setup-venv.sh
```

Creates `.venv` and installs the project plus TUI dependencies.

Manual alternative:

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[tui]"
```

### Convenience scripts

All scripts use the project venv automatically:

| Script | Mode |
|--------|------|
| `./scripts/tnfs <command>` | One-shot commands |
| `./scripts/tnfs-shell` | Interactive shell |
| `./scripts/tnfs-tui` | TUI browser |

```bash
./scripts/tnfs --host tnfs.example ls -l /
./scripts/tnfs ls -l / --host tnfs.example          # --host can go either side
./scripts/tnfs-shell --host tnfs.example
./scripts/tnfs-tui --host tnfs.example
./scripts/tnfs-tui --host tnfs.example --local-dir ~/Downloads
```

## Connection options

Shared by every command:

| Option | Default | Description |
|--------|---------|-------------|
| `--host` | `localhost` | TNFS server hostname |
| `--port` | `16384` | TNFS server port |
| `--mount` | `/` | Mount path on the server |
| `--transport` | auto | `tcp`, `udp`, or omit to try TCP then fall back to UDP |

TNFS requires UDP on port **16384**. TCP is optional; this client prefers TCP when available.

```bash
./scripts/tnfs --host tnfs.example --transport udp ls /
./scripts/tnfs --host tnfs.example --port 16384 df
```

If you run the TUI without a reachable host (default `localhost`), it fails quickly with a tip instead of hanging on a blank screen.

## One-shot commands

```bash
./scripts/tnfs --host tnfs.example COMMAND [args...]
# or
python tnfscli.py --host tnfs.example COMMAND [args...]
```

| Command | Description |
|---------|-------------|
| `ls [path]` | List a remote directory (`-l` for long listing with size/mtime) |
| `stat <path>` | Show file or directory metadata |
| `cat <path>` | Print a remote file to stdout |
| `get [-r] <remote> [local]` | Download a file, or a directory tree with `-r` |
| `put [-r] <local> [remote]` | Upload a file, or a directory tree with `-r` |
| `mkdir <path>` | Create a remote directory |
| `rmdir <path>` | Remove an empty remote directory |
| `rm [-r] <path>` | Delete a file, an empty directory, or a tree with `-r` |
| `df` | Show filesystem size / free / used |
| `shell` | Start the interactive shell |
| `tui` | Start the dual-pane TUI |

### Examples

```bash
./scripts/tnfs --host tnfs.example ls
./scripts/tnfs --host tnfs.example ls -l /games
./scripts/tnfs --host tnfs.example stat /readme.txt
./scripts/tnfs --host tnfs.example cat /readme.txt

# Single files
./scripts/tnfs --host tnfs.example get /rom.atr ./rom.atr
./scripts/tnfs --host tnfs.example put ./hello.txt /hello.txt

# Whole directory trees (structure preserved)
./scripts/tnfs --host tnfs.example get -r /games ./games
./scripts/tnfs --host tnfs.example put -r ./roms /roms

# Create / delete
./scripts/tnfs --host tnfs.example mkdir /games/new
./scripts/tnfs --host tnfs.example rmdir /games/empty
./scripts/tnfs --host tnfs.example rm /old.txt
./scripts/tnfs --host tnfs.example rm /emptydir          # empty dirs work with rm
./scripts/tnfs --host tnfs.example rm -r /games/oldtree  # recursive tree delete

./scripts/tnfs --host tnfs.example df
```

**Notes**

- Directory `get` / `put` require `-r` / `--recursive`.
- `rm` on a **file** or **empty directory** works without `-r`.
- `rm` on a **non-empty directory** needs `-r` (or empty it first and use `rmdir`).
- Paths may be absolute (`/games`) or relative to the mount root.

## Interactive shell

```bash
./scripts/tnfs-shell --host tnfs.example
# or
./scripts/tnfs --host tnfs.example shell
```

Keeps one connection open and tracks a remote working directory:

```text
Connected to tnfs.example:16384 via tcp (TNFS 1.3)
Type 'help' for commands, 'quit' to exit.
tnfs://tnfs.example/> ls
tnfs://tnfs.example/> cd games
tnfs://tnfs.example/games> pwd
/games
tnfs://tnfs.example/games> get -r RTYPE ./rtype
tnfs://tnfs.example/games> rm -r old
tnfs://tnfs.example/games> quit
```

| Command | Description |
|---------|-------------|
| `ls [-l] [path]` | List directory |
| `cd [path]` | Change remote directory (`cd` alone goes to `/`) |
| `pwd` | Print remote working directory |
| `stat <path>` | Metadata |
| `cat <path>` | Print file |
| `get [-r] <remote> [local]` | Download file or tree |
| `put [-r] <local> [remote]` | Upload file or tree |
| `mkdir <path>` | Create directory |
| `rmdir <path>` | Remove empty directory |
| `rm [-r] <path>` | Delete file / empty dir / tree |
| `df` | Filesystem usage |
| `help` | Show help |
| `quit` / `exit` | Disconnect |

## TUI browser

Dual-pane file manager: **remote TNFS (left)** and **local filesystem (right)**.

```bash
./scripts/tnfs-tui --host tnfs.example
./scripts/tnfs-tui --host tnfs.example --transport udp
./scripts/tnfs-tui --host tnfs.example --local-dir ~/Downloads
```

### Keyboard shortcuts

| Key | Action |
|-----|--------|
| `Tab` | Switch between remote and local panes |
| `Enter` | Open a directory, or preview a file |
| `..` + `Enter` | Go up one level (`..` is listed at the top) |
| `Backspace` | Parent directory in the focused pane |
| `g` | Download selected remote file **or directory tree** to the local pane |
| `p` | Upload selected local file **or directory tree** to the remote pane |
| `m` | Create a directory in the focused pane |
| `Delete` | Remove selected file or empty remote directory |
| `r` | Refresh focused pane |
| `/` | Focus command bar |
| `q` | Quit |

### Typical workflow

1. Launch with `--host` set to your TNFS server
2. `Tab` to the local pane; navigate with `Enter` / `..` to the destination folder
3. `Tab` back to remote; open folders with `Enter`
4. `g` to download or `p` to upload (works on single files and whole folders)

Transfers preserve nested structure. Downloads land in the local pane’s current directory; that pane refreshes when a transfer finishes. Status messages clear after a few seconds.

The command bar (`/`) accepts shell-style commands (`cd`, `get -r`, `put -r`, `mkdir`, `rm -r`, `rmdir`, …) applied to the focused pane.

## Library usage

```python
from tnfs.remote import RemoteSession

with RemoteSession("tnfs.example") as session:
    session.chdir("/games")
    for entry in session.list_entries(include_parent=False):
        print(entry.name, "dir" if entry.is_dir else entry.size)

    # Single file
    session.download("/readme.txt", "./readme.txt")
    session.upload("./hello.txt", "/hello.txt")

    # Recursive trees
    session.download_tree("/games", "./games-backup")
    session.upload_tree("./roms", "/roms")

    # Delete file, empty dir, or tree
    session.remove("/hello.txt")
    session.remove("/emptydir")
    session.remove("/oldtree", recursive=True)
```

Lower-level protocol access is available via `tnfs.client.TNFSClient` (`mount`, `listdir`, `stat`, `read_file`, `write_file`, …).

## Project layout

```text
tnfscli.py          CLI entry point
tnfs/
  client.py         Wire protocol client (UDP/TCP)
  remote.py         Session helpers, cwd, recursive transfer/delete
  shell.py          Interactive shell
  tui.py            Textual dual-pane UI
  local.py          Local filesystem browser for the TUI
  protocol.py       Packet helpers and constants
  formatting.py     Shared listing/stat formatting
scripts/
  setup-venv.sh     Create venv + install deps
  tnfs              One-shot CLI wrapper
  tnfs-shell        Shell wrapper
  tnfs-tui          TUI wrapper
```

## License

See repository metadata / license file if present. TNFS protocol documentation is maintained upstream by the Spectranet / FujiNet projects.

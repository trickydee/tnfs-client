# TNFS Client

A Python client for [TNFS](https://github.com/FujiNetWIFI/spectranet/blob/master/tnfs/tnfs-protocol.md) servers used by FujiNet, Spectranet, and similar retro networking projects.

It supports three ways to work with a server:

- **One-shot commands** for scripting and quick tasks
- **Interactive shell** with a remote working directory
- **TUI browser** for keyboard-driven dual-pane navigation

## Requirements

- Python 3.10+
- Stdlib only for CLI commands and the interactive shell
- `textual` for the TUI (`pip install 'tnfs-client[tui]'`)

## Install

```bash
./scripts/setup-venv.sh
```

This creates `.venv` with the project and TUI dependencies installed.

### Convenience scripts

| Script | Mode |
|--------|------|
| `./scripts/tnfs <command>` | One-shot commands (`ls`, `get`, `stat`, etc.) |
| `./scripts/tnfs-shell` | Interactive shell |
| `./scripts/tnfs-tui` | TUI browser |

Examples:

```bash
./scripts/tnfs --host tnfs.example ls -l /
./scripts/tnfs ls -l / --host tnfs.example
./scripts/tnfs-shell --host tnfs.example
./scripts/tnfs-tui --host tnfs.example
```

Connection options (`--host`, `--port`, `--mount`, `--transport`) can go before or after the subcommand.

Or manually:

```bash
pip install -e .
pip install -e ".[tui]"
```

## One-shot commands

```bash
python tnfscli.py --host tnfs.example ls
python tnfscli.py --host tnfs.example ls -l /
python tnfscli.py --host tnfs.example mkdir /games
python tnfscli.py --host tnfs.example rmdir /games
python tnfscli.py --host tnfs.example stat /example.atr
python tnfscli.py --host tnfs.example get /example.atr ./example.atr
python tnfscli.py --host tnfs.example put ./hello.txt /hello.txt
python tnfscli.py --host tnfs.example rm /hello.txt
python tnfscli.py --host tnfs.example df
```

## Interactive shell

Start a persistent session with a remote working directory:

```bash
python tnfscli.py --host tnfs.example shell
# or
./scripts/tnfs-shell --host tnfs.example
```

Example session:

```text
Connected to tnfs.example:16384 via tcp (TNFS 1.3)
Type 'help' for commands, 'quit' to exit.
tnfs://tnfs.example/> ls
tnfs://tnfs.example/> cd games
tnfs://tnfs.example/games> pwd
/games
tnfs://tnfs.example/games> get rom.atr
tnfs://tnfs.example/games> quit
```

Shell commands: `ls`, `cd`, `pwd`, `stat`, `cat`, `get`, `put`, `mkdir`, `rmdir`, `rm`, `df`, `help`, `quit`

## TUI browser

Dual-pane file manager: **remote TNFS on the left**, **local filesystem on the right**.

```bash
./scripts/tnfs-tui --host tnfs.example
python tnfscli.py tui --host tnfs.example
python tnfscli.py --host tnfs.example tui --local-dir ~/Downloads
```

The TUI connects before launching. If the host is unreachable (for example the default `localhost` with no server), it fails quickly with a tip instead of showing a blank screen.

### Navigation

| Key | Action |
|-----|--------|
| `Tab` | Switch between remote and local panes |
| `Enter` | Open a directory, or preview a file |
| `..` + `Enter` | Go up one directory (shown at the top of listings) |
| `Backspace` | Go to parent directory in the focused pane |
| `g` | Download selected remote file into the local pane's current directory |
| `p` | Upload selected local file into the remote pane's current directory |
| `m` | Create a directory in the focused pane |
| `Delete` | Remove selected file (remote or local) |
| `r` | Refresh focused pane |
| `/` | Focus command bar |
| `q` | Quit |

Typical workflow:

1. Start with `--host` pointing at your TNFS server
2. Press `Tab` to focus the local pane and navigate to the folder you want (use `Enter` / `..`)
3. Press `Tab` back to remote, open folders with `Enter`, download with `g` or upload with `p`

Downloads land in the local pane's current directory and that pane refreshes automatically. Status messages clear after a few seconds.

The command bar accepts shell-style commands such as `cd`, `get`, `put`, `mkdir`, `rm`, and `rmdir` (applied to the focused pane).

## Connection options

| Option | Default | Description |
|--------|---------|-------------|
| `--host` | `localhost` | TNFS server hostname |
| `--port` | `16384` | TNFS server port |
| `--mount` | `/` | Mount path on the server |
| `--transport` | auto | `udp` or `tcp` (tries TCP first, then UDP) |

TNFS servers must support UDP on port 16384; TCP is optional. This client prefers TCP when available.

## Library usage

```python
from tnfs.remote import RemoteSession

with RemoteSession("tnfs.example") as session:
    session.chdir("/games")
    for entry in session.list_entries():
        print(entry.name, entry.size)
```

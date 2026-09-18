# TNFS Client

A Python client for [TNFS](https://github.com/FujiNetWIFI/spectranet/blob/master/tnfs/tnfs-protocol.md) servers used by FujiNet, Spectranet, and similar retro networking projects.

It supports three ways to work with a server:

- **One-shot commands** for scripting and quick tasks
- **Interactive shell** with a remote working directory
- **TUI browser** for keyboard-driven navigation

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
python tnfscli.py ls
python tnfscli.py ls -l /
python tnfscli.py mkdir /games
python tnfscli.py stat /example.atr
python tnfscli.py get /example.atr ./example.atr
python tnfscli.py put ./hello.txt /hello.txt
python tnfscli.py df
```

## Interactive shell

Start a persistent session with a remote working directory:

```bash
python tnfscli.py shell
```

Example session:

```text
Connected to localhost:16384 via tcp (TNFS 1.3)
Type 'help' for commands, 'quit' to exit.
tnfs://localhost/> ls
tnfs://localhost/> cd games
tnfs://localhost/games> pwd
/games
tnfs://localhost/games> get rom.atr
tnfs://localhost/games> quit
```

Shell commands: `ls`, `cd`, `pwd`, `stat`, `cat`, `get`, `put`, `mkdir`, `rmdir`, `rm`, `df`, `help`, `quit`

## TUI browser

Dual-pane file manager with remote TNFS on the left and your local filesystem on the right.

```bash
python tnfscli.py tui --host tnfs.example
python tnfscli.py --host tnfs.example tui --local-dir ~/Downloads
./scripts/tnfs-tui --host tnfs.example
```

Keyboard shortcuts:

| Key | Action |
|-----|--------|
| `Tab` | Switch between remote and local panes |
| `Enter` | Open directory or preview file |
| `Backspace` | Go to parent directory in focused pane |
| `g` | Download selected remote file to local directory |
| `p` | Upload selected local file to remote directory |
| `m` | Create a directory in the focused pane |
| `Delete` | Remove selected file (remote or local) |
| `r` | Refresh focused pane |
| `/` | Focus command bar |
| `q` | Quit |

Downloads land in the local pane's current directory and the local pane refreshes automatically. Status messages clear after a few seconds.

The command bar accepts shell-style commands such as `cd`, `get`, `put`, `mkdir`, `rm`, and `rmdir` (applied to the focused pane).

## Connection options

| Option | Default | Description |
|--------|---------|-------------|
| `--host` | `localhost` | TNFS server hostname |
| `--port` | `16384` | TNFS server port |
| `--mount` | `/` | Mount path on the server |
| `--transport` | auto | `udp` or `tcp` (auto tries TCP first) |

## Library usage

```python
from tnfs.remote import RemoteSession

with RemoteSession("localhost") as session:
    session.chdir("/games")
    for entry in session.list_entries():
        print(entry.name, entry.size)
```

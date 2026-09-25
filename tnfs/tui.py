"""Textual TUI for browsing TNFS servers with a local filesystem pane."""

from __future__ import annotations

from pathlib import Path

from tnfs.client import TNFSError
from tnfs.formatting import format_mtime, format_size, format_stat
from tnfs.local import LocalBrowser, LocalEntry
from tnfs.remote import RemoteEntry, RemoteSession

try:
    from textual import on, work
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Horizontal, Vertical
    from textual.screen import ModalScreen
    from textual.timer import Timer
    from textual.widgets import Button, DataTable, Footer, Header, Input, Label, RichLog, Static
except ImportError as exc:  # pragma: no cover - exercised when optional dep missing
    raise ImportError(
        "The TUI requires the 'textual' package. Install it with: pip install 'tnfs-client[tui]'"
    ) from exc


class DirectoryNamePrompt(ModalScreen[str | None]):
    """Ask for a directory name."""

    CSS = """
    DirectoryNamePrompt {
        align: center middle;
    }

    #prompt-box {
        width: 60;
        height: auto;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }

    #prompt-buttons {
        height: auto;
        margin-top: 1;
        align: right middle;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    def __init__(self, title: str = "Create directory"):
        super().__init__()
        self._title = title

    def compose(self) -> ComposeResult:
        with Vertical(id="prompt-box"):
            yield Label(self._title)
            yield Input(placeholder="directory-name", id="name-input")
            with Horizontal(id="prompt-buttons"):
                yield Button("Cancel", id="cancel", variant="default")
                yield Button("Create", id="create", variant="primary")

    def on_mount(self) -> None:
        self.query_one("#name-input", Input).focus()

    @on(Input.Submitted, "#name-input")
    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._submit(event.value)

    @on(Button.Pressed, "#create")
    def on_create(self) -> None:
        self._submit(self.query_one("#name-input", Input).value)

    @on(Button.Pressed, "#cancel")
    def on_cancel_button(self) -> None:
        self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _submit(self, value: str) -> None:
        name = value.strip().strip("/\\")
        if not name or "/" in name or "\\" in name:
            self.app.notify("Enter a single directory name (no path separators)", severity="warning")
            return
        self.dismiss(name)


class TNFSBrowser(App):
    """Dual-pane file browser for remote TNFS and local filesystem."""

    CSS = """
    Screen {
        layout: vertical;
    }

    #panes {
        height: 1fr;
    }

    .pane {
        width: 1fr;
        height: 1fr;
        border: solid $surface-lighten-1;
    }

    .pane.focused {
        border: solid $accent;
    }

    .pane-title {
        height: 1;
        background: $surface;
        color: $text;
        padding: 0 1;
    }

    .pane-path {
        height: 1;
        background: $panel;
        color: $text-muted;
        padding: 0 1;
    }

    .file-table {
        height: 1fr;
    }

    #details {
        height: 8;
        border: solid $accent;
        padding: 0 1;
    }

    #status {
        height: 1;
        background: $surface;
        color: $text-muted;
        padding: 0 1;
    }

    #command-bar {
        height: 3;
        border-top: solid $primary;
        padding: 0 1;
    }

    #command-input {
        width: 1fr;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("tab", "switch_pane", "Switch pane"),
        Binding("r", "refresh", "Refresh"),
        Binding("enter", "open_selected", "Open"),
        Binding("backspace", "go_up", "Up"),
        Binding("g", "download_selected", "Get"),
        Binding("p", "upload_selected", "Put"),
        Binding("m", "mkdir", "Mkdir"),
        Binding("delete", "delete_selected", "Delete"),
        Binding("slash", "focus_command", "Command", show=False),
    ]

    def __init__(
        self,
        host: str,
        port: int = 16384,
        transport: str | None = None,
        mount_path: str = "/",
        local_dir: str | Path | None = None,
        session: RemoteSession | None = None,
    ):
        super().__init__()
        self.host = host
        self.port = port
        self.transport = transport
        self.mount_path = mount_path
        self.local_browser = LocalBrowser(Path(local_dir) if local_dir else None)
        self.session = session
        self.remote_entries: list[RemoteEntry] = []
        self.local_entries: list[LocalEntry] = []
        self._remote_cursor_index = 0
        self._local_cursor_index = 0
        self.active_pane = "remote"
        self._status_timer: Timer | None = None
        self._busy = False
        self._owns_session = session is None

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="panes"):
            with Vertical(id="remote-pane", classes="pane focused"):
                yield Static("Remote (TNFS)", classes="pane-title")
                yield Static("", id="remote-path", classes="pane-path")
                yield DataTable(id="remote-table", classes="file-table", cursor_type="row", zebra_stripes=True)
            with Vertical(id="local-pane", classes="pane"):
                yield Static("Local", classes="pane-title")
                yield Static("", id="local-path", classes="pane-path")
                yield DataTable(id="local-table", classes="file-table", cursor_type="row", zebra_stripes=True)
        yield RichLog(id="details", wrap=True, highlight=True, markup=True)
        yield Static("Starting...", id="status")
        with Vertical(id="command-bar"):
            yield Input(
                placeholder="Commands: cd, get, put, mkdir, rm (applies to focused pane)",
                id="command-input",
            )
        yield Footer()

    def on_mount(self) -> None:
        for table_id in ("remote-table", "local-table"):
            table = self.query_one(f"#{table_id}", DataTable)
            table.add_columns("Type", "Size", "Modified", "Name")

        if self.session is None:
            self._set_status(f"Connecting to {self.host}:{self.port}...")
            self.session = RemoteSession(
                host=self.host,
                port=self.port,
                transport=self.transport,
                mount_path=self.mount_path,
                timeout=5.0,
            )
            self._owns_session = True

        self._restore_status()
        self.refresh_remote_listing()
        self.refresh_local_listing()
        self.query_one("#remote-table", DataTable).focus()

    def on_unmount(self) -> None:
        if self.session is not None and self._owns_session:
            self.session.close()
            self.session = None

    def _default_status(self) -> str:
        remote = self.session.cwd if self.session else "/"
        return f"Remote: {remote}  |  Local: {self.local_browser.cwd}  |  Focus: {self.active_pane}"

    def _set_status(self, message: str, *, transient: bool = False) -> None:
        if self._status_timer is not None:
            self._status_timer.stop()
            self._status_timer = None
        safe_message = message.replace("[", "\\[")
        self.query_one("#status", Static).update(safe_message)
        if transient:
            self._status_timer = self.set_timer(4.0, self._restore_status)

    def _restore_status(self) -> None:
        if self._busy:
            return
        self.query_one("#status", Static).update(self._default_status())
        self._status_timer = None

    def _set_busy(self, message: str) -> None:
        self._busy = True
        self._set_status(message)

    def _clear_busy(self, message: str, *, transient: bool = True) -> None:
        self._busy = False
        self._set_status(message, transient=transient)

    def _update_pane_styles(self) -> None:
        remote_pane = self.query_one("#remote-pane")
        local_pane = self.query_one("#local-pane")
        remote_pane.remove_class("focused")
        local_pane.remove_class("focused")
        if self.active_pane == "remote":
            remote_pane.add_class("focused")
        else:
            local_pane.add_class("focused")

    def _populate_table(self, table_id: str, rows: list[tuple[str, str, str, str]]) -> None:
        table = self.query_one(f"#{table_id}", DataTable)
        table.clear()
        for row in rows:
            table.add_row(*row)

    def refresh_remote_listing(self) -> None:
        assert self.session is not None
        self.remote_entries = self.session.list_entries()
        self.query_one("#remote-path", Static).update(
            f"tnfs://{self.session.host}{self.session.cwd}"
        )
        rows = [
            (
                "dir" if entry.is_dir else "file",
                "" if entry.is_dir else format_size(entry.size),
                format_mtime(entry.mtime),
                entry.name,
            )
            for entry in self.remote_entries
        ]
        self._populate_table("remote-table", rows)
        if self.active_pane == "remote":
            self._show_remote_details(self._selected_remote_entry())

    def refresh_local_listing(self) -> None:
        self.local_entries = self.local_browser.list_entries()
        self.query_one("#local-path", Static).update(str(self.local_browser.cwd))
        rows = [
            (
                "dir" if entry.is_dir else "file",
                "" if entry.is_dir else format_size(entry.size),
                format_mtime(int(entry.mtime)),
                entry.name,
            )
            for entry in self.local_entries
        ]
        self._populate_table("local-table", rows)
        if self.active_pane == "local":
            self._show_local_details(self._selected_local_entry())

    def _entry_from_table(
        self,
        table_id: str,
        entries: list,
        cursor_index: int,
    ):
        table = self.query_one(f"#{table_id}", DataTable)
        if table.row_count == 0 or not entries:
            return None
        row_index = table.cursor_row
        if row_index is None or row_index < 0 or row_index >= len(entries):
            row_index = cursor_index
        if row_index < 0 or row_index >= len(entries):
            return None
        return entries[row_index]

    def _selected_remote_entry(self) -> RemoteEntry | None:
        return self._entry_from_table("remote-table", self.remote_entries, self._remote_cursor_index)

    def _selected_local_entry(self) -> LocalEntry | None:
        return self._entry_from_table("local-table", self.local_entries, self._local_cursor_index)

    def _show_remote_details(self, entry: RemoteEntry | None) -> None:
        details = self.query_one("#details", RichLog)
        details.clear()
        if entry is None:
            details.write("[dim]No remote selection[/dim]")
            return
        if entry.name == "..":
            details.write("Parent directory")
            details.write(f"Path:        {entry.path}")
            return
        assert self.session is not None
        try:
            info = self.session.client.stat(entry.path)
            details.write(format_stat(info, entry.path))
        except TNFSError as exc:
            details.write(f"[red]Unable to stat {entry.path}: {exc}[/red]")

    def _show_local_details(self, entry: LocalEntry | None) -> None:
        details = self.query_one("#details", RichLog)
        details.clear()
        if entry is None:
            details.write("[dim]No local selection[/dim]")
            return
        if entry.name == "..":
            details.write("Parent directory")
            details.write(f"Path:        {entry.path}")
            return
        details.write(self.local_browser.format_details(entry))

    def _valid_row(self, cursor_row: int | None, entries: list) -> bool:
        return (
            cursor_row is not None
            and cursor_row >= 0
            and cursor_row < len(entries)
        )

    @on(DataTable.RowHighlighted, "#remote-table")
    def on_remote_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if not self._valid_row(event.cursor_row, self.remote_entries):
            return
        self._remote_cursor_index = event.cursor_row
        if self.active_pane == "remote":
            self._show_remote_details(self.remote_entries[event.cursor_row])

    @on(DataTable.RowHighlighted, "#local-table")
    def on_local_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if not self._valid_row(event.cursor_row, self.local_entries):
            return
        self._local_cursor_index = event.cursor_row
        if self.active_pane == "local":
            self._show_local_details(self.local_entries[event.cursor_row])

    @on(DataTable.RowSelected, "#remote-table")
    def on_remote_row_selected(self, event: DataTable.RowSelected) -> None:
        # DataTable consumes Enter for RowSelected, so open from here.
        if self._valid_row(event.cursor_row, self.remote_entries):
            self._remote_cursor_index = event.cursor_row
        self.active_pane = "remote"
        self._update_pane_styles()
        self._open_remote_selected()

    @on(DataTable.RowSelected, "#local-table")
    def on_local_row_selected(self, event: DataTable.RowSelected) -> None:
        if self._valid_row(event.cursor_row, self.local_entries):
            self._local_cursor_index = event.cursor_row
        self.active_pane = "local"
        self._update_pane_styles()
        self._open_local_selected()

    def action_switch_pane(self) -> None:
        if self.active_pane == "remote":
            self.active_pane = "local"
            self.query_one("#local-table", DataTable).focus()
            self._show_local_details(self._selected_local_entry())
        else:
            self.active_pane = "remote"
            self.query_one("#remote-table", DataTable).focus()
            self._show_remote_details(self._selected_remote_entry())
        self._update_pane_styles()
        self._restore_status()

    def action_refresh(self) -> None:
        if self.active_pane == "remote":
            self.refresh_remote_listing()
            self._set_status("Remote listing refreshed", transient=True)
        else:
            self.refresh_local_listing()
            self._set_status("Local listing refreshed", transient=True)

    def action_go_up(self) -> None:
        if self.active_pane == "remote":
            assert self.session is not None
            parent = self.session.parent_dir()
            if parent == self.session.cwd:
                self._set_status("Already at remote filesystem root", transient=True)
                return
            self.session.chdir(parent)
            self.refresh_remote_listing()
            self._set_status(f"Remote directory: {self.session.cwd}", transient=True)
            return

        parent = self.local_browser.parent_dir()
        if parent == self.local_browser.cwd:
            self._set_status("Already at local filesystem root", transient=True)
            return
        self.local_browser.cwd = parent
        self.refresh_local_listing()
        self._set_status(f"Local directory: {self.local_browser.cwd}", transient=True)

    def action_open_selected(self) -> None:
        if self.active_pane == "remote":
            self._open_remote_selected()
        else:
            self._open_local_selected()

    def _open_remote_selected(self) -> None:
        entry = self._selected_remote_entry()
        if entry is None:
            self._set_status("No remote entry selected", transient=True)
            return
        if entry.is_dir:
            assert self.session is not None
            try:
                self.session.chdir(entry.path)
                self.refresh_remote_listing()
                self._set_status(f"Remote directory: {self.session.cwd}", transient=True)
            except TNFSError as exc:
                self._set_status(f"Cannot enter directory: {exc}", transient=True)
            return

        try:
            assert self.session is not None
            data = self.session.read_file(entry.path)
            preview = data[:4000]
            text = preview.decode("utf-8", errors="replace")
            details = self.query_one("#details", RichLog)
            details.clear()
            details.write(f"[bold]{entry.path}[/bold] ({len(data)} bytes)")
            if len(data) > len(preview):
                details.write("[dim]Showing first 4000 bytes[/dim]")
            details.write("")
            details.write(text)
            self._set_status(f"Opened {entry.name}", transient=True)
        except TNFSError as exc:
            self._set_status(f"Open failed: {exc}", transient=True)

    def _open_local_selected(self) -> None:
        entry = self._selected_local_entry()
        if entry is None:
            return
        if entry.is_dir:
            self.local_browser.chdir(entry.path)
            self.refresh_local_listing()
            self._set_status(f"Local directory: {self.local_browser.cwd}", transient=True)
            return
        self._show_local_details(entry)
        self._set_status(f"Selected {entry.name}", transient=True)

    def action_download_selected(self) -> None:
        if self.active_pane != "remote":
            self._set_status("Switch to the remote pane to download (Tab)", transient=True)
            return
        entry = self._selected_remote_entry()
        if entry is None:
            self._set_status("No remote entry selected", transient=True)
            return
        if entry.name == "..":
            self._set_status("Cannot download '..'", transient=True)
            return
        destination = (self.local_browser.cwd / entry.name).resolve()
        kind = "directory" if entry.is_dir else "file"
        self._set_busy(f"Downloading {kind} {entry.name} -> {destination}")
        self._download_entry(entry, destination)

    @work(thread=True, exclusive=True)
    def _download_entry(self, entry: RemoteEntry, destination: Path) -> None:
        assert self.session is not None
        try:
            summary = self.session.download_tree(entry.path, destination)
            self.call_from_thread(self._finish_download, summary)
        except (TNFSError, OSError) as exc:
            self.call_from_thread(self._fail_transfer, f"Download failed: {exc}")

    def _finish_download(self, summary) -> None:
        self.refresh_local_listing()
        self._clear_busy(
            f"Downloaded {summary.files} file(s), {summary.directories} dir(s), "
            f"{summary.bytes_transferred} bytes to {summary.destination}",
            transient=True,
        )

    def action_upload_selected(self) -> None:
        if self.active_pane != "local":
            self._set_status("Switch to the local pane to upload (Tab)", transient=True)
            return
        entry = self._selected_local_entry()
        if entry is None:
            self._set_status("No local entry selected", transient=True)
            return
        if entry.name == "..":
            self._set_status("Cannot upload '..'", transient=True)
            return
        assert self.session is not None
        remote_path = f"{self.session.cwd.rstrip('/')}/{entry.name}"
        kind = "directory" if entry.is_dir else "file"
        self._set_busy(f"Uploading {kind} {entry.name} to {remote_path}...")
        self._upload_entry(entry, remote_path)

    @work(thread=True, exclusive=True)
    def _upload_entry(self, entry: LocalEntry, remote_path: str) -> None:
        assert self.session is not None
        try:
            summary = self.session.upload_tree(entry.path, remote_path)
            self.call_from_thread(self._finish_upload, summary)
        except (TNFSError, OSError) as exc:
            self.call_from_thread(self._fail_transfer, f"Upload failed: {exc}")

    def _finish_upload(self, summary) -> None:
        self.refresh_remote_listing()
        self._clear_busy(
            f"Uploaded {summary.files} file(s), {summary.directories} dir(s), "
            f"{summary.bytes_transferred} bytes to {summary.destination}",
            transient=True,
        )

    def _fail_transfer(self, message: str) -> None:
        self._clear_busy(message, transient=True)

    def action_mkdir(self) -> None:
        where = "remote" if self.active_pane == "remote" else "local"
        self.push_screen(
            DirectoryNamePrompt(f"Create {where} directory"),
            self._on_mkdir_name,
        )

    def _on_mkdir_name(self, name: str | None) -> None:
        if not name:
            return
        try:
            if self.active_pane == "remote":
                assert self.session is not None
                created = self.session.mkdir(name)
                self.refresh_remote_listing()
                self._set_status(f"Created remote directory {created}", transient=True)
            else:
                path = self.local_browser.resolve(name)
                path.mkdir(parents=False, exist_ok=False)
                self.refresh_local_listing()
                self._set_status(f"Created local directory {path}", transient=True)
        except (TNFSError, OSError, FileExistsError) as exc:
            self._set_status(f"mkdir failed: {exc}", transient=True)

    def action_delete_selected(self) -> None:
        if self.active_pane == "remote":
            entry = self._selected_remote_entry()
            if entry is None:
                return
            if entry.name == "..":
                self._set_status("Cannot delete '..'", transient=True)
                return
            assert self.session is not None
            try:
                if entry.is_dir:
                    self.session.rmdir(entry.path)
                    self._set_status(f"Removed remote directory {entry.path}", transient=True)
                else:
                    self.session.unlink(entry.path)
                    self._set_status(f"Removed remote file {entry.path}", transient=True)
                self.refresh_remote_listing()
            except TNFSError as exc:
                self._set_status(f"Delete failed: {exc}", transient=True)
            return

        entry = self._selected_local_entry()
        if entry is None:
            return
        if entry.name == "..":
            self._set_status("Cannot delete '..'", transient=True)
            return
        if entry.is_dir:
            self._set_status("Local directory delete is not supported", transient=True)
            return
        try:
            entry.path.unlink()
            self.refresh_local_listing()
            self._set_status(f"Removed local file {entry.path}", transient=True)
        except OSError as exc:
            self._set_status(f"Delete failed: {exc}", transient=True)

    def action_focus_command(self) -> None:
        self.query_one("#command-input", Input).focus()

    @on(Input.Submitted, "#command-input")
    def on_command_submitted(self, event: Input.Submitted) -> None:
        line = event.value.strip()
        event.input.value = ""
        if not line:
            return

        runner = _TUICommandRunner(self)
        try:
            message = runner.run(line)
            if message:
                self._set_status(message, transient=True)
            if runner.touched_remote:
                self.refresh_remote_listing()
            if runner.touched_local:
                self.refresh_local_listing()
        except (TNFSError, ValueError, FileNotFoundError, OSError) as exc:
            self._set_status(str(exc), transient=True)


class _TUICommandRunner:
    """Run commands from the TUI command bar."""

    def __init__(self, app: TNFSBrowser):
        self.app = app
        self.touched_remote = False
        self.touched_local = False

    @property
    def session(self) -> RemoteSession:
        assert self.app.session is not None
        return self.app.session

    def run(self, line: str) -> str:
        import shlex

        parts = shlex.split(line)
        command = parts[0].lower()
        args = parts[1:]

        if command == "ls":
            return "Use the file panes; refresh with 'r'"

        if command == "cd":
            if self.app.active_pane == "local":
                target = args[0] if args else str(Path.home())
                self.app.local_browser.chdir(target)
                self.touched_local = True
                return f"Local directory: {self.app.local_browser.cwd}"
            target = args[0] if args else "/"
            self.session.chdir(target)
            self.touched_remote = True
            return f"Remote directory: {self.session.cwd}"

        if command == "pwd":
            if self.app.active_pane == "local":
                return str(self.app.local_browser.cwd)
            return self.session.cwd

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
            local = Path(paths[1]) if len(paths) > 1 else self.app.local_browser.cwd / Path(remote).name
            _, info = self.session.stat(remote)
            if info.is_dir and not recursive:
                raise ValueError(f"{remote!r} is a directory; use: get -r {remote}")
            summary = self.session.download_tree(remote, local)
            self.touched_local = True
            return (
                f"Downloaded {summary.files} file(s), {summary.directories} dir(s), "
                f"{summary.bytes_transferred} bytes to {summary.destination}"
            )

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
            self.touched_remote = True
            return (
                f"Uploaded {summary.files} file(s), {summary.directories} dir(s), "
                f"{summary.bytes_transferred} bytes to {summary.destination}"
            )

        if command == "mkdir":
            if not args:
                raise ValueError("usage: mkdir <path>")
            if self.app.active_pane == "local":
                path = self.app.local_browser.resolve(args[0])
                path.mkdir(parents=True, exist_ok=True)
                self.touched_local = True
                return f"Created local directory {path}"
            created = self.session.mkdir(args[0])
            self.touched_remote = True
            return f"Created remote directory {created}"

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
            if self.app.active_pane == "local":
                path = self.app.local_browser.resolve(paths[0])
                if path.is_dir():
                    if not recursive:
                        raise ValueError(f"{path} is a directory; use: rm -r {paths[0]}")
                    import shutil

                    shutil.rmtree(path)
                    self.touched_local = True
                    return f"Removed local directory tree {path}"
                path.unlink()
                self.touched_local = True
                return f"Removed local file {path}"
            summary = self.session.remove(paths[0], recursive=recursive)
            self.touched_remote = True
            if summary.directories and not summary.files:
                return f"Removed directory {summary.source}"
            if summary.directories:
                return (
                    f"Removed {summary.files} file(s) and {summary.directories} dir(s) "
                    f"under {summary.source}"
                )
            return f"Removed file {summary.source}"

        if command == "rmdir":
            if not args:
                raise ValueError("usage: rmdir <path>")
            removed = self.session.rmdir(args[0])
            self.touched_remote = True
            return f"Removed remote directory {removed}"

        raise ValueError(f"Unknown command: {command}")


def run_tui(
    host: str,
    port: int = 16384,
    transport: str | None = None,
    mount_path: str = "/",
    local_dir: str | Path | None = None,
) -> int:
    import sys

    print(f"Connecting to {host}:{port}...", flush=True)
    try:
        session = RemoteSession(
            host=host,
            port=port,
            transport=transport,
            mount_path=mount_path,
            timeout=5.0,
        )
    except (TNFSError, OSError, TimeoutError) as exc:
        print(f"Connection failed: {exc}", file=sys.stderr)
        if host == "localhost":
            print(
                "Tip: default host is localhost. Pass your server explicitly, e.g.\n"
                "  ./scripts/tnfs-tui --host tnfs.home.lab",
                file=sys.stderr,
            )
        return 1

    print(f"Connected via {session.transport} (TNFS {session.version})")
    try:
        app = TNFSBrowser(
            host=host,
            port=port,
            transport=transport,
            mount_path=mount_path,
            local_dir=local_dir,
            session=session,
        )
        app.run()
    finally:
        session.close()
    return 0

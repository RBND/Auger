"""
Main Tkinter application window: layout, tabs, and wiring to AugerService.

This module is a *view*: it builds widgets, forwards user actions to
``core.service.AugerService`` and renders the events the service emits.
All file, download and process logic lives in the service.
"""

import queue
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Dict, List, Optional

from core import __version__
from core.config_schema import CHOICE, FIELDS_BY_KEY, GROUPS
from core.service import AugerService, ServiceError, normalize_sandbox_code
from core.settings_store import get_saved_value
from core.utils import open_folder, server_binary_name
from gui.views import (
    UI_FONT,
    LoggerTextBox,
    SandboxCodeHelpDialog,
    SteamCMDMissingModal,
    bind_mousewheel,
    disable_combobox_wheel,
)

PLATFORM_OPTIONS = ["Steam", "EOS", "XBL", "PSN"]
SERVER_BRANCH_STABLE = "Stable (public)"
SERVER_BRANCH_EXPERIMENTAL = "Latest Experimental"
SERVER_BRANCH_CUSTOM = "Custom branch"
SERVER_BRANCH_OPTIONS = [
    SERVER_BRANCH_STABLE,
    SERVER_BRANCH_EXPERIMENTAL,
    SERVER_BRANCH_CUSTOM,
]
SERVER_BRANCH_VALUES = {
    SERVER_BRANCH_STABLE: "public",
    SERVER_BRANCH_EXPERIMENTAL: "latest_experimental",
}

ADMIN_PERMISSION_LEVELS = ["0 (Superadmin)", "10 (Admin)", "100 (Moderator)", "1000 (Player)"]
ADMIN_PERMISSION_VALUES = ["0", "10", "100", "1000"]

ADMIN_SECTION_META: Dict[str, str] = {
    "users": (
        "Admins and moderators with elevated permissions. Supports individual users and Steam groups. "
        "Users not listed here default to permission level 1000."
    ),
    "whitelist": (
        "Whitelist-only mode activates when any entry exists here. When active, only listed users "
        "and admins can join the server."
    ),
    "blacklist": (
        "Banned players. Use unbandate for temporary bans (format: YYYY-MM-DD HH:MM:SS) or a far-future "
        "date for permanent bans."
    ),
    "commands": (
        "Console command permission overrides. Commands not listed default to permission level 0. "
        "A user may run any command at or above their permission level."
    ),
}

ADMIN_COLUMN_META: Dict[str, str] = {
    "platform": "Platform: Steam, EOS, XBL, or PSN",
    "userid": "User ID on that platform (SteamID64 for Steam, EOS ID for EOS, etc.)",
    "name": "Optional display name for reference only",
    "permission_level": "0-1000 (0=superadmin, 1000=default player)",
    "unbandate": "Ban expiry date: YYYY-MM-DD HH:MM:SS",
    "reason": "Optional ban reason shown in logs",
    "cmd": "Console command name (e.g. kick, ban, giveself)",
}

ADMIN_SECTIONS = ("users", "whitelist", "blacklist", "commands")


def _perm_display(val: str) -> str:
    """Convert a raw permission level string to a display string."""
    mapping = {"0": "0 (Superadmin)", "10": "10 (Admin)", "100": "100 (Moderator)", "1000": "1000 (Player)"}
    return mapping.get(str(val), str(val))


def _perm_raw(display: str) -> str:
    """Convert a display string back to a raw permission level."""
    return display.split(" ")[0]


class MainWindow:
    """
    Main application UI class managing notebook tabs, path configuration,
    server control buttons, XML configuration editor, and service events.
    """

    def __init__(self, root: tk.Tk, service: Optional[AugerService] = None):
        self.root = root
        self.root.title("7 Days to Die - Dedicated Server Manager")
        self.root.geometry("1000x800")
        self.root.minsize(860, 680)

        # Application core (all business logic) + its thread-safe event queue
        self.service = service or AugerService(queue.Queue())
        self.tool_name: str = self.service.tool_name

        # Form state
        self.form_entries: Dict[str, Any] = {}   # ttk.Entry OR ttk.Combobox
        self.form_vars: Dict[str, tk.StringVar] = {}
        self._busy_widgets: List[ttk.Widget] = []
        self._busy = False

        # Admin tab row tracking
        self._admin_rows: Dict[str, List[Dict[str, Any]]] = {key: [] for key in ADMIN_SECTIONS}

        # UI StringVars for path displays and status indicators
        self.tool_path_var = tk.StringVar(value="Searching...")
        self.tool_status_var = tk.StringVar(value="Checking...")
        self.server_path_var = tk.StringVar(value="Searching...")
        self.server_status_var = tk.StringVar(value="Checking...")
        self.server_runtime_var = tk.StringVar(value="Stopped")
        self.progress_label_var = tk.StringVar(value="")
        self.config_file_var = tk.StringVar(value="")

        saved_branch = str(get_saved_value("server_branch", "public")).strip()
        if saved_branch == "public":
            saved_branch_choice = SERVER_BRANCH_STABLE
            custom_branch = ""
        elif saved_branch == "latest_experimental":
            saved_branch_choice = SERVER_BRANCH_EXPERIMENTAL
            custom_branch = ""
        else:
            saved_branch_choice = SERVER_BRANCH_CUSTOM
            custom_branch = saved_branch
        self.server_branch_choice_var = tk.StringVar(value=saved_branch_choice)
        self.custom_branch_var = tk.StringVar(value=custom_branch)
        self.beta_password_var = tk.StringVar()
        self.validate_server_files_var = tk.BooleanVar(
            value=bool(get_saved_value("validate_server_files", False))
        )

        self._build_ui()

        # Start periodic event polling loop
        self.root.after(50, self.poll_events)

        # Run initial auto-detection
        self.root.after(200, lambda: self.service.detect_async(on_done=self._after_detection))

        # Track whether the server we started is still running
        self.root.after(2000, self._poll_server_process)

    def _build_ui(self) -> None:
        """Constructs the notebook tabbed layout."""
        disable_combobox_wheel(self.root)

        header_frame = ttk.Frame(self.root, padding=12)
        header_frame.pack(fill=tk.X)

        ttk.Label(
            header_frame,
            text="🎮 7 Days to Die - Dedicated Server Manager",
            font=(UI_FONT, 14, "bold"),
        ).pack(side=tk.LEFT)

        ttk.Label(
            header_frame,
            text=f"v{__version__}",
            font=(UI_FONT, 9, "italic"),
        ).pack(side=tk.RIGHT, padx=5)

        ttk.Separator(self.root, orient=tk.HORIZONTAL).pack(fill=tk.X)

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.tab_control = ttk.Frame(self.notebook, padding=10)
        self.tab_config = ttk.Frame(self.notebook, padding=10)
        self.tab_admin = ttk.Frame(self.notebook, padding=10)
        self.tab_logs = ttk.Frame(self.notebook, padding=10)

        self.notebook.add(self.tab_control, text=" 🚀 Server Control & Setup ")
        self.notebook.add(self.tab_config, text=" ⚙️ Config Editor ")
        self.notebook.add(self.tab_admin, text=" 🛡️ Server Admin ")
        self.notebook.add(self.tab_logs, text=" 📜 Live Logs ")

        self._build_control_tab()
        self._build_config_tab()
        self._build_admin_tab()
        self._build_logs_tab()

    # ------------------------------------------------------------------
    # TAB 1: SERVER CONTROL & SETUP
    # ------------------------------------------------------------------
    def _build_control_tab(self) -> None:
        paths_group = ttk.LabelFrame(self.tab_control, text=" Installation Paths & Detection ", padding=12)
        paths_group.pack(fill=tk.X, pady=(0, 10))

        r1 = ttk.Frame(paths_group)
        r1.pack(fill=tk.X, pady=4)
        ttk.Label(r1, text=f"{self.tool_name} Location:", width=22, anchor=tk.W).pack(side=tk.LEFT)
        ttk.Entry(r1, textvariable=self.tool_path_var, state="readonly").pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(r1, text="📁 Browse", command=self.browse_tool).pack(side=tk.LEFT, padx=2)
        ttk.Button(r1, text="📂 Open Folder", command=self.open_tool_folder).pack(side=tk.LEFT, padx=2)

        r2 = ttk.Frame(paths_group)
        r2.pack(fill=tk.X, pady=4)
        ttk.Label(r2, text="7DTD Server Folder:", width=22, anchor=tk.W).pack(side=tk.LEFT)
        ttk.Entry(r2, textvariable=self.server_path_var, state="readonly").pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        browse_server_btn = ttk.Button(r2, text="📁 Browse", command=self.browse_server_dir)
        browse_server_btn.pack(side=tk.LEFT, padx=2)
        ttk.Button(r2, text="📂 Open Folder", command=self.open_server_folder).pack(side=tk.LEFT, padx=2)

        r3 = ttk.Frame(paths_group)
        r3.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(r3, text=f"{self.tool_name} Status:", font=(UI_FONT, 9, "bold")).pack(side=tk.LEFT)
        ttk.Label(r3, textvariable=self.tool_status_var, foreground="#0066CC").pack(side=tk.LEFT, padx=(5, 30))
        ttk.Label(r3, text="7DTD Server Status:", font=(UI_FONT, 9, "bold")).pack(side=tk.LEFT)
        ttk.Label(r3, textvariable=self.server_status_var, foreground="#0066CC").pack(side=tk.LEFT, padx=5)

        actions_group = ttk.LabelFrame(self.tab_control, text=" Management Actions ", padding=12)
        actions_group.pack(fill=tk.X, pady=(0, 10))

        btn_row1 = ttk.Frame(actions_group)
        btn_row1.pack(fill=tk.X, pady=4)

        self.btn_dl_steam = ttk.Button(
            btn_row1, text=f"⬇️ Download / Update {self.tool_name}", command=self.action_download_tool,
        )
        self.btn_dl_steam.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)

        self.btn_dl_server = ttk.Button(
            btn_row1, text="🎮 Install / Update 7DTD Dedicated Server", command=self.action_install_server,
        )
        self.btn_dl_server.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)

        progress_row = ttk.Frame(actions_group)
        progress_row.pack(fill=tk.X, pady=(6, 0))
        self.progress_bar = ttk.Progressbar(progress_row, mode="determinate", maximum=100)
        self.progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        ttk.Label(progress_row, textvariable=self.progress_label_var, width=28).pack(side=tk.LEFT, padx=4)

        version_group = ttk.LabelFrame(
            self.tab_control, text=" Server Version ", padding=12
        )
        version_group.pack(fill=tk.X, pady=(0, 10))

        version_row = ttk.Frame(version_group)
        version_row.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(version_row, text="Version / branch:", width=22, anchor=tk.W).pack(side=tk.LEFT)
        self.server_branch_selector = ttk.Combobox(
            version_row,
            textvariable=self.server_branch_choice_var,
            values=SERVER_BRANCH_OPTIONS,
            state="readonly",
            width=24,
        )
        self.server_branch_selector.pack(side=tk.LEFT, padx=(0, 12))
        self.server_branch_selector.bind("<<ComboboxSelected>>", self._on_branch_selection_changed)
        ttk.Checkbutton(
            version_row,
            text="Verify all game files (slower; your settings are kept)",
            variable=self.validate_server_files_var,
        ).pack(side=tk.LEFT)

        custom_row = ttk.Frame(version_group)
        custom_row.pack(fill=tk.X, pady=2)
        ttk.Label(custom_row, text="Custom branch:", width=22, anchor=tk.W).pack(side=tk.LEFT)
        self.custom_branch_entry = ttk.Entry(
            custom_row, textvariable=self.custom_branch_var, width=28
        )
        self.custom_branch_entry.pack(side=tk.LEFT, padx=(0, 12))
        ttk.Label(custom_row, text="Use only a branch published by the game developer.").pack(side=tk.LEFT)

        password_row = ttk.Frame(version_group)
        password_row.pack(fill=tk.X, pady=(2, 0))
        ttk.Label(password_row, text="Beta password:", width=22, anchor=tk.W).pack(side=tk.LEFT)
        ttk.Entry(password_row, textvariable=self.beta_password_var, show="•", width=28).pack(
            side=tk.LEFT, padx=(0, 12)
        )
        ttk.Label(password_row, text="Optional. Never saved or shown in logs.").pack(side=tk.LEFT)
        self._on_branch_selection_changed()

        launch_group = ttk.LabelFrame(self.tab_control, text=" Quick Launch ", padding=12)
        launch_group.pack(fill=tk.X, pady=(0, 10))

        status_row = ttk.Frame(launch_group)
        status_row.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(status_row, text="Server is:", font=(UI_FONT, 9, "bold")).pack(side=tk.LEFT)
        self.server_runtime_label = ttk.Label(
            status_row, textvariable=self.server_runtime_var, foreground="#7F8C8D",
            font=(UI_FONT, 9, "bold"),
        )
        self.server_runtime_label.pack(side=tk.LEFT, padx=5)

        self.btn_start_server = ttk.Button(
            launch_group, text="🚀 START 7DTD SERVER", command=self.action_start_server,
        )
        self.btn_start_server.pack(fill=tk.X, ipady=8)

        # Buttons that must not be used while a download/install is running.
        self._busy_widgets = [
            self.btn_dl_steam, self.btn_dl_server, self.btn_start_server, browse_server_btn,
        ]

        log_preview_group = ttk.LabelFrame(self.tab_control, text=" Recent Activity ", padding=8)
        log_preview_group.pack(fill=tk.BOTH, expand=True)

        self.mini_logger = LoggerTextBox(log_preview_group)
        self.mini_logger.pack(fill=tk.BOTH, expand=True)

    # ------------------------------------------------------------------
    # TAB 2: CONFIG EDITOR
    # ------------------------------------------------------------------
    def _build_config_tab(self) -> None:
        # Action toolbar at bottom (packed first to anchor at BOTTOM)
        btn_bar = ttk.Frame(self.tab_config, padding=8)
        btn_bar.pack(side=tk.BOTTOM, fill=tk.X)

        ttk.Button(btn_bar, text="💾 Save Config", command=self.save_config).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_bar, text="📋 Reload Config", command=self.load_config_into_ui).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_bar, text="🔄 Reset to Defaults", command=self.reset_config).pack(side=tk.RIGHT, padx=5)

        ttk.Label(
            self.tab_config, textvariable=self.config_file_var,
            font=(UI_FONT, 8, "italic"), foreground="#7F8C8D",
        ).pack(side=tk.BOTTOM, anchor=tk.W, padx=8)

        ttk.Separator(self.tab_config, orient=tk.HORIZONTAL).pack(side=tk.BOTTOM, fill=tk.X, pady=(0, 4))

        # Scrollable canvas
        canvas = tk.Canvas(self.tab_config, borderwidth=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.tab_config, orient="vertical", command=canvas.yview)
        scroll_frame = ttk.Frame(canvas, padding=10)

        scroll_frame.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas_win = canvas.create_window((0, 0), window=scroll_frame, anchor="nw")

        def _on_canvas_resize(event: tk.Event) -> None:
            canvas.itemconfig(canvas_win, width=event.width)

        canvas.bind("<Configure>", _on_canvas_resize)
        canvas.configure(yscrollcommand=scrollbar.set)

        # Mouse wheel scrolling (only while the pointer is over this tab's canvas)
        bind_mousewheel(canvas)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Build all groups from the schema
        for group in GROUPS:
            gbox = ttk.LabelFrame(scroll_frame, text=f" {group.display_title} ", padding=10)
            gbox.pack(fill=tk.X, expand=True, pady=4)

            gbox.columnconfigure(0, weight=0, minsize=220)
            gbox.columnconfigure(1, weight=1, minsize=180)
            gbox.columnconfigure(2, weight=2)

            for idx, key in enumerate(group.keys):
                spec = FIELDS_BY_KEY[key]

                lbl = ttk.Label(gbox, text=spec.label, anchor=tk.W)
                lbl.grid(row=idx, column=0, sticky="w", padx=(0, 8), pady=3)

                var = tk.StringVar()
                self.form_vars[key] = var

                if spec.kind == CHOICE:
                    widget = ttk.Combobox(
                        gbox,
                        textvariable=var,
                        values=spec.choice_values,
                        state="readonly",
                    )
                else:
                    widget = ttk.Entry(gbox, textvariable=var)

                widget.grid(row=idx, column=1, sticky="ew", padx=(0, 8), pady=3)
                self.form_entries[key] = widget

                tip_lbl = ttk.Label(
                    gbox,
                    text=spec.help,
                    font=(UI_FONT, 8, "italic"),
                    foreground="#7F8C8D",
                    wraplength=320,
                    justify=tk.LEFT,
                )
                tip_lbl.grid(row=idx, column=2, sticky="w", pady=3)

            if "SandboxCode" in group.keys:
                self._add_sandbox_helpers(gbox, row=len(group.keys))

    def _add_sandbox_helpers(self, parent: ttk.LabelFrame, row: int) -> None:
        """Paste + how-to buttons under the Sandbox Code field."""
        helper_row = ttk.Frame(parent)
        helper_row.grid(row=row, column=1, columnspan=2, sticky="w", pady=(2, 3))
        ttk.Button(
            helper_row, text="📋 Paste from Clipboard", command=self.paste_sandbox_code
        ).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(
            helper_row, text="❓ How do I get a code?",
            command=lambda: SandboxCodeHelpDialog(self.root),
        ).pack(side=tk.LEFT)

    def paste_sandbox_code(self) -> None:
        try:
            raw = self.root.clipboard_get()
        except tk.TclError:
            messagebox.showwarning(
                "Clipboard Empty",
                "Nothing to paste. In the game's Sandbox Options screen, click Copy first.",
                parent=self.root,
            )
            return
        code = normalize_sandbox_code(raw)
        if not code:
            messagebox.showwarning(
                "Not a Sandbox Code",
                "The clipboard doesn't contain a Sandbox Code. Copy it from the game's "
                "Sandbox Options screen and try again.",
                parent=self.root,
            )
            return
        self.form_vars["SandboxCode"].set(code)
        self.log_message("Sandbox Code pasted. Click 💾 Save Config to apply it.", "SUCCESS")

    # ------------------------------------------------------------------
    # TAB 3: SERVER ADMIN
    # ------------------------------------------------------------------
    def _build_admin_tab(self) -> None:
        # Bottom button bar
        btn_bar = ttk.Frame(self.tab_admin, padding=8)
        btn_bar.pack(side=tk.BOTTOM, fill=tk.X)

        ttk.Button(btn_bar, text="💾 Save Admin File", command=self.save_admin).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_bar, text="📋 Reload", command=self.load_admin_into_ui).pack(side=tk.LEFT, padx=5)

        ttk.Separator(self.tab_admin, orient=tk.HORIZONTAL).pack(side=tk.BOTTOM, fill=tk.X, pady=(0, 4))

        # Scrollable canvas
        canvas = tk.Canvas(self.tab_admin, borderwidth=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.tab_admin, orient="vertical", command=canvas.yview)
        scroll_frame = ttk.Frame(canvas, padding=8)

        scroll_frame.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas_win = canvas.create_window((0, 0), window=scroll_frame, anchor="nw")

        def _on_canvas_resize(event: tk.Event) -> None:
            canvas.itemconfig(canvas_win, width=event.width)

        canvas.bind("<Configure>", _on_canvas_resize)
        canvas.configure(yscrollcommand=scrollbar.set)

        bind_mousewheel(canvas)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Store reference for rebuilding sections
        self._admin_scroll_frame = scroll_frame

        # Build admin sections
        self._build_admin_section(
            scroll_frame, "users", "👑 Users (Admins / Mods)",
            columns=["Platform", "User ID", "Display Name (optional)", "Permission Level"],
            col_keys=["platform", "userid", "name", "permission_level"],
            use_perm_dropdown=True,
            use_platform_dropdown=True,
        )

        self._build_admin_section(
            scroll_frame, "whitelist", "✅ Whitelist",
            columns=["Platform", "User ID", "Display Name (optional)"],
            col_keys=["platform", "userid", "name"],
            use_perm_dropdown=False,
            use_platform_dropdown=True,
        )

        self._build_admin_section(
            scroll_frame, "blacklist", "🚫 Blacklist",
            columns=["Platform", "User ID", "Display Name (optional)", "Unban Date", "Reason"],
            col_keys=["platform", "userid", "name", "unbandate", "reason"],
            use_perm_dropdown=False,
            use_platform_dropdown=True,
        )

        self._build_admin_section(
            scroll_frame, "commands", "🔧 Command Permissions",
            columns=["Command", "Permission Level"],
            col_keys=["cmd", "permission_level"],
            use_perm_dropdown=True,
            use_platform_dropdown=False,
        )

    def _build_admin_section(
        self,
        parent: ttk.Frame,
        section_key: str,
        title: str,
        columns: List[str],
        col_keys: List[str],
        use_perm_dropdown: bool,
        use_platform_dropdown: bool = False,
    ) -> None:
        """Build a single admin section with description and column tooltips."""
        frame = ttk.LabelFrame(parent, text=f" {title} ", padding=10)
        frame.pack(fill=tk.X, expand=True, pady=6)

        section_desc = ADMIN_SECTION_META.get(section_key, "")
        if section_desc:
            ttk.Label(
                frame,
                text=section_desc,
                font=(UI_FONT, 8, "italic"),
                foreground="#7F8C8D",
                wraplength=820,
                justify=tk.LEFT,
            ).pack(anchor=tk.W, pady=(0, 8))

        header_row = ttk.Frame(frame)
        header_row.pack(fill=tk.X)
        for col_title in columns:
            ttk.Label(header_row, text=col_title, font=(UI_FONT, 9, "bold"), anchor=tk.W).pack(
                side=tk.LEFT, expand=True, fill=tk.X, padx=3
            )
        ttk.Label(header_row, text="", width=8).pack(side=tk.LEFT)

        tip_row = ttk.Frame(frame)
        tip_row.pack(fill=tk.X, pady=(2, 0))
        for key in col_keys:
            tip_text = ADMIN_COLUMN_META.get(key, "")
            ttk.Label(
                tip_row,
                text=tip_text,
                font=(UI_FONT, 8, "italic"),
                foreground="#7F8C8D",
                wraplength=160,
                justify=tk.LEFT,
            ).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=3)
        ttk.Label(tip_row, text="", width=8).pack(side=tk.LEFT)

        ttk.Separator(frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(4, 0))

        # Row container
        rows_frame = ttk.Frame(frame)
        rows_frame.pack(fill=tk.X, expand=True)

        # Store meta for dynamic row building
        self._admin_rows[section_key] = []
        self._admin_row_meta = getattr(self, "_admin_row_meta", {})
        self._admin_row_meta[section_key] = {
            "frame": rows_frame,
            "col_keys": col_keys,
            "use_perm_dropdown": use_perm_dropdown,
            "use_platform_dropdown": use_platform_dropdown,
        }

        # Add button
        btn_row = ttk.Frame(frame)
        btn_row.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(
            btn_row,
            text=f"➕ Add Entry",
            command=lambda sk=section_key: self._add_admin_row(sk),
        ).pack(side=tk.LEFT, padx=2)

    def _add_admin_row(self, section_key: str, initial_values: Optional[Dict[str, str]] = None) -> None:
        """Dynamically add a new editable row to an admin section."""
        meta = self._admin_row_meta[section_key]
        rows_frame: ttk.Frame = meta["frame"]
        col_keys: List[str] = meta["col_keys"]
        use_perm_dropdown: bool = meta["use_perm_dropdown"]
        use_platform_dropdown: bool = meta.get("use_platform_dropdown", False)

        row_frame = ttk.Frame(rows_frame)
        row_frame.pack(fill=tk.X, pady=2)

        row_vars: Dict[str, tk.StringVar] = {}

        for key in col_keys:
            var = tk.StringVar()
            initial = ""
            if initial_values:
                raw = initial_values.get(key, "")
                if key == "permission_level" and use_perm_dropdown:
                    initial = _perm_display(raw)
                else:
                    initial = raw
            if key == "platform" and not initial:
                initial = "Steam"
            var.set(initial)
            row_vars[key] = var

            if key == "permission_level" and use_perm_dropdown:
                widget = ttk.Combobox(
                    row_frame,
                    textvariable=var,
                    values=ADMIN_PERMISSION_LEVELS,
                    state="readonly",
                    width=18,
                )
            elif key == "platform" and use_platform_dropdown:
                widget = ttk.Combobox(
                    row_frame,
                    textvariable=var,
                    values=PLATFORM_OPTIONS,
                    state="readonly",
                    width=10,
                )
            else:
                widget = ttk.Entry(row_frame, textvariable=var)

            widget.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=3)

        row_record = {"frame": row_frame, "vars": row_vars}
        self._admin_rows[section_key].append(row_record)

        def _delete(rec=row_record, sk=section_key):
            rec["frame"].destroy()
            self._admin_rows[sk].remove(rec)

        ttk.Button(row_frame, text="✖", width=3, command=_delete).pack(side=tk.LEFT, padx=2)

    def _collect_admin_section(self, section_key: str) -> List[Dict[str, str]]:
        """Collect current values from all rows in a section."""
        meta = self._admin_row_meta[section_key]
        col_keys = meta["col_keys"]
        use_perm_dropdown = meta["use_perm_dropdown"]

        results = []
        for row_record in self._admin_rows[section_key]:
            entry: Dict[str, str] = {}
            for key in col_keys:
                raw_val = row_record["vars"][key].get()
                if key == "permission_level" and use_perm_dropdown:
                    raw_val = _perm_raw(raw_val)
                entry[key] = raw_val
            # Skip entirely empty rows
            primary_key = col_keys[0]
            if entry.get(primary_key, "").strip():
                results.append(entry)
        return results

    # ------------------------------------------------------------------
    # TAB 4: LIVE LOGS
    # ------------------------------------------------------------------
    def _build_logs_tab(self) -> None:
        self.main_logger = LoggerTextBox(self.tab_logs)
        self.main_logger.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        bar = ttk.Frame(self.tab_logs)
        bar.pack(fill=tk.X)

        ttk.Button(bar, text="🧹 Clear Logs", command=self.clear_logs).pack(side=tk.LEFT, padx=4)
        ttk.Button(bar, text="💾 Save Logs to File", command=self.save_logs_to_file).pack(side=tk.LEFT, padx=4)

    # ------------------------------------------------------------------
    # SERVICE EVENTS
    # ------------------------------------------------------------------
    def poll_events(self) -> None:
        """Render events from the service (runs on the Tk thread)."""
        self.service.dispatch_pending(self._handle_event, limit=200)
        self.root.after(50, self.poll_events)

    def _handle_event(self, event: tuple) -> None:
        kind = event[0]
        if kind == "log":
            _, level, message = event
            self.mini_logger.append_log(message, level)
            self.main_logger.append_log(message, level)
        elif kind == "status":
            _, component, text = event
            if component == "tool":
                self.tool_status_var.set(text)
            elif component == "server":
                self.server_status_var.set(text)
        elif kind == "progress":
            _, component, percent = event
            self._show_progress(component, percent)
        elif kind == "busy":
            self._set_busy(bool(event[1]))
        elif kind == "changed":
            what = event[1]
            if what == "tool":
                self._refresh_tool_path()
            elif what == "server":
                self._refresh_server_path()
                self._refresh_runtime()
            elif what == "config":
                self.load_config_into_ui()
            elif what == "admin":
                self.load_admin_into_ui()
            elif what == "runtime":
                self._refresh_runtime()

    def _show_progress(self, component: str, percent: Optional[float]) -> None:
        if percent is None:
            self.progress_bar["value"] = 0
            self.progress_label_var.set("")
            return
        self.progress_bar["value"] = percent
        what = self.tool_name if component == "tool" else "Server files"
        self.progress_label_var.set(f"{what}: {percent:.0f}%")

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = tk.DISABLED if busy else tk.NORMAL
        for widget in self._busy_widgets:
            try:
                widget.config(state=state)
            except tk.TclError:
                pass
        if not busy:
            self._refresh_runtime()

    def _refresh_tool_path(self) -> None:
        path = self.service.tool_path
        self.tool_path_var.set(str(path) if path else "Not installed yet")

    def _refresh_server_path(self) -> None:
        server_dir = self.service.server_dir
        suffix = "" if self.service.server_installed() else "   (not installed yet)"
        self.server_path_var.set(f"{server_dir}{suffix}")

    def _refresh_runtime(self) -> None:
        running = self.service.server_running()
        if running:
            self.server_runtime_var.set(f"Running (PID {self.service.server_pid})")
            self.server_runtime_label.config(foreground="#27AE60")
        else:
            self.server_runtime_var.set("Stopped")
            self.server_runtime_label.config(foreground="#7F8C8D")
        if not self._busy:
            can_start = (not running) and self.service.server_installed()
            self.btn_start_server.config(state=tk.NORMAL if can_start else tk.DISABLED)

    def _poll_server_process(self) -> None:
        self.service.poll_server()
        self._refresh_runtime()
        self.root.after(2000, self._poll_server_process)

    def _after_detection(self) -> None:
        self._refresh_tool_path()
        self._refresh_server_path()
        self._refresh_runtime()
        if not self.service.tool_ready():
            modal = SteamCMDMissingModal(self.root, tool_name=self.tool_name)
            self.root.wait_window(modal)
            if modal.user_choice == "download":
                self.action_download_tool()
            elif modal.user_choice == "browse" and modal.selected_path:
                self.service.set_tool_path(Path(modal.selected_path).resolve())

    def log_message(self, message: str, level: str = "INFO") -> None:
        self.mini_logger.append_log(message, level)
        self.main_logger.append_log(message, level)

    # ------------------------------------------------------------------
    # ACTIONS & EVENT HANDLERS
    # ------------------------------------------------------------------
    def browse_tool(self) -> None:
        path = filedialog.askopenfilename(
            parent=self.root,
            title=f"Select the {self.tool_name} program",
            filetypes=[(f"{self.tool_name} program", "*")],
        )
        if path:
            self.service.set_tool_path(Path(path).resolve())

    def browse_server_dir(self) -> None:
        path = filedialog.askdirectory(parent=self.root, title="Select 7DTD Server Directory")
        if path:
            self.service.set_server_dir(Path(path).resolve())

    def open_tool_folder(self) -> None:
        target = self.service.tool_path.parent if self.service.tool_ready() else self.service.default_tool_dir()
        if not open_folder(target):
            messagebox.showwarning("Folder Missing", f"Folder does not exist yet: {target}")

    def open_server_folder(self) -> None:
        target = self.service.server_dir
        if not open_folder(target):
            messagebox.showwarning("Folder Missing", f"Folder does not exist yet: {target}")

    def action_download_tool(self) -> None:
        """Download (or refresh) the download tool into its folder — no folder picker needed."""
        self.service.download_tool_async()

    def _on_branch_selection_changed(self, event: Optional[tk.Event] = None) -> None:
        """Enables or disables the custom branch entry based on current dropdown selection."""
        choice = self.server_branch_choice_var.get()
        if choice == SERVER_BRANCH_CUSTOM:
            self.custom_branch_entry.config(state=tk.NORMAL)
        else:
            self.custom_branch_entry.config(state=tk.DISABLED)

    def get_selected_branch(self) -> Optional[str]:
        """Returns the normalized branch name to download, or None if invalid."""
        choice = self.server_branch_choice_var.get()
        if choice == SERVER_BRANCH_CUSTOM:
            branch = self.custom_branch_var.get().strip()
            if not branch:
                messagebox.showerror(
                    "Branch Name Required",
                    "Please enter a valid custom branch name or select Stable / Latest Experimental.",
                )
                return None
            return branch
        return SERVER_BRANCH_VALUES.get(choice, "public")

    def action_install_server(self) -> None:
        """Install or update the server into the current server folder — no folder picker needed.

        Use the Browse button next to "7DTD Server Folder" first to pick a different location.
        """
        branch = self.get_selected_branch()
        if not branch:
            return
        try:
            self.service.install_server_async(
                branch=branch,
                beta_password=self.beta_password_var.get().strip() or None,
                validate=self.validate_server_files_var.get(),
            )
        except ServiceError as err:
            messagebox.showerror("Can't Install Yet", str(err))

    def action_start_server(self) -> None:
        try:
            self.service.start_server()
        except ServiceError as err:
            messagebox.showerror("Launch Failed", str(err))
        self._refresh_runtime()

    # ------------------------------------------------------------------
    # CONFIGURATION
    # ------------------------------------------------------------------
    def load_config_into_ui(self) -> None:
        try:
            settings = self.service.load_config()
        except Exception as err:
            self.log_message(f"Error loading config: {err}", "ERROR")
            return
        if settings is None:
            for var in self.form_vars.values():
                var.set("")
            self.config_file_var.set(
                f"Settings appear here once the server is installed ({server_binary_name()} not found yet)."
            )
            return
        for key, var in self.form_vars.items():
            var.set(settings.get(key, ""))
        self.config_file_var.set(f"Editing: {self.service.config_path}")

    def save_config(self) -> None:
        values = {key: var.get() for key, var in self.form_vars.items()}
        try:
            saved = self.service.save_config(values)
        except ServiceError as err:
            messagebox.showerror("Can't Save Settings", str(err))
            return
        except Exception as err:
            self.log_message(f"Error saving config: {err}", "ERROR")
            messagebox.showerror("Save Failed", f"Could not save configuration: {err}")
            return
        if "SandboxCode" in saved:
            self.form_vars["SandboxCode"].set(saved["SandboxCode"])
        messagebox.showinfo("Config Saved", "Settings saved!\nA backup copy was created.")

    def reset_config(self) -> None:
        confirm = messagebox.askyesno(
            "Confirm Reset",
            "Are you sure you want to reset the server settings to defaults?\n\n"
            "A backup copy of your existing configuration will be saved, and your worlds stay where they are.",
            icon="warning",
        )
        if not confirm:
            return
        try:
            self.service.reset_config()
        except ServiceError as err:
            messagebox.showerror("Can't Reset", str(err))
            return
        except Exception as err:
            self.log_message(f"Error resetting config: {err}", "ERROR")
            return
        messagebox.showinfo("Reset Complete", "Configuration successfully restored to default settings.")

    # ------------------------------------------------------------------
    # ADMIN FILE
    # ------------------------------------------------------------------
    def load_admin_into_ui(self) -> None:
        """Populate all admin section rows from the service's admin lists."""
        # Clear existing rows in each section
        for section_key in ADMIN_SECTIONS:
            for row_record in list(self._admin_rows[section_key]):
                row_record["frame"].destroy()
            self._admin_rows[section_key] = []

        if not self.service.admin_ready():
            return

        admin = self.service.admin
        for section_key, entries in (
            ("users", admin.users),
            ("whitelist", admin.whitelist),
            ("blacklist", admin.blacklist),
            ("commands", admin.commands),
        ):
            for entry in entries:
                self._add_admin_row(section_key, initial_values=entry)

    def save_admin(self) -> None:
        try:
            self.service.save_admin(
                users=self._collect_admin_section("users"),
                whitelist=self._collect_admin_section("whitelist"),
                blacklist=self._collect_admin_section("blacklist"),
                commands=self._collect_admin_section("commands"),
            )
        except ServiceError as err:
            messagebox.showerror("Can't Save Admin File", str(err))
            return
        messagebox.showinfo("Admin Saved", "serveradmin.xml successfully updated!\nA backup was created.")

    # ------------------------------------------------------------------
    # LOG UTILITIES
    # ------------------------------------------------------------------
    def clear_logs(self) -> None:
        self.mini_logger.clear_logs()
        self.main_logger.clear_logs()

    def save_logs_to_file(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Save Log File",
            defaultextension=".txt",
            filetypes=[("Text File", "*.txt"), ("Log File", "*.log"), ("All Files", "*.*")],
        )
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(self.main_logger.get_logs())
                messagebox.showinfo("Logs Saved", f"Logs successfully saved to {path}")
            except Exception as err:
                messagebox.showerror("Error", f"Failed to save logs: {err}")

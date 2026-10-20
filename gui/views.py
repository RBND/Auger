"""
Custom widgets, colored logger text box, and modal dialogs for Tkinter UI.
"""

import datetime
import platform
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
from typing import Literal, Optional

IS_WINDOWS = platform.system() == "Windows"
MONO_FONT = "Consolas" if IS_WINDOWS else "TkFixedFont"
UI_FONT = "Segoe UI" if IS_WINDOWS else "TkDefaultFont"


def bind_mousewheel(canvas: tk.Canvas) -> None:
    """Scroll ``canvas`` with the mouse wheel only while the pointer is over it.

    Works on Windows/macOS (<MouseWheel> with delta) and X11 (<Button-4>/<Button-5>).
    Binding globally only while hovered stops multiple canvases from stealing each
    other's wheel events.
    """

    def _on_wheel(event: tk.Event) -> None:
        if getattr(event, "num", None) == 4:
            step = -1
        elif getattr(event, "num", None) == 5:
            step = 1
        elif event.delta:
            # Windows sends multiples of 120; macOS sends small values.
            step = -1 * (event.delta // 120 if abs(event.delta) >= 120 else (1 if event.delta > 0 else -1))
        else:
            return
        canvas.yview_scroll(int(step), "units")

    def _bind(_event: tk.Event) -> None:
        canvas.bind_all("<MouseWheel>", _on_wheel)
        canvas.bind_all("<Button-4>", _on_wheel)
        canvas.bind_all("<Button-5>", _on_wheel)

    def _unbind(event: tk.Event) -> None:
        # <Leave> also fires when moving onto a child widget; only unbind when truly outside.
        try:
            widget = canvas.winfo_containing(event.x_root, event.y_root)
        except (KeyError, tk.TclError):
            widget = None
        while widget is not None:
            if widget == canvas:
                return
            widget = widget.master
        canvas.unbind_all("<MouseWheel>")
        canvas.unbind_all("<Button-4>")
        canvas.unbind_all("<Button-5>")

    canvas.bind("<Enter>", _bind)
    canvas.bind("<Leave>", _unbind)


def disable_combobox_wheel(root: tk.Misc) -> None:
    """Stop ttk dropdowns from changing value when the user scrolls past them."""
    for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
        try:
            root.unbind_class("TCombobox", sequence)
        except tk.TclError:
            pass


class LoggerTextBox(ttk.Frame):
    """
    Scrollable text widget for displaying real-time logs with colored severity tags.
    """

    MAX_LINES = 5000

    def __init__(self, parent: tk.Widget, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

        # ScrolledText widget setup
        self.text_widget = scrolledtext.ScrolledText(
            self,
            wrap=tk.WORD,
            font=(MONO_FONT, 10),
            bg="#1E1E1E",
            fg="#CCCCCC",
            insertbackground="#FFFFFF",
            relief=tk.FLAT,
            padx=8,
            pady=8,
        )
        self.text_widget.pack(fill=tk.BOTH, expand=True)

        # Configure color tags for log levels
        self.text_widget.tag_config("TIMESTAMP", foreground="#7F8C8D")
        self.text_widget.tag_config("INFO", foreground="#E0E0E0")
        self.text_widget.tag_config("SUCCESS", foreground="#2ECC71", font=(MONO_FONT, 10, "bold"))
        self.text_widget.tag_config("WARNING", foreground="#F39C12", font=(MONO_FONT, 10, "bold"))
        self.text_widget.tag_config("ERROR", foreground="#E74C3C", font=(MONO_FONT, 10, "bold"))

        self._last_was_progress = False

    def append_log(self, message: str, level: str = "INFO") -> None:
        """Appends a timestamped log line with severity color formatting."""
        self.text_widget.config(state=tk.NORMAL)

        now = datetime.datetime.now().strftime("[%H:%M:%S] ")
        tag = level.upper() if level.upper() in ("INFO", "SUCCESS", "WARNING", "ERROR") else "INFO"

        # Check if message is a progress update (e.g. "Downloading: 40%", "[ 15%]...", or "Update state ... progress:")
        msg_lower = message.lower()
        is_progress = (
            message.startswith("Downloading:")
            or (message.startswith("[") and ("%" in message or "----" in message))
            or "progress:" in msg_lower
            or "update state" in msg_lower
        )

        if is_progress and self._last_was_progress:
            try:
                self.text_widget.delete("end-2c linestart", "end-1c")
            except Exception:
                pass

        self.text_widget.insert(tk.END, now, "TIMESTAMP")
        self.text_widget.insert(tk.END, f"[{tag}] ", tag)
        self.text_widget.insert(tk.END, f"{message}\n", tag)

        self._last_was_progress = is_progress

        # Keep memory bounded for long sessions.
        line_count = int(self.text_widget.index("end-1c").split(".")[0])
        if line_count > self.MAX_LINES:
            self.text_widget.delete("1.0", f"{line_count - self.MAX_LINES}.0")

        # Auto-scroll to end
        self.text_widget.see(tk.END)
        self.text_widget.config(state=tk.DISABLED)

    def clear_logs(self) -> None:
        """Clears all text from the log window."""
        self.text_widget.config(state=tk.NORMAL)
        self.text_widget.delete("1.0", tk.END)
        self.text_widget.config(state=tk.DISABLED)

    def get_logs(self) -> str:
        """Returns the raw text content of the logs."""
        return self.text_widget.get("1.0", tk.END)


class _CenteredModal(tk.Toplevel):
    """Base class: modal Toplevel centred on its parent."""

    def __init__(self, parent: tk.Widget, title: str):
        super().__init__(parent)
        self.title(title)
        self.transient(parent)
        self.resizable(False, False)

    def center_on_parent(self, parent: tk.Widget) -> None:
        self.update_idletasks()
        parent_x = parent.winfo_rootx()
        parent_y = parent.winfo_rooty()
        parent_w = parent.winfo_width()
        parent_h = parent.winfo_height()

        w = self.winfo_width()
        h = self.winfo_height()

        x = parent_x + (parent_w - w) // 2
        y = parent_y + (parent_h - h) // 2
        self.geometry(f"+{max(0, x)}+{max(0, y)}")

    def _make_modal(self) -> None:
        self.wait_visibility()
        self.grab_set()


class SteamCMDMissingModal(_CenteredModal):
    """
    Modal dialog prompted when the download tool (SteamCMD or DepotDownloader) is missing.
    Allows user to select existing binary or trigger auto-download.
    """

    def __init__(self, parent: tk.Widget, tool_name: str = "SteamCMD"):
        super().__init__(parent, f"{tool_name} Needed")
        self.tool_name = tool_name

        self.user_choice: Literal["browse", "download", "cancel"] = "cancel"
        self.selected_path: Optional[str] = None

        self._build_ui()
        self.center_on_parent(parent)
        self._make_modal()

    def _build_ui(self) -> None:
        container = ttk.Frame(self, padding=20)
        container.pack(fill=tk.BOTH, expand=True)

        header = ttk.Label(
            container,
            text=f"{self.tool_name} is needed",
            font=(UI_FONT, 12, "bold"),
        )
        header.pack(anchor=tk.W, pady=(0, 10))

        desc = ttk.Label(
            container,
            text=(
                f"Auger uses {self.tool_name} to download the 7 Days to Die Dedicated Server "
                "from Steam. Click Auto-Download and Auger will set it up for you."
            ),
            wraplength=440,
        )
        desc.pack(anchor=tk.W, pady=(0, 20))

        btn_frame = ttk.Frame(container)
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM)

        download_btn = ttk.Button(
            btn_frame,
            text=f"⬇️ Auto-Download {self.tool_name}",
            command=self._on_download,
        )
        download_btn.pack(side=tk.LEFT, padx=(0, 10), expand=True, fill=tk.X)

        browse_btn = ttk.Button(
            btn_frame,
            text="📁 Browse Existing...",
            command=self._on_browse,
        )
        browse_btn.pack(side=tk.LEFT, padx=(0, 10), expand=True, fill=tk.X)

        cancel_btn = ttk.Button(
            btn_frame,
            text="Cancel",
            command=self._on_cancel,
        )
        cancel_btn.pack(side=tk.RIGHT)

    def _on_download(self) -> None:
        self.user_choice = "download"
        self.destroy()

    def _on_browse(self) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            title=f"Select the {self.tool_name} program",
            filetypes=[
                (f"{self.tool_name} program", "*"),
            ],
        )
        if path:
            self.selected_path = path
            self.user_choice = "browse"
            self.destroy()

    def _on_cancel(self) -> None:
        self.user_choice = "cancel"
        self.destroy()


SANDBOX_HELP_STEPS = [
    (
        "What is a Sandbox Code?",
        "A short code that stores all of your gameplay rules: difficulty, loot, XP, day length, "
        "blood moons, zombie speed and more. The game makes it for you, so you never have to "
        "type it yourself.",
    ),
    (
        "Step 1: Open the game",
        "Start 7 Days to Die normally from Steam on your PC (the regular game, not the "
        "server). Ideally it should be the same game version as your server.",
    ),
    (
        "Step 2: Open Sandbox Options",
        "Go to Play Game → New Game, then open Sandbox Options.",
    ),
    (
        "Step 3: Choose your rules",
        "Pick a preset or change any settings you like. You don't need to start the game.",
    ),
    (
        "Step 4: Copy the code",
        "Click the Copy button on the Sandbox Options screen. The code is now on your "
        "clipboard. You can close the game.",
    ),
    (
        "Step 5: Paste it into Auger",
        "In Auger, open the ⚙️ Config Editor tab, find the 🧩 Gameplay Rules (Sandbox Code) "
        "section, and click 📋 Paste from Clipboard (or paste with Ctrl+V).",
    ),
    (
        "Step 6: Save and restart",
        "Click 💾 Save Config. If the server is already running, restart it so the new "
        "rules take effect.",
    ),
]


class SandboxCodeHelpDialog(_CenteredModal):
    """Step-by-step instructions for creating and copying a Sandbox Code in-game."""

    def __init__(self, parent: tk.Widget):
        super().__init__(parent, "How to get a Sandbox Code")
        self._build_ui()
        self.center_on_parent(parent)
        self._make_modal()

    def _build_ui(self) -> None:
        container = ttk.Frame(self, padding=20)
        container.pack(fill=tk.BOTH, expand=True)

        for title, body in SANDBOX_HELP_STEPS:
            ttk.Label(container, text=title, font=(UI_FONT, 10, "bold")).pack(anchor=tk.W, pady=(8, 0))
            ttk.Label(container, text=body, wraplength=520, justify=tk.LEFT).pack(anchor=tk.W)

        ttk.Label(
            container,
            text=(
                "Tip: if your friends can't see the new rules, check that you clicked Save "
                "Config and restarted the server."
            ),
            font=(UI_FONT, 9, "italic"),
            foreground="#7F8C8D",
            wraplength=520,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(14, 0))

        ttk.Button(container, text="Got it", command=self.destroy).pack(anchor=tk.E, pady=(16, 0))


def show_error(parent: tk.Widget, title: str, message: str) -> None:
    """Small wrapper so callers don't import messagebox everywhere."""
    messagebox.showerror(title, message, parent=parent)

"""
Custom widgets, colored logger text box, and modal dialogs for Tkinter UI.
"""

import datetime
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
from typing import Optional, Literal


class LoggerTextBox(ttk.Frame):
    """
    Scrollable text widget for displaying real-time logs with colored severity tags.
    """

    def __init__(self, parent: tk.Widget, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

        # ScrolledText widget setup
        self.text_widget = scrolledtext.ScrolledText(
            self,
            wrap=tk.WORD,
            font=("Consolas", 10),
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
        self.text_widget.tag_config("SUCCESS", foreground="#2ECC71", font=("Consolas", 10, "bold"))
        self.text_widget.tag_config("WARNING", foreground="#F39C12", font=("Consolas", 10, "bold"))
        self.text_widget.tag_config("ERROR", foreground="#E74C3C", font=("Consolas", 10, "bold"))

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


class SteamCMDMissingModal(tk.Toplevel):
    """
    Modal dialog prompted when SteamCMD executable is missing.
    Allows user to select existing binary or trigger auto-download.
    """

    def __init__(self, parent: tk.Widget):
        super().__init__(parent)
        self.title("SteamCMD Missing")
        self.geometry("480x240")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.user_choice: Literal["browse", "download", "cancel"] = "cancel"
        self.selected_path: Optional[str] = None

        self._build_ui()
        self.center_on_parent(parent)

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

    def _build_ui(self) -> None:
        container = ttk.Frame(self, padding=20)
        container.pack(fill=tk.BOTH, expand=True)

        header = ttk.Label(
            container,
            text="SteamCMD Executable Not Found",
            font=("Segoe UI", 12, "bold"),
        )
        header.pack(anchor=tk.W, pady=(0, 10))

        desc = ttk.Label(
            container,
            text=(
                "SteamCMD is required to download and manage the 7 Days to Die Dedicated Server.\n"
                "Please choose an action below:"
            ),
            wraplength=440,
        )
        desc.pack(anchor=tk.W, pady=(0, 20))

        btn_frame = ttk.Frame(container)
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM)

        download_btn = ttk.Button(
            btn_frame,
            text="⬇️ Auto-Download SteamCMD",
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
            title="Select steamcmd.exe or steamcmd.sh",
            filetypes=[
                ("SteamCMD Executable", "steamcmd.exe;steamcmd.sh;steamcmd"),
                ("All Files", "*.*"),
            ],
        )
        if path:
            self.selected_path = path
            self.user_choice = "browse"
            self.destroy()

    def _on_cancel(self) -> None:
        self.user_choice = "cancel"
        self.destroy()

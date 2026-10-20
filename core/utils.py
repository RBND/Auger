"""
Cross-platform path helpers, OS command launchers, process helpers, and High-DPI initialization.
"""

import ctypes
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Union


def get_app_dir() -> Path:
    """
    Returns the root application directory.
    Handles PyInstaller frozen environments (sys._MEIPASS / sys.executable)
    as well as standard Python script execution.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent.resolve()
    return Path(__file__).resolve().parent.parent


def get_app_data_dir() -> Path:
    """Return the writable, per-user directory used for Auger settings."""
    current_os = platform.system()
    if current_os == "Windows":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "Auger"
    if current_os == "Darwin":
        return Path.home() / "Library" / "Application Support" / "Auger"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "auger"


def setup_tcl_tk_env() -> None:
    """
    Locates and sets TCL_LIBRARY and TK_LIBRARY environment variables
    if not already set or if running in frozen/custom Python environments.
    """
    if "TCL_LIBRARY" in os.environ and "TK_LIBRARY" in os.environ:
        return

    # 1. Check frozen PyInstaller MEIPASS directory
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        meipass = Path(sys._MEIPASS)
        tcl_path = meipass / "tcl" / "tcl8.6"
        tk_path = meipass / "tcl" / "tk8.6"
        if tcl_path.exists():
            os.environ["TCL_LIBRARY"] = str(tcl_path)
        if tk_path.exists():
            os.environ["TK_LIBRARY"] = str(tk_path)
        return

    # 2. Check candidate system paths (Windows + Linux)
    candidate_tcl_roots = [
        # Windows paths
        Path(sys.prefix) / "tcl",
        Path(sys.base_prefix) / "tcl",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/Python/Python313/tcl",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/Python/Python312/tcl",
        Path("C:/Python313/tcl"),
        # Linux paths — each entry is the parent of tcl8.6/ and tk8.6/
        Path("/usr/lib"),              # /usr/lib/tcl8.6 and /usr/lib/tk8.6
        Path("/usr/share/tcltk"),      # /usr/share/tcltk/tcl8.6 and /usr/share/tcltk/tk8.6
        Path(sys.prefix) / "lib",      # venv-local: <venv>/lib/tcl8.6
        Path(sys.base_prefix) / "lib", # system Python: /usr/local/lib/tcl8.6
    ]

    for root in candidate_tcl_roots:
        try:
            tcl_dir = root / "tcl8.6"
            tk_dir = root / "tk8.6"
            if tcl_dir.exists() and tk_dir.exists():
                os.environ["TCL_LIBRARY"] = str(tcl_dir)
                os.environ["TK_LIBRARY"] = str(tk_dir)
                break
        except Exception:
            continue


def set_dpi_awareness() -> None:
    """
    Safely enables High-DPI awareness on Windows platforms to prevent blurry GUI rendering.
    Wrapped in try/except to prevent exceptions on unsupported OS versions or non-Windows systems.
    """
    setup_tcl_tk_env()
    if platform.system() == "Windows":
        try:
            # Per-monitor DPI awareness (Windows 8.1+)
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            try:
                # System DPI awareness (Windows Vista/7)
                ctypes.windll.user32.SetProcessDpiAware()
            except Exception:
                pass


def get_executable_name(base_name: str) -> str:
    """
    Returns the platform-appropriate executable file name.
    Appends '.exe' on Windows if not already present.
    """
    if platform.system() == "Windows":
        if not base_name.lower().endswith(".exe"):
            return f"{base_name}.exe"
    return base_name


def is_windows() -> bool:
    """Return True when running on Windows."""
    return platform.system() == "Windows"


def get_data_dir() -> Path:
    """Return the writable, per-user directory for large data (tools, server files).

    Windows: %LOCALAPPDATA%\\Auger   Linux: $XDG_DATA_HOME/auger (~/.local/share/auger)
    """
    if is_windows():
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "Auger"
    if platform.system() == "Darwin":
        return Path.home() / "Library" / "Application Support" / "Auger"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "auger"


def steamcmd_binary_name() -> str:
    """SteamCMD entry point: steamcmd.exe on Windows, the steamcmd.sh wrapper on Linux."""
    return "steamcmd.exe" if is_windows() else "steamcmd.sh"


def game_default_userdata_dir() -> Path:
    """Where the 7DTD server keeps saves when serverconfig's UserDataFolder is not set."""
    if is_windows():
        return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "7DaysToDie"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "7DaysToDie"


def depotdownloader_binary_name() -> str:
    """DepotDownloader entry point inside its release zip."""
    return "DepotDownloader.exe" if is_windows() else "DepotDownloader"


def server_binary_name() -> str:
    """7 Days to Die dedicated server executable for the current OS."""
    return "7DaysToDieServer.exe" if is_windows() else "7DaysToDieServer.x86_64"


def ensure_executable(path: Union[Path, str]) -> None:
    """Add the executable bit on POSIX systems (zip extraction drops it)."""
    if is_windows():
        return
    target = Path(path)
    if target.is_file():
        mode = target.stat().st_mode
        target.chmod(mode | 0o755)


def open_folder(target_path: Union[Path, str]) -> bool:
    """
    Opens the specified folder in the platform's default file manager
    (Windows Explorer, macOS Finder, or Linux File Manager).
    """
    path = Path(target_path).resolve()
    if not path.exists():
        return False

    # Ensure path points to a directory
    if path.is_file():
        path = path.parent

    try:
        current_os = platform.system()
        if current_os == "Windows":
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif current_os == "Darwin":  # macOS
            subprocess.Popen(["open", str(path)])
        else:  # Linux and Unix-like
            subprocess.Popen(["xdg-open", str(path)])
        return True
    except Exception as err:
        print(f"[Error] Failed to open folder {path}: {err}", file=sys.stderr)
        return False


def launch_detached_process(
    cmd: Union[List[str], str], cwd: Optional[Union[Path, str]] = None
) -> bool:
    """
    Launches a command in a detached process, independent of the management GUI.
    """
    work_dir = str(cwd) if cwd else None
    current_os = platform.system()

    try:
        if current_os == "Windows":
            if isinstance(cmd, str):
                subprocess.Popen(
                    cmd, cwd=work_dir, creationflags=subprocess.CREATE_NEW_CONSOLE, shell=True
                )
            else:
                subprocess.Popen(cmd, cwd=work_dir, creationflags=subprocess.CREATE_NEW_CONSOLE)
        else:
            if isinstance(cmd, str):
                subprocess.Popen(
                    cmd, cwd=work_dir, start_new_session=True, shell=True
                )
            else:
                subprocess.Popen(cmd, cwd=work_dir, start_new_session=True)
        return True
    except Exception as err:
        print(f"[Error] Failed to launch process {cmd}: {err}", file=sys.stderr)
        return False

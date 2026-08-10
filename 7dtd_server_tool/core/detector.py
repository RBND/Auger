"""
Detection logic for SteamCMD executable and 7 Days to Die Dedicated Server installation files.
Scans all available drive letters, relative paths, system PATH, and standard Steam libraries.
"""

import os
import platform
import shutil
import string
from pathlib import Path
from typing import Optional, List, Union

from .utils import get_app_dir, get_executable_name


def get_available_drives() -> List[Path]:
    """Returns a list of root Paths for all available Windows drive letters (C:/, D:/, E:/, etc.)."""
    drives: List[Path] = []
    if platform.system() == "Windows":
        for letter in string.ascii_uppercase:
            drive_path = Path(f"{letter}:/")
            try:
                if drive_path.exists():
                    drives.append(drive_path)
            except (PermissionError, OSError):
                continue
    else:
        drives.append(Path("/"))
    return drives


def find_steamcmd(custom_hint_path: Optional[Union[Path, str]] = None) -> Optional[Path]:
    """
    Scans relative project directories, system PATH, and all available drive roots
    to locate an existing SteamCMD executable.

    Returns the absolute Path to steamcmd executable if found, or None.
    """
    app_dir = get_app_dir()
    exe_name = get_executable_name("steamcmd")

    search_candidates: List[Path] = []

    # 1. User hint path (if provided)
    if custom_hint_path:
        hint = Path(custom_hint_path).resolve()
        if hint.is_dir():
            search_candidates.append(hint / exe_name)
        else:
            search_candidates.append(hint)

    # 2. Relative project paths
    search_candidates.extend(
        [
            app_dir / "steamcmd" / exe_name,
            app_dir / exe_name,
            app_dir / "SteamCMD" / exe_name,
        ]
    )

    # 3. System PATH check
    which_path = shutil.which("steamcmd")
    if which_path:
        search_candidates.append(Path(which_path).resolve())

    # 4. Multi-drive root scan & standard OS installation paths
    current_os = platform.system()
    if current_os == "Windows":
        local_appdata = Path(os.environ.get("LOCALAPPDATA", "C:/"))
        search_candidates.append(local_appdata / "SteamCMD" / exe_name)

        for drive in get_available_drives():
            search_candidates.extend(
                [
                    drive / "SteamCMD" / exe_name,
                    drive / "steamcmd" / exe_name,
                    drive / exe_name,
                    drive / "Program Files (x86)" / "SteamCMD" / exe_name,
                    drive / "Program Files (x86)" / "Steam" / exe_name,
                    drive / "Program Files" / "SteamCMD" / exe_name,
                    drive / "Steam" / exe_name,
                    drive / "SteamLibrary" / "SteamCMD" / exe_name,
                    drive / "Games" / "SteamCMD" / exe_name,
                    drive / "Servers" / "SteamCMD" / exe_name,
                    drive / "Server" / "SteamCMD" / exe_name,
                ]
            )
    else:  # Linux / macOS
        home = Path.home()
        search_candidates.extend(
            [
                home / ".local/share/Steam/steamcmd.sh",
                home / ".local/share/Steamcmd/steamcmd.sh",
                home / "steamcmd/steamcmd.sh",
                Path("/usr/bin/steamcmd"),
                Path("/usr/local/bin/steamcmd"),
            ]
        )

    # Validate candidate paths safely against PermissionError or OSError
    for candidate in search_candidates:
        try:
            if candidate.is_file() and os.access(candidate, os.X_OK | os.R_OK):
                return candidate.resolve()
            elif current_os == "Windows" and candidate.is_file():
                return candidate.resolve()
        except (PermissionError, OSError):
            continue

    return None


def find_7dtd_server(
    custom_hint_path: Optional[Union[Path, str]] = None,
    steamcmd_path: Optional[Path] = None,
) -> Optional[Path]:
    """
    Scans candidate directories across all system drives for an existing 7 Days to Die Dedicated Server installation.
    Looks for server binary (7DaysToDieServer.exe / 7DaysToDieServer.x86_64) and serverconfig.xml.

    Returns the absolute Path to the 7DTD server directory if found, or None.
    """
    app_dir = get_app_dir()
    is_windows = platform.system() == "Windows"
    binary_name = "7DaysToDieServer.exe" if is_windows else "7DaysToDieServer.x86_64"

    search_dirs: List[Path] = []

    # 1. Custom hint path
    if custom_hint_path:
        search_dirs.append(Path(custom_hint_path).resolve())

    # 2. Relative project directories
    search_dirs.extend(
        [
            app_dir / "7dtd_server",
            app_dir / "7 Days To Die Dedicated Server",
            app_dir,
            app_dir.parent / "7dtd_server",
        ]
    )

    # 3. SteamCMD default installation target (steamapps/common/...)
    if steamcmd_path:
        steamcmd_dir = steamcmd_path.parent
        search_dirs.extend(
            [
                steamcmd_dir / "steamapps/common/7 Days To Die Dedicated Server",
                steamcmd_dir / "7dtd_server",
            ]
        )

    # 4. Multi-drive Steam Library and Dedicated Server search
    for drive in get_available_drives():
        search_dirs.extend(
            [
                drive / "7dtd_server",
                drive / "7 Days To Die Dedicated Server",
                drive / "SteamLibrary/steamapps/common/7 Days To Die Dedicated Server",
                drive / "Steam/steamapps/common/7 Days To Die Dedicated Server",
                drive / "Program Files (x86)/Steam/steamapps/common/7 Days To Die Dedicated Server",
                drive / "Program Files/Steam/steamapps/common/7 Days To Die Dedicated Server",
                drive / "SteamCMD/steamapps/common/7 Days To Die Dedicated Server",
                drive / "steamcmd/steamapps/common/7 Days To Die Dedicated Server",
                drive / "Games/7 Days To Die Dedicated Server",
                drive / "Servers/7 Days To Die Dedicated Server",
            ]
        )

    if not is_windows:
        home = Path.home()
        search_dirs.extend(
            [
                home / ".local/share/Steam/steamapps/common/7 Days To Die Dedicated Server",
                home / "Steam/steamapps/common/7 Days To Die Dedicated Server",
            ]
        )

    # Inspect search directories
    for sdir in search_dirs:
        try:
            if not sdir.exists() or not sdir.is_dir():
                continue

            # Check if directory contains server executable or start script
            exe_file = sdir / binary_name
            config_file = sdir / "serverconfig.xml"
            bat_file = sdir / "startdedicated.bat"
            legacy_bat = sdir / "startserver.bat"

            if (exe_file.is_file() or bat_file.is_file() or legacy_bat.is_file()) and config_file.is_file():
                return sdir.resolve()
            elif exe_file.is_file():
                return sdir.resolve()
        except (PermissionError, OSError):
            continue

    return None

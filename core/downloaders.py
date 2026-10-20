"""
Download-tool definitions for fetching the 7 Days to Die Dedicated Server.

Windows uses SteamCMD; Linux uses DepotDownloader (self-contained 64-bit .NET),
which avoids SteamCMD's 32-bit library requirements on Linux.

Everything in this module is pure (no I/O) so it can be unit tested.
"""

import re
from pathlib import Path
from typing import Dict, List, Optional

from .utils import depotdownloader_binary_name, is_windows, steamcmd_binary_name

GAME_APP_ID = "294420"

TOOL_STEAMCMD = "steamcmd"
TOOL_DEPOTDOWNLOADER = "depotdownloader"

STEAMCMD_WIN_URL = "https://steamcdn-a.akamaihd.net/client/installer/steamcmd.zip"
STEAMCMD_LINUX_URL = "https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz"
DEPOTDOWNLOADER_URL_TEMPLATE = (
    "https://github.com/SteamRE/DepotDownloader/releases/latest/download/DepotDownloader-{asset}.zip"
)

BRANCH_PATTERN = re.compile(r"[A-Za-z0-9_.-]{1,64}")
_FORBIDDEN_PASSWORD_CHARS = "\r\n\x00"


def default_tool_for_platform() -> str:
    """SteamCMD on Windows, DepotDownloader everywhere else."""
    return TOOL_STEAMCMD if is_windows() else TOOL_DEPOTDOWNLOADER


def tool_display_name(tool: str) -> str:
    return "SteamCMD" if tool == TOOL_STEAMCMD else "DepotDownloader"


def tool_binary_name(tool: str) -> str:
    return steamcmd_binary_name() if tool == TOOL_STEAMCMD else depotdownloader_binary_name()


def tool_default_subdir(tool: str) -> str:
    return "steamcmd" if tool == TOOL_STEAMCMD else "depotdownloader"


def tool_download_url(tool: str) -> str:
    if tool == TOOL_STEAMCMD:
        return STEAMCMD_WIN_URL if is_windows() else STEAMCMD_LINUX_URL
    asset = "windows-x64" if is_windows() else "linux-x64"
    return DEPOTDOWNLOADER_URL_TEMPLATE.format(asset=asset)


def tool_environment(tool: str, base_env: Dict[str, str]) -> Dict[str, str]:
    """Extra environment for running the tool.

    DepotDownloader is a .NET app; invariant globalization means it does not
    need libicu installed on Linux.
    """
    env = dict(base_env)
    if tool == TOOL_DEPOTDOWNLOADER:
        env.setdefault("DOTNET_SYSTEM_GLOBALIZATION_INVARIANT", "1")
    return env


def validate_branch(branch: str) -> str:
    normalized = (branch or "").strip()
    if not BRANCH_PATTERN.fullmatch(normalized):
        raise ValueError(
            "The server branch must be 1-64 letters, numbers, dots, underscores, or hyphens."
        )
    return normalized


def validate_beta_password(beta_password: Optional[str]) -> Optional[str]:
    if not beta_password:
        return None
    if any(char in beta_password for char in _FORBIDDEN_PASSWORD_CHARS):
        raise ValueError("The beta password contains unsupported characters.")
    return beta_password


def build_steamcmd_command(
    steamcmd_path: Path,
    server_dir: Path,
    branch: str = "public",
    beta_password: Optional[str] = None,
    validate: bool = False,
) -> List[str]:
    """Build a SteamCMD argv list.

    * ``+force_install_dir`` must come before ``+login``.
    * Every token is its own argv element so no platform quoting can merge them.
    """
    branch = validate_branch(branch)
    beta_password = validate_beta_password(beta_password)

    cmd = [
        str(steamcmd_path),
        "+force_install_dir", str(server_dir),
        "+login", "anonymous",
        "+app_update", GAME_APP_ID,
        "-beta", branch,
    ]
    if beta_password:
        cmd += ["-betapassword", beta_password]
    if validate:
        cmd.append("validate")
    cmd.append("+quit")
    return cmd


def build_depotdownloader_command(
    depotdownloader_path: Path,
    server_dir: Path,
    branch: str = "public",
    beta_password: Optional[str] = None,
    validate: bool = False,
    target_os: Optional[str] = None,
) -> List[str]:
    """Build a DepotDownloader argv list (anonymous login is the default)."""
    branch = validate_branch(branch)
    beta_password = validate_beta_password(beta_password)
    target_os = target_os or ("windows" if is_windows() else "linux")

    cmd = [
        str(depotdownloader_path),
        "-app", GAME_APP_ID,
        "-os", target_os,
        "-osarch", "64",
        "-dir", str(server_dir),
        "-branch", branch,
    ]
    if beta_password:
        cmd += ["-branchpassword", beta_password]
    if validate:
        cmd.append("-validate")
    return cmd


def build_install_command(
    tool: str,
    tool_path: Path,
    server_dir: Path,
    branch: str = "public",
    beta_password: Optional[str] = None,
    validate: bool = False,
) -> List[str]:
    if tool == TOOL_STEAMCMD:
        return build_steamcmd_command(tool_path, server_dir, branch, beta_password, validate)
    return build_depotdownloader_command(tool_path, server_dir, branch, beta_password, validate)


# ---------------------------------------------------------------------------
# Output parsing
# ---------------------------------------------------------------------------
_STEAMCMD_PROGRESS = re.compile(r"progress:\s*([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)
_DEPOT_PROGRESS = re.compile(r"^\s*([0-9]{1,3}\.[0-9]{2})%\s")


class InstallOutputTracker:
    """Classifies tool output lines and decides whether an install succeeded.

    Exit codes alone are unreliable (SteamCMD in particular), so success is
    judged from the tool's own completion/error messages.
    """

    def __init__(self, tool: str):
        self.tool = tool
        self.saw_success = False
        self.errors: List[str] = []
        self.last_percent: Optional[float] = None

    def feed(self, line: str) -> str:
        """Record a line; return its log level (INFO/SUCCESS/WARNING/ERROR/PROGRESS)."""
        text = line.strip()
        lower = text.lower()

        percent = self._parse_progress(text)
        if percent is not None:
            self.last_percent = percent
            return "PROGRESS"

        if self.tool == TOOL_STEAMCMD:
            if "success!" in lower and "fully installed" in lower:
                self.saw_success = True
                return "SUCCESS"
            if text.startswith("ERROR!") or "failed to install" in lower:
                self.errors.append(text)
                return "ERROR"
            if "error" in lower or "failed" in lower:
                return "WARNING"
            return "INFO"

        # DepotDownloader
        if text.startswith("Total downloaded:"):
            self.saw_success = True
            return "SUCCESS"
        if (
            text.startswith("Error")
            or text.startswith("Unable to")
            or text.startswith("No valid depot key")
            or text.startswith("Download failed")
            or "Aborting." in text
        ):
            self.errors.append(text)
            return "ERROR"
        if text.startswith("Encountered") or text.startswith("Warning"):
            return "WARNING"
        return "INFO"

    def _parse_progress(self, text: str) -> Optional[float]:
        pattern = _STEAMCMD_PROGRESS if self.tool == TOOL_STEAMCMD else _DEPOT_PROGRESS
        match = pattern.search(text)
        if not match:
            return None
        try:
            return max(0.0, min(100.0, float(match.group(1))))
        except ValueError:
            return None

    def succeeded(self, return_code: int) -> bool:
        if self.errors:
            return False
        if self.tool == TOOL_STEAMCMD:
            # SteamCMD sometimes exits non-zero after a successful install.
            return self.saw_success
        return return_code == 0 and self.saw_success

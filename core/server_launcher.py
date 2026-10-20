"""
Builds the per-OS launch command for the 7 Days to Die Dedicated Server and
keeps a handle to the running process so Auger knows whether it is running.

This replaces launching startdedicated.bat / startserver.sh, which broke on
Linux and gave Auger no way to know if the server was alive.
"""

import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .utils import ensure_executable, is_windows, server_binary_name

LOG_SUBDIR = "7DaysToDieServer_Data"


def is_server_installed(server_dir: Optional[Path]) -> bool:
    """True when the dedicated server executable for this OS exists in ``server_dir``."""
    return bool(server_dir) and (Path(server_dir) / server_binary_name()).is_file()


def build_server_launch(
    server_dir: Path,
    config_file: str = "serverconfig.xml",
    log_file: Optional[Path] = None,
    base_env: Optional[Dict[str, str]] = None,
) -> Tuple[List[str], Dict[str, str], Path]:
    """Return ``(argv, env, log_file)`` mirroring the official start scripts."""
    server_dir = Path(server_dir)
    if log_file is None:
        stamp = datetime.now().strftime("%Y-%m-%d__%H-%M-%S")
        log_file = server_dir / LOG_SUBDIR / f"output_log__{stamp}.txt"

    cmd = [
        str(server_dir / server_binary_name()),
        "-logfile", str(log_file),
        "-quit",
        "-batchmode",
        "-nographics",
        f"-configfile={config_file}",
        "-dedicated",
    ]

    env = dict(os.environ if base_env is None else base_env)
    if not is_windows():
        # The Linux server loads its bundled .so files from its own folder.
        existing = env.get("LD_LIBRARY_PATH", "")
        env["LD_LIBRARY_PATH"] = str(server_dir) + (os.pathsep + existing if existing else "")
    return cmd, env, log_file


class ServerProcess:
    """Owns the dedicated server process started by this Auger session."""

    def __init__(self) -> None:
        self._proc: Optional[subprocess.Popen] = None
        self.log_file: Optional[Path] = None

    @property
    def pid(self) -> Optional[int]:
        return self._proc.pid if self._proc else None

    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def exit_code(self) -> Optional[int]:
        return None if self._proc is None else self._proc.poll()

    def start(self, server_dir: Path, config_file: str = "serverconfig.xml") -> Path:
        """Start the server. Raises RuntimeError/OSError with a readable message on failure."""
        if self.is_running():
            raise RuntimeError("The server is already running.")

        server_dir = Path(server_dir)
        binary = server_dir / server_binary_name()
        if not binary.is_file():
            raise RuntimeError(f"Server program not found: {binary}")
        if not (server_dir / config_file).is_file():
            raise RuntimeError(f"Config file not found: {server_dir / config_file}")

        ensure_executable(binary)
        cmd, env, log_file = build_server_launch(server_dir, config_file)
        log_file.parent.mkdir(parents=True, exist_ok=True)

        kwargs = {
            "cwd": str(server_dir),
            "env": env,
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
        }
        if is_windows():
            kwargs["creationflags"] = (
                subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
            )
        else:
            kwargs["start_new_session"] = True

        self._proc = subprocess.Popen(cmd, **kwargs)
        self.log_file = log_file
        return log_file

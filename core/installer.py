"""
Asynchronous installer and updater for SteamCMD and 7 Days to Die Dedicated Server.
Pipes process logs safely into a thread-safe queue.Queue for GUI updates.
"""

import os
import platform
import queue
import re
import subprocess
import tarfile
import tempfile
import threading
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable, Optional, Union

from .utils import get_app_dir, get_executable_name


def _enqueue_output(
    stdout,
    line_queue: queue.Queue,
) -> None:
    """
    Dedicated reader thread: reads process stdout by chunk, splits on \\r and \\n,
    and enqueues each unique non-empty line.
    Runs in a daemon thread so it never blocks the UI or installer worker thread.
    """
    buffer = bytearray()
    last_line = b""

    try:
        while True:
            chunk = stdout.read(512)
            if not chunk:
                break
            buffer.extend(chunk)

            # Process all complete lines (split on \r or \n)
            while True:
                cr = buffer.find(b"\r")
                nl = buffer.find(b"\n")

                if cr == -1 and nl == -1:
                    break

                # Pick whichever delimiter comes first
                if cr == -1:
                    end = nl
                elif nl == -1:
                    end = cr
                else:
                    end = min(cr, nl)

                line = buffer[:end].strip()
                # Skip past delimiter(s)
                skip = end + 1
                if end + 1 < len(buffer) and buffer[end] == ord("\r") and buffer[end + 1] == ord("\n"):
                    skip = end + 2
                buffer = buffer[skip:]

                if line and line != last_line:
                    last_line = line
                    try:
                        line_queue.put_nowait(line.decode("utf-8", errors="replace"))
                    except Exception:
                        pass

        # Flush any remaining buffer content
        if buffer:
            line = buffer.strip()
            if line and line != last_line:
                try:
                    line_queue.put_nowait(line.decode("utf-8", errors="replace"))
                except Exception:
                    pass
    except Exception:
        pass
    finally:
        line_queue.put(None)  # Sentinel: signals the reader is done


class InstallationManager:
    """
    Manages SteamCMD download/extraction and 7DTD server downloading/updating
    using background threads to ensure zero GUI lockups.
    """

    STEAMCMD_WIN_URL = "https://steamcdn-a.akamaihd.net/client/installer/steamcmd.zip"
    STEAMCMD_LINUX_URL = "https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz"
    GAME_APP_ID = "294420"
    DOWNLOAD_TIMEOUT_SECONDS = 60
    BRANCH_PATTERN = re.compile(r"[A-Za-z0-9_.-]{1,64}")

    def __init__(self, log_queue: queue.Queue):
        self.log_queue = log_queue
        self._is_running = False

    def log(self, message: str, level: str = "INFO") -> None:
        """Dispatches a log message tuple to the thread-safe GUI queue."""
        self.log_queue.put(("log", level, message))

    def status_update(self, component: str, message: str) -> None:
        """Dispatches a status change tuple to the thread-safe GUI queue."""
        self.log_queue.put(("status", component, message))

    def is_busy(self) -> bool:
        return self._is_running

    @classmethod
    def build_app_update_argument(
        cls,
        branch: str = "public",
        beta_password: Optional[str] = None,
        validate: bool = True,
    ) -> str:
        """Build the single SteamCMD app_update argument safely.

        SteamCMD retains the last selected beta branch.  Supplying ``public``
        explicitly therefore also makes switching back to the stable server
        reliable.
        """
        normalized_branch = branch.strip()
        if not cls.BRANCH_PATTERN.fullmatch(normalized_branch):
            raise ValueError(
                "The server branch must be 1-64 letters, numbers, dots, underscores, or hyphens."
            )
        if beta_password and any(char in beta_password for char in "\r\n\x00"):
            raise ValueError("The beta password contains unsupported characters.")

        parts = [cls.GAME_APP_ID, "-beta", normalized_branch]
        if beta_password:
            parts.extend(["-betapassword", beta_password])
        if validate:
            parts.append("validate")
        return " ".join(parts)

    @staticmethod
    def _safe_archive_destination(destination: Path, member_name: str) -> Path:
        """Return a destination only when an archive member stays in its folder."""
        root = destination.resolve()
        candidate = (root / member_name).resolve()
        if candidate != root and root not in candidate.parents:
            raise ValueError(f"Archive member escapes the destination: {member_name}")
        return candidate

    @classmethod
    def _extract_zip_safely(cls, archive_path: Path, destination: Path) -> None:
        with zipfile.ZipFile(archive_path, "r") as archive:
            for member in archive.infolist():
                cls._safe_archive_destination(destination, member.filename)
                # A Unix symlink is encoded in the upper file attributes.
                if (member.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError(f"Refusing symlink in archive: {member.filename}")
            archive.extractall(destination)

    @classmethod
    def _extract_tar_safely(cls, archive_path: Path, destination: Path) -> None:
        with tarfile.open(archive_path, "r:gz") as archive:
            members = archive.getmembers()
            for member in members:
                cls._safe_archive_destination(destination, member.name)
                if not (member.isfile() or member.isdir()):
                    raise ValueError(f"Refusing unsafe archive member: {member.name}")
            archive.extractall(destination, members=members)

    def _download_file(
        self,
        url: str,
        destination: Path,
        report_progress: Callable[[int, int], None],
    ) -> None:
        """Download an HTTPS file with a timeout and progress reporting."""
        request = urllib.request.Request(url, headers={"User-Agent": "Auger/1.1"})
        with urllib.request.urlopen(request, timeout=self.DOWNLOAD_TIMEOUT_SECONDS) as response:
            content_length = int(response.headers.get("Content-Length", "0"))
            downloaded = 0
            with open(destination, "wb") as handle:
                while chunk := response.read(1024 * 128):
                    handle.write(chunk)
                    downloaded += len(chunk)
                    report_progress(downloaded, content_length)

    def _run_steamcmd_hidden(
        self,
        cmd: list[str],
        cwd: str,
        line_callback: Callable[[str], None],
    ) -> int:
        """
        Launches a SteamCMD command with no console window.
        Uses a dedicated reader thread to stream stdout lines to line_callback in real time.
        Returns the process exit code.
        """
        is_windows = platform.system() == "Windows"
        creation_flags = subprocess.CREATE_NO_WINDOW if is_windows else 0

        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0,
            creationflags=creation_flags,
        )

        # Spin up dedicated reader thread for this process's stdout
        line_q: queue.Queue = queue.Queue()
        reader = threading.Thread(
            target=_enqueue_output,
            args=(proc.stdout, line_q),
            daemon=True,
        )
        reader.start()

        # Consume lines from the reader queue and forward to callback
        while True:
            try:
                line = line_q.get(timeout=0.1)
                if line is None:
                    break  # Sentinel received: reader thread is done
                line_callback(line)
            except queue.Empty:
                # Check if process has died and reader queue is empty
                if proc.poll() is not None and line_q.empty():
                    break

        reader.join(timeout=5)
        proc.wait()
        return proc.returncode

    def download_and_setup_steamcmd_async(
        self,
        target_dir: Optional[Union[Path, str]] = None,
        on_complete: Optional[Callable[[Optional[Path]], None]] = None,
    ) -> None:
        """Starts background thread to download and bootstrap SteamCMD."""
        if self._is_running:
            self.log("An operation is already in progress.", "WARNING")
            return

        thread = threading.Thread(
            target=self._download_and_setup_steamcmd_worker,
            args=(target_dir, on_complete),
            daemon=True,
        )
        thread.start()

    def _download_and_setup_steamcmd_worker(
        self,
        target_dir: Optional[Union[Path, str]],
        on_complete: Optional[Callable[[Optional[Path]], None]],
    ) -> None:
        self._is_running = True
        is_windows = platform.system() == "Windows"
        exe_name = get_executable_name("steamcmd")

        try:
            dest_dir = (
                Path(target_dir).resolve()
                if target_dir
                else (get_app_dir() / "steamcmd")
            )
            dest_dir.mkdir(parents=True, exist_ok=True)

            self.status_update("steamcmd", "Downloading...")
            self.log(f"Downloading SteamCMD into {dest_dir}...", "INFO")

            download_url = (
                self.STEAMCMD_WIN_URL if is_windows else self.STEAMCMD_LINUX_URL
            )
            archive_suffix = ".zip" if is_windows else ".tar.gz"
            with tempfile.NamedTemporaryFile(
                dir=dest_dir, suffix=archive_suffix, delete=False
            ) as handle:
                archive_path = Path(handle.name)

            last_percent = -1

            def _report_progress(downloaded: int, total_size: int) -> None:
                nonlocal last_percent
                if total_size > 0:
                    percent = int(min(100.0, (downloaded / total_size) * 100))
                    if percent != last_percent and (percent % 5 == 0 or percent == 100):
                        last_percent = percent
                        self.log(f"Downloading: {percent}%", "INFO")

            self._download_file(download_url, archive_path, _report_progress)
            self.log("Download completed. Extracting files...", "SUCCESS")

            self.status_update("steamcmd", "Extracting...")
            if is_windows or str(archive_path).endswith(".zip"):
                self._extract_zip_safely(archive_path, dest_dir)
            else:
                self._extract_tar_safely(archive_path, dest_dir)

            if archive_path.exists():
                archive_path.unlink()

            steamcmd_bin = dest_dir / exe_name
            if not is_windows and steamcmd_bin.exists():
                steamcmd_bin.chmod(0o755)

            self.log(f"SteamCMD successfully extracted to {steamcmd_bin}", "SUCCESS")

            # Bootstrapping First-Run Step
            self.log("Performing SteamCMD initial self-update / bootstrap...", "INFO")
            self.status_update("steamcmd", "Bootstrapping...")

            def _on_bootstrap_line(line: str):
                if line:
                    self.log(line, "INFO")

            self._run_steamcmd_hidden(
                cmd=[str(steamcmd_bin), "+quit"],
                cwd=str(dest_dir),
                line_callback=_on_bootstrap_line,
            )

            self.log("SteamCMD initial setup completed successfully!", "SUCCESS")
            self.status_update("steamcmd", "Ready")

            if on_complete:
                on_complete(steamcmd_bin)

        except Exception as err:
            self.log(f"SteamCMD installation failed: {err}", "ERROR")
            self.status_update("steamcmd", "Error")
            if on_complete:
                on_complete(None)

        finally:
            self._is_running = False

    def install_or_update_server_async(
        self,
        steamcmd_path: Path,
        server_dir: Path,
        branch: str = "public",
        beta_password: Optional[str] = None,
        validate: bool = True,
        on_complete: Optional[Callable[[bool], None]] = None,
    ) -> None:
        """Starts background thread to download or update the 7DTD Dedicated Server."""
        if self._is_running:
            self.log("An operation is already in progress.", "WARNING")
            return

        thread = threading.Thread(
            target=self._install_or_update_server_worker,
            args=(steamcmd_path, server_dir, branch, beta_password, validate, on_complete),
            daemon=True,
        )
        thread.start()

    def _install_or_update_server_worker(
        self,
        steamcmd_path: Path,
        server_dir: Path,
        branch: str,
        beta_password: Optional[str],
        validate: bool,
        on_complete: Optional[Callable[[bool], None]],
    ) -> None:
        self._is_running = True
        try:
            server_dir.mkdir(parents=True, exist_ok=True)
            self.status_update("server", "Downloading / Updating...")
            self.log(
                f"Starting 7DTD Server download/update from the '{branch}' branch in {server_dir}...",
                "INFO",
            )
            app_update_argument = self.build_app_update_argument(
                branch=branch, beta_password=beta_password, validate=validate
            )

            cmd = [
                str(steamcmd_path),
                "+login",
                "anonymous",
                "+force_install_dir",
                str(server_dir),
                "+app_update",
                app_update_argument,
            ]
            cmd.append("+quit")

            # Do not log the raw command: a password for a private branch would be exposed.
            self.log(
                f"Requesting app {self.GAME_APP_ID} branch '{branch}'"
                f"{' with validation' if validate else ''}.",
                "INFO",
            )

            def _on_server_line(clean_line: str):
                if "Error" in clean_line or "FAILED" in clean_line:
                    self.log(clean_line, "ERROR")
                elif "Success" in clean_line or "Fully installed" in clean_line:
                    self.log(clean_line, "SUCCESS")
                else:
                    self.log(clean_line, "INFO")

            return_code = self._run_steamcmd_hidden(
                cmd=cmd,
                cwd=str(steamcmd_path.parent),
                line_callback=_on_server_line,
            )

            if return_code == 0:
                self.log(
                    "7 Days to Die Dedicated Server installation/update completed!",
                    "SUCCESS",
                )
                self.status_update("server", "Installed & Ready")
                if on_complete:
                    on_complete(True)
            else:
                self.log(
                    f"SteamCMD exited with non-zero code ({return_code}). Update may be incomplete.",
                    "WARNING",
                )
                self.status_update("server", "Update Warning")
                if on_complete:
                    on_complete(False)

        except Exception as err:
            self.log(f"Failed during server update: {err}", "ERROR")
            self.status_update("server", "Error")
            if on_complete:
                on_complete(False)
        finally:
            self._is_running = False

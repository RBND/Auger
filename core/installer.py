"""
Asynchronous installer and updater for the download tool (SteamCMD / DepotDownloader)
and the 7 Days to Die Dedicated Server.

All results are delivered through the thread-safe ``queue.Queue`` used by the GUI:

* ``("log", level, message)``
* ``("status", component, message)``      component: "tool" | "server"
* ``("progress", component, percent)``     percent: 0-100, or None to hide
* ``("busy", bool)``
* ``("callback", fn, args)``               run ``fn(*args)`` on the GUI thread
"""

import os
import platform
import queue
import shutil
import subprocess
import tarfile
import tempfile
import threading
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable, Dict, Optional, Union

from .downloaders import (
    GAME_APP_ID,
    TOOL_STEAMCMD,
    InstallOutputTracker,
    build_install_command,
    tool_binary_name,
    tool_default_subdir,
    tool_display_name,
    tool_download_url,
    tool_environment,
    validate_beta_password,
    validate_branch,
)
from .utils import ensure_executable, get_data_dir

# Files the game depot ships that users customise. They are preserved across updates.
PRESERVED_SERVER_FILES = ("serverconfig.xml",)
PRESERVE_SUFFIX = ".auger-preserve"


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


def preserve_user_files(server_dir: Path) -> Dict[Path, Path]:
    """Copy user-edited depot files aside before an update. Returns {original: backup}."""
    preserved: Dict[Path, Path] = {}
    for name in PRESERVED_SERVER_FILES:
        original = server_dir / name
        if original.is_file():
            backup = server_dir / f"{name}{PRESERVE_SUFFIX}"
            shutil.copy2(original, backup)
            preserved[original] = backup
    return preserved


def restore_user_files(preserved: Dict[Path, Path]) -> None:
    """Put preserved files back after an update (the depot may have overwritten them)."""
    for original, backup in preserved.items():
        if backup.is_file():
            os.replace(backup, original)


class InstallationManager:
    """
    Manages download-tool setup and 7DTD server downloading/updating
    using background threads to ensure zero GUI lockups.
    """

    GAME_APP_ID = GAME_APP_ID
    DOWNLOAD_TIMEOUT_SECONDS = 60

    def __init__(self, log_queue: queue.Queue):
        self.log_queue = log_queue
        self._is_running = False
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Event helpers
    # ------------------------------------------------------------------
    def log(self, message: str, level: str = "INFO") -> None:
        """Dispatches a log message tuple to the thread-safe GUI queue."""
        self.log_queue.put(("log", level, message))

    def status_update(self, component: str, message: str) -> None:
        """Dispatches a status change tuple to the thread-safe GUI queue."""
        self.log_queue.put(("status", component, message))

    def progress(self, component: str, percent: Optional[float]) -> None:
        self.log_queue.put(("progress", component, percent))

    def _callback(self, fn: Optional[Callable], *args) -> None:
        """Run ``fn`` on the GUI thread (Tkinter is not thread-safe)."""
        if fn:
            self.log_queue.put(("callback", fn, args))

    def is_busy(self) -> bool:
        return self._is_running

    def _try_begin(self) -> bool:
        """Atomically claim the single operation slot (prevents double-clicks)."""
        with self._lock:
            if self._is_running:
                return False
            self._is_running = True
        self.log_queue.put(("busy", True))
        return True

    def _end(self) -> None:
        with self._lock:
            self._is_running = False
        self.log_queue.put(("busy", False))

    def _start_worker(self, target: Callable, *args) -> bool:
        if not self._try_begin():
            self.log("An operation is already in progress.", "WARNING")
            return False
        thread = threading.Thread(target=self._run_guarded, args=(target, *args), daemon=True)
        thread.start()
        return True

    def _run_guarded(self, target: Callable, *args) -> None:
        try:
            target(*args)
        finally:
            self._end()

    # ------------------------------------------------------------------
    # Archive / download helpers
    # ------------------------------------------------------------------
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
        request = urllib.request.Request(url, headers={"User-Agent": "Auger/1.2"})
        with urllib.request.urlopen(request, timeout=self.DOWNLOAD_TIMEOUT_SECONDS) as response:
            content_length = int(response.headers.get("Content-Length", "0"))
            downloaded = 0
            with open(destination, "wb") as handle:
                while chunk := response.read(1024 * 128):
                    handle.write(chunk)
                    downloaded += len(chunk)
                    report_progress(downloaded, content_length)

    def _run_tool_hidden(
        self,
        cmd: list,
        cwd: str,
        line_callback: Callable[[str], None],
        env: Optional[Dict[str, str]] = None,
    ) -> int:
        """
        Launches a download-tool command with no console window.
        Uses a dedicated reader thread to stream stdout lines to line_callback in real time.
        Returns the process exit code.
        """
        is_windows = platform.system() == "Windows"
        creation_flags = subprocess.CREATE_NO_WINDOW if is_windows else 0

        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0,
            creationflags=creation_flags,
            env=env,
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

    # ------------------------------------------------------------------
    # Download tool setup (SteamCMD or DepotDownloader)
    # ------------------------------------------------------------------
    def default_tool_dir(self, tool: str) -> Path:
        return get_data_dir() / tool_default_subdir(tool)

    def download_and_setup_tool_async(
        self,
        tool: str,
        target_dir: Optional[Union[Path, str]] = None,
        on_complete: Optional[Callable[[Optional[Path]], None]] = None,
    ) -> bool:
        """Starts a background thread to download and prepare the download tool."""
        return self._start_worker(self._setup_tool_worker, tool, target_dir, on_complete)

    def _setup_tool_worker(
        self,
        tool: str,
        target_dir: Optional[Union[Path, str]],
        on_complete: Optional[Callable[[Optional[Path]], None]],
    ) -> None:
        name = tool_display_name(tool)
        archive_path: Optional[Path] = None
        try:
            dest_dir = Path(target_dir).resolve() if target_dir else self.default_tool_dir(tool)
            dest_dir.mkdir(parents=True, exist_ok=True)

            self.status_update("tool", "Downloading...")
            self.log(f"Downloading {name} into {dest_dir}...", "INFO")

            url = tool_download_url(tool)
            suffix = ".tar.gz" if url.endswith(".tar.gz") else ".zip"
            with tempfile.NamedTemporaryFile(dir=dest_dir, suffix=suffix, delete=False) as handle:
                archive_path = Path(handle.name)

            last_percent = -1

            def _report_progress(downloaded: int, total_size: int) -> None:
                nonlocal last_percent
                if total_size > 0:
                    percent = int(min(100.0, (downloaded / total_size) * 100))
                    if percent != last_percent:
                        last_percent = percent
                        self.progress("tool", percent)
                        if percent % 10 == 0:
                            self.log(f"Downloading: {percent}%", "INFO")

            self._download_file(url, archive_path, _report_progress)
            self.log("Download completed. Extracting files...", "SUCCESS")

            self.status_update("tool", "Extracting...")
            if suffix == ".zip":
                self._extract_zip_safely(archive_path, dest_dir)
            else:
                self._extract_tar_safely(archive_path, dest_dir)

            tool_bin = dest_dir / tool_binary_name(tool)
            if not tool_bin.is_file():
                raise FileNotFoundError(f"{tool_bin.name} was not found after extraction.")
            ensure_executable(tool_bin)
            if tool == TOOL_STEAMCMD:
                ensure_executable(dest_dir / "linux32" / "steamcmd")

            self.log(f"{name} extracted to {tool_bin}", "SUCCESS")
            self.status_update("tool", "Checking...")

            def _on_line(line: str) -> None:
                if line:
                    self.log(line, "INFO")

            if tool == TOOL_STEAMCMD:
                # First run: SteamCMD updates itself.
                self.log("Performing SteamCMD initial self-update...", "INFO")
                self._run_tool_hidden([str(tool_bin), "+quit"], str(dest_dir), _on_line)
            else:
                # Sanity check: confirms the binary runs on this system.
                env = tool_environment(tool, os.environ.copy())
                code = self._run_tool_hidden([str(tool_bin), "-V"], str(dest_dir), _on_line, env)
                if code != 0:
                    raise RuntimeError(f"{name} could not run on this system (exit code {code}).")

            self.log(f"{name} is ready.", "SUCCESS")
            self.status_update("tool", "Ready")
            self._callback(on_complete, tool_bin)

        except Exception as err:
            self.log(f"{name} installation failed: {err}", "ERROR")
            self.status_update("tool", "Error")
            self._callback(on_complete, None)
        finally:
            self.progress("tool", None)
            if archive_path and archive_path.exists():
                archive_path.unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # Server install / update
    # ------------------------------------------------------------------
    def install_or_update_server_async(
        self,
        tool: str,
        tool_path: Path,
        server_dir: Path,
        branch: str = "public",
        beta_password: Optional[str] = None,
        validate: bool = False,
        on_complete: Optional[Callable[[bool], None]] = None,
    ) -> bool:
        """Starts a background thread to download or update the 7DTD Dedicated Server."""
        try:
            validate_branch(branch)
            validate_beta_password(beta_password)
        except ValueError as err:
            self.log(str(err), "ERROR")
            return False
        return self._start_worker(
            self._install_server_worker,
            tool, tool_path, server_dir, branch, beta_password, validate, on_complete,
        )

    def _install_server_worker(
        self,
        tool: str,
        tool_path: Path,
        server_dir: Path,
        branch: str,
        beta_password: Optional[str],
        validate: bool,
        on_complete: Optional[Callable[[bool], None]],
    ) -> None:
        preserved: Dict[Path, Path] = {}
        success = False
        try:
            server_dir.mkdir(parents=True, exist_ok=True)
            preserved = preserve_user_files(server_dir)
            if preserved:
                self.log("Backed up your serverconfig.xml so the update cannot overwrite it.", "INFO")

            self.status_update("server", "Downloading / Updating...")
            self.log(
                f"Starting 7DTD Server download/update from the '{branch}' branch "
                f"using {tool_display_name(tool)} into {server_dir}...",
                "INFO",
            )

            cmd = build_install_command(tool, tool_path, server_dir, branch, beta_password, validate)
            # Do not log the raw command: a password for a private branch would be exposed.
            self.log(
                f"Requesting app {self.GAME_APP_ID} branch '{branch}'"
                f"{' with validation' if validate else ''}.",
                "INFO",
            )

            tracker = InstallOutputTracker(tool)
            last_logged_percent = -1

            def _on_line(line: str) -> None:
                nonlocal last_logged_percent
                level = tracker.feed(line)
                if level == "PROGRESS":
                    pct = tracker.last_percent or 0.0
                    self.progress("server", pct)
                    if int(pct) != last_logged_percent:
                        last_logged_percent = int(pct)
                        self.log(f"Downloading: {int(pct)}%", "INFO")
                    return
                self.log(line, level)

            env = tool_environment(tool, os.environ.copy())
            return_code = self._run_tool_hidden(cmd, str(tool_path.parent), _on_line, env)
            success = tracker.succeeded(return_code)

            if success:
                self.log("7 Days to Die Dedicated Server installation/update completed!", "SUCCESS")
                self.status_update("server", "Installed & Ready")
            else:
                details = tracker.errors[-1] if tracker.errors else f"exit code {return_code}"
                self.log(f"The server download did not finish successfully ({details}).", "ERROR")
                self.status_update("server", "Update Failed")

        except Exception as err:
            self.log(f"Failed during server update: {err}", "ERROR")
            self.status_update("server", "Error")
        finally:
            try:
                restore_user_files(preserved)
                if preserved:
                    self.log("Restored your serverconfig.xml.", "INFO")
            except OSError as err:
                self.log(f"Could not restore serverconfig.xml backup: {err}", "ERROR")
            self.progress("server", None)
            self._callback(on_complete, success)

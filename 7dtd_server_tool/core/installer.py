"""
Asynchronous installer and updater for SteamCMD and 7 Days to Die Dedicated Server.
Pipes process logs safely into a thread-safe queue.Queue for GUI updates.
"""

import os
import platform
import queue
import shutil
import subprocess
import tarfile
import threading
import urllib.request
import zipfile
from pathlib import Path
from typing import Optional, Union, Callable

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
            archive_path = dest_dir / ("steamcmd.zip" if is_windows else "steamcmd.tar.gz")

            last_percent = -1

            def _report_hook(block_num: int, block_size: int, total_size: int):
                nonlocal last_percent
                if total_size > 0:
                    percent = int(min(100.0, (block_num * block_size / total_size) * 100))
                    if percent != last_percent and (percent % 5 == 0 or percent == 100):
                        last_percent = percent
                        self.log(f"Downloading: {percent}%", "INFO")

            urllib.request.urlretrieve(download_url, archive_path, reporthook=_report_hook)
            self.log("Download completed. Extracting files...", "SUCCESS")

            self.status_update("steamcmd", "Extracting...")
            if is_windows or str(archive_path).endswith(".zip"):
                with zipfile.ZipFile(archive_path, "r") as zip_ref:
                    zip_ref.extractall(dest_dir)
            else:
                with tarfile.open(archive_path, "r:gz") as tar_ref:
                    tar_ref.extractall(dest_dir)

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
        validate: bool = True,
        on_complete: Optional[Callable[[bool], None]] = None,
    ) -> None:
        """Starts background thread to download or update the 7DTD Dedicated Server."""
        if self._is_running:
            self.log("An operation is already in progress.", "WARNING")
            return

        thread = threading.Thread(
            target=self._install_or_update_server_worker,
            args=(steamcmd_path, server_dir, validate, on_complete),
            daemon=True,
        )
        thread.start()

    def _install_or_update_server_worker(
        self,
        steamcmd_path: Path,
        server_dir: Path,
        validate: bool,
        on_complete: Optional[Callable[[bool], None]],
    ) -> None:
        self._is_running = True
        try:
            server_dir.mkdir(parents=True, exist_ok=True)
            self.status_update("server", "Downloading / Updating...")
            self.log(f"Starting 7DTD Server download/update in {server_dir}...", "INFO")

            cmd = [
                str(steamcmd_path),
                "+login",
                "anonymous",
                "+force_install_dir",
                str(server_dir),
                "+app_update",
                self.GAME_APP_ID,
            ]

            if validate:
                cmd.append("validate")
            cmd.append("+quit")

            self.log(f"Executing: {' '.join(cmd)}", "INFO")

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

"""
AugerService: the application core, independent of any GUI toolkit.

The GUI (or the CLI) calls commands on the service and drains its event queue.
Everything that touches the filesystem, the download tools, or the server process
lives here, so the view layer can be replaced (Tk today, possibly Qt later)
without touching business logic.

Events put on ``service.events`` (consumers handle them on ONE thread):

* ``("log", level, message)``
* ``("status", component, text)``          component: "tool" | "server"
* ``("progress", component, percent)``     None hides the progress indicator
* ``("busy", bool)``
* ``("changed", what)``                    what: "tool" | "server" | "config" | "admin" | "runtime"
* ``("callback", fn, args)``               consumer must call ``fn(*args)``
"""

import queue
import threading
from pathlib import Path
from typing import Callable, Dict, List, Optional

from .admin_manager import AdminManager, migrate_legacy_admin_file, resolve_admin_file_path
from .config_manager import ConfigManager, normalize_sandbox_code
from .config_schema import validate_values
from .detector import find_7dtd_server, find_download_tool
from .downloaders import TOOL_STEAMCMD, default_tool_for_platform, tool_default_subdir, tool_display_name
from .installer import InstallationManager
from .instance import AUGER_CONFIG_NAME, ServerInstance, default_server_dir
from .server_launcher import ServerProcess
from .settings_store import get_saved_path, save_settings
from .utils import get_data_dir, server_binary_name


class ServiceError(Exception):
    """A problem the user can understand and act on (message is shown as-is)."""


class AugerService:
    def __init__(self, events: Optional[queue.Queue] = None, tool: Optional[str] = None):
        self.events: queue.Queue = events if events is not None else queue.Queue()
        self.tool: str = tool or default_tool_for_platform()
        self.installer = InstallationManager(self.events)
        self.process = ServerProcess()
        self.admin = AdminManager()
        self.tool_path: Optional[Path] = None
        self.instance = ServerInstance(default_server_dir())
        self._was_running = False

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------
    def log(self, message: str, level: str = "INFO") -> None:
        self.events.put(("log", level, message))

    def _changed(self, what: str) -> None:
        self.events.put(("changed", what))

    def _callback(self, fn: Optional[Callable], *args) -> None:
        if fn:
            self.events.put(("callback", fn, args))

    def dispatch_pending(self, handler: Callable[[tuple], None], limit: int = 500) -> int:
        """Drain queued events: run callbacks, pass everything else to ``handler``."""
        handled = 0
        while handled < limit:
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            if event[0] == "callback":
                _, fn, args = event
                try:
                    fn(*args)
                except Exception as err:  # never let one callback break the loop
                    self.log(f"Internal error: {err}", "ERROR")
            else:
                handler(event)
            handled += 1
        return handled

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------
    @property
    def tool_name(self) -> str:
        return tool_display_name(self.tool)

    @property
    def server_dir(self) -> Path:
        return self.instance.server_dir

    @property
    def config_path(self) -> Path:
        return self.instance.config_path

    def default_tool_dir(self) -> Path:
        return get_data_dir() / tool_default_subdir(self.tool)

    def is_busy(self) -> bool:
        return self.installer.is_busy()

    def tool_ready(self) -> bool:
        return bool(self.tool_path) and self.tool_path.is_file()

    def server_installed(self) -> bool:
        return self.instance.is_installed()

    def server_running(self) -> bool:
        return self.process.is_running()

    @property
    def server_pid(self) -> Optional[int]:
        return self.process.pid

    def config_available(self) -> bool:
        return self.instance.has_auger_config()

    # ------------------------------------------------------------------
    # Detection & paths
    # ------------------------------------------------------------------
    def detect_async(self, on_done: Optional[Callable[[], None]] = None) -> None:
        """Find the download tool and an existing server in the background (drive scans can be slow)."""
        self.log(f"Scanning for {self.tool_name} & 7DTD Dedicated Server...", "INFO")
        self.events.put(("status", "tool", "Searching..."))
        self.events.put(("status", "server", "Searching..."))

        def _worker() -> None:
            saved_tool = get_saved_path(f"{self.tool}_path")
            tool_path = saved_tool or find_download_tool(self.tool)
            saved_server = get_saved_path("server_dir")
            hint = tool_path if self.tool == TOOL_STEAMCMD else None
            server_dir = saved_server or find_7dtd_server(steamcmd_path=hint)
            self._callback(
                self._apply_detection, tool_path, bool(saved_tool), server_dir, bool(saved_server), on_done
            )

        threading.Thread(target=_worker, daemon=True).start()

    def detect_blocking(self, handler: Optional[Callable[[tuple], None]] = None) -> None:
        """Synchronous detection (CLI / tests). Non-callback events go to ``handler``."""
        done = threading.Event()
        self.detect_async(on_done=done.set)
        while not done.is_set():
            self.dispatch_pending(handler or (lambda _event: None))
            done.wait(0.05)

    def _apply_detection(
        self,
        tool_path: Optional[Path],
        tool_from_saved: bool,
        server_dir: Optional[Path],
        server_from_saved: bool,
        on_done: Optional[Callable[[], None]],
    ) -> None:
        if tool_path:
            self.tool_path = Path(tool_path)
            self.events.put(("status", "tool", "Ready"))
            source = "saved settings" if tool_from_saved else "auto-detection"
            self.log(f"{self.tool_name} located via {source}: {tool_path}", "SUCCESS")
        else:
            self.events.put(("status", "tool", "Missing"))
            self.log(f"{self.tool_name} not found. Auger can download it for you.", "WARNING")
        self._changed("tool")

        if server_dir:
            self.set_server_dir(Path(server_dir), persist=not server_from_saved)
        else:
            self.instance = ServerInstance(default_server_dir())
            self.events.put(("status", "server", "Not Installed"))
            self.log("7DTD Server not installed yet. Click 'Install / Update 7DTD Dedicated Server'.", "INFO")
            self._changed("server")

        if on_done:
            on_done()

    def set_tool_path(self, path: Path) -> None:
        self.tool_path = Path(path)
        save_settings(**{f"{self.tool}_path": self.tool_path})
        self.events.put(("status", "tool", "Ready"))
        self.log(f"{self.tool_name} path set to: {self.tool_path}", "INFO")
        self._changed("tool")

    def set_server_dir(self, path: Path, persist: bool = True) -> None:
        """Point Auger at a server folder. Adopts an existing install's config without changing it."""
        self.instance = ServerInstance(Path(path))
        if persist:
            save_settings(server_dir=self.instance.server_dir)

        if self.instance.is_installed():
            self.events.put(("status", "server", "Installed & Ready"))
            self.log(f"7DTD Dedicated Server found: {self.instance.server_dir}", "SUCCESS")
            action = self.instance.ensure_config(fresh=False)
            if action == "adopted":
                self.log(
                    f"Auger now keeps its own copy of your settings in {AUGER_CONFIG_NAME} "
                    "(game updates can't overwrite it).",
                    "INFO",
                )
            self._init_admin()
        else:
            self.events.put(("status", "server", "Not Installed"))
            self.log(
                f"No server installed in {self.instance.server_dir} yet. "
                "Click 'Install / Update 7DTD Dedicated Server'.",
                "INFO",
            )
        self._changed("server")
        self._changed("config")

    # ------------------------------------------------------------------
    # Downloads
    # ------------------------------------------------------------------
    def download_tool_async(self, on_done: Optional[Callable[[Optional[Path]], None]] = None) -> bool:
        target_dir = self.tool_path.parent if self.tool_ready() else self.default_tool_dir()

        def _done(tool_path: Optional[Path]) -> None:
            if tool_path:
                self.set_tool_path(tool_path)
            if on_done:
                on_done(tool_path)

        return self.installer.download_and_setup_tool_async(self.tool, target_dir=target_dir, on_complete=_done)

    def install_server_async(
        self,
        branch: str = "public",
        beta_password: Optional[str] = None,
        validate: bool = False,
        on_done: Optional[Callable[[bool], None]] = None,
    ) -> bool:
        if not self.tool_ready():
            raise ServiceError(
                f"{self.tool_name} must be downloaded first. Click 'Download / Update {self.tool_name}'."
            )
        if self.server_running():
            raise ServiceError("Please stop the server before updating it.")

        fresh = not self.instance.is_installed() and not self.instance.has_auger_config()
        save_settings(server_branch=branch, validate_server_files=validate)
        server_dir = self.instance.server_dir

        def _done(success: bool) -> None:
            if success:
                self._after_install(server_dir, fresh)
            if on_done:
                on_done(success)

        return self.installer.install_or_update_server_async(
            tool=self.tool,
            tool_path=self.tool_path,
            server_dir=server_dir,
            branch=branch,
            beta_password=beta_password,
            validate=validate,
            on_complete=_done,
        )

    def _after_install(self, server_dir: Path, fresh: bool) -> None:
        instance = ServerInstance(server_dir)
        action = instance.ensure_config(fresh=fresh)
        if action == "created":
            self.log(
                f"Created {AUGER_CONFIG_NAME}. Worlds and saves will be stored in {instance.userdata_dir}.",
                "SUCCESS",
            )
        added = instance.merge_new_stock_keys()
        if added:
            self.log(f"Added {len(added)} new setting(s) from the game update: {', '.join(added)}", "INFO")
        self.set_server_dir(server_dir)

    # ------------------------------------------------------------------
    # Server process
    # ------------------------------------------------------------------
    def start_server(self) -> Path:
        if self.server_running():
            raise ServiceError("The server is already running.")
        if not self.server_installed():
            raise ServiceError(
                f"{server_binary_name()} was not found. Click 'Install / Update 7DTD Dedicated Server' first."
            )
        self.instance.ensure_config(fresh=False)
        try:
            log_file = self.process.start(self.instance.server_dir, config_file=AUGER_CONFIG_NAME)
        except (RuntimeError, OSError) as err:
            raise ServiceError(f"Could not start the server: {err}") from err

        self._was_running = True
        self.log(
            f"Server starting (PID {self.process.pid}). It can take a few minutes before players "
            f"can join. Server log: {log_file}",
            "SUCCESS",
        )
        self._changed("runtime")
        return log_file

    def poll_server(self) -> None:
        """Call periodically; reports when the server we started exits."""
        running = self.process.is_running()
        if self._was_running and not running:
            code = self.process.exit_code()
            self.log(f"The server has stopped (exit code {code}).", "INFO" if code == 0 else "WARNING")
            self._changed("runtime")
        self._was_running = running

    # ------------------------------------------------------------------
    # Configuration (Auger's own serverconfig.auger.xml)
    # ------------------------------------------------------------------
    def _config_manager(self) -> ConfigManager:
        return ConfigManager(self.instance.config_path)

    def load_config(self) -> Optional[Dict[str, str]]:
        """Current settings, or None when no server is set up yet. Never writes anything."""
        if not self.instance.has_auger_config():
            return None
        return self._config_manager().load_config()

    def save_config(self, values: Dict[str, str]) -> Dict[str, str]:
        """Validate and save. Returns the values actually written (e.g. cleaned Sandbox Code)."""
        if not self.instance.has_auger_config():
            if not self.server_installed():
                raise ServiceError(
                    "Install the 7DTD Dedicated Server first (Server Control & Setup tab). "
                    "Then come back here to change its settings."
                )
            self.instance.ensure_config(fresh=False)

        cleaned = dict(values)
        raw_code = cleaned.get("SandboxCode", "")
        if raw_code.strip():
            code = normalize_sandbox_code(raw_code)
            if not code:
                raise ServiceError(
                    "The Sandbox Code doesn't look right. Copy it again from the game's "
                    "Sandbox Options screen (click ❓ next to the field for help)."
                )
            cleaned["SandboxCode"] = code

        problems = validate_values(cleaned)
        if problems:
            raise ServiceError("Please fix these settings:\n\n• " + "\n• ".join(problems))

        manager = self._config_manager()
        existing = manager.load_config_raw()
        manager.load_config()
        admin_before = self.admin_path()
        # Don't introduce empty properties the file never had (e.g. UserDataFolder, which the
        # game leaves commented out unless it's used).
        for key in [k for k, v in cleaned.items() if k not in existing and not str(v).strip()]:
            del cleaned[key]
        manager.save_config(cleaned, make_backup=True)
        self.log(f"Saved {AUGER_CONFIG_NAME} (a timestamped backup was created).", "SUCCESS")
        if self.server_running():
            self.log("Restart the server for the new settings to take effect.", "WARNING")
        if self.admin_path() != admin_before:
            self._init_admin()  # admin file location changed
        self._changed("config")
        return cleaned

    def reset_config(self) -> None:
        if not self.instance.has_auger_config():
            raise ServiceError("There is no configuration to reset yet.")
        manager = self._config_manager()
        current = manager.load_config()
        keep = {key: current.get(key, "") for key in ("UserDataFolder", "AdminFileName")}
        manager.reset_to_defaults(make_backup=True, keep=keep)
        self.log("Configuration reset to default settings (your saves folder was kept).", "SUCCESS")
        self._changed("config")

    # ------------------------------------------------------------------
    # Admin file (serveradmin.xml)
    # ------------------------------------------------------------------
    def admin_path(self) -> Optional[Path]:
        settings = self.load_config()
        if settings is None:
            return None
        return resolve_admin_file_path(self.instance.server_dir, settings)

    def _init_admin(self) -> None:
        settings = self.load_config()
        if settings is None:
            return
        try:
            migrated = migrate_legacy_admin_file(self.instance.server_dir, settings)
            if migrated:
                self.log(
                    f"Moved your admin list to {migrated}, the file the game actually reads.", "INFO"
                )
            path = resolve_admin_file_path(self.instance.server_dir, settings)
            self.admin.set_path(path)
            created = not path.exists()
            self.admin.ensure_exists(server_dir=self.instance.server_dir, settings=settings)
            if created:
                self.log(f"Created serveradmin.xml at: {path}", "INFO")
            self.admin.load()
            self._changed("admin")
        except Exception as err:
            self.log(f"Could not load serveradmin.xml: {err}", "WARNING")

    def admin_ready(self) -> bool:
        return self.admin.admin_path is not None

    def save_admin(
        self,
        users: List[Dict[str, str]],
        whitelist: List[Dict[str, str]],
        blacklist: List[Dict[str, str]],
        commands: List[Dict[str, str]],
    ) -> Path:
        path = self.admin_path()
        if path is None:
            raise ServiceError("Install the server first, then you can manage admins.")
        self.admin.set_path(path)
        self.admin.users = users
        self.admin.whitelist = whitelist
        self.admin.blacklist = blacklist
        self.admin.commands = commands
        try:
            self.admin.save()
        except OSError as err:
            raise ServiceError(f"Could not save serveradmin.xml: {err}") from err
        self.log(f"Saved serveradmin.xml to {path}", "SUCCESS")
        self._changed("admin")
        return path

"""
The server "instance": where the game files, Auger's own config file, and the
saves (user data) live.

Key rule: Auger edits ``serverconfig.auger.xml``, NOT the game's ``serverconfig.xml``.
The game's file belongs to the Steam depot and is reset by updates/validation;
Auger's file is never touched by the downloader, and the server is launched with
``-configfile=serverconfig.auger.xml``.

Default layout (per user):

    <data dir>/instances/default/server     game files (SteamCMD/DepotDownloader target)
    <data dir>/instances/default/userdata   worlds, saves, Saves/serveradmin.xml

The server folder can be changed (Browse); the user-data folder for *new*
configs is always the instance one. Configs adopted from an existing install keep
whatever UserDataFolder they already had, so nobody's worlds "disappear".
"""

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from .config_manager import ConfigManager
from .server_launcher import is_server_installed
from .utils import get_data_dir

AUGER_CONFIG_NAME = "serverconfig.auger.xml"
STOCK_CONFIG_NAME = "serverconfig.xml"
DEFAULT_INSTANCE = "default"


def instance_root(name: str = DEFAULT_INSTANCE) -> Path:
    return get_data_dir() / "instances" / name


def default_server_dir(name: str = DEFAULT_INSTANCE) -> Path:
    return instance_root(name) / "server"


def default_userdata_dir(name: str = DEFAULT_INSTANCE) -> Path:
    return instance_root(name) / "userdata"


def legacy_server_dirs() -> List[Path]:
    """Install locations used by earlier Auger versions (still auto-detected)."""
    return [get_data_dir() / "7dtd_server"]


@dataclass
class ServerInstance:
    server_dir: Path
    name: str = DEFAULT_INSTANCE

    @property
    def config_path(self) -> Path:
        return self.server_dir / AUGER_CONFIG_NAME

    @property
    def stock_config_path(self) -> Path:
        return self.server_dir / STOCK_CONFIG_NAME

    @property
    def userdata_dir(self) -> Path:
        return default_userdata_dir(self.name)

    def is_installed(self) -> bool:
        return is_server_installed(self.server_dir)

    def has_auger_config(self) -> bool:
        return self.config_path.is_file()

    def managed_values(self) -> Dict[str, str]:
        """Values Auger controls in configs it creates."""
        return {
            "UserDataFolder": str(self.userdata_dir),
            "AdminFileName": "serveradmin.xml",
        }

    # ------------------------------------------------------------------
    # Creating / adopting Auger's config file
    # ------------------------------------------------------------------
    def create_fresh_config(self) -> Path:
        """New install: start from the game's own config, then apply Auger's managed values."""
        self.userdata_dir.mkdir(parents=True, exist_ok=True)
        manager = ConfigManager()
        if self.stock_config_path.is_file():
            shutil.copy2(self.stock_config_path, self.config_path)
            manager.set_config_path(self.config_path)
            manager.load_config()
        else:
            manager.generate_default_file(self.config_path)
        manager.save_config(self.managed_values(), make_backup=False)
        return self.config_path

    def adopt_existing_config(self) -> Path:
        """Existing install: copy the current game config as-is (keeps the user's worlds where they are)."""
        if self.stock_config_path.is_file():
            shutil.copy2(self.stock_config_path, self.config_path)
        else:
            manager = ConfigManager()
            manager.generate_default_file(self.config_path)
        return self.config_path

    def ensure_config(self, fresh: bool) -> Optional[str]:
        """Make sure Auger's config exists. Returns a short description of what was done, or None."""
        if self.has_auger_config():
            return None
        if fresh:
            self.create_fresh_config()
            return "created"
        self.adopt_existing_config()
        return "adopted"

    def merge_new_stock_keys(self) -> List[str]:
        """After a game update, add any properties the new game version introduced.

        Existing values in Auger's config are never changed.
        """
        if not (self.has_auger_config() and self.stock_config_path.is_file()):
            return []
        stock = ConfigManager(self.stock_config_path)
        stock_values = stock.load_config_raw()
        mine = ConfigManager(self.config_path)
        my_values = mine.load_config_raw()
        missing = {k: v for k, v in stock_values.items() if k not in my_values}
        if missing:
            mine.save_config(missing, make_backup=True)
        return sorted(missing)

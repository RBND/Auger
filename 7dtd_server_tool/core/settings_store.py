"""
Persists application settings such as install paths between sessions.
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional

from core.utils import get_app_dir

SETTINGS_FILENAME = "manager_settings.json"


def get_settings_path() -> Path:
    return get_app_dir() / SETTINGS_FILENAME


def load_settings() -> Dict[str, Any]:
    path = get_settings_path()
    if not path.exists():
        return {}

    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_settings(
    steamcmd_path: Optional[Path] = None,
    server_dir: Optional[Path] = None,
) -> None:
    data = load_settings()

    if steamcmd_path is not None:
        data["steamcmd_path"] = str(Path(steamcmd_path).resolve())

    if server_dir is not None:
        data["server_dir"] = str(Path(server_dir).resolve())

    path = get_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)


def get_saved_path(key: str) -> Optional[Path]:
    value = load_settings().get(key, "")
    if not value:
        return None

    path = Path(value)
    return path if path.exists() else None

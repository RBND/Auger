"""
Persists application settings such as install paths between sessions.
"""

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from core.utils import get_app_data_dir, get_app_dir

SETTINGS_FILENAME = "manager_settings.json"


def get_settings_path() -> Path:
    """Return the per-user settings path, migrating legacy settings on first use."""
    override = os.environ.get("AUGER_SETTINGS_DIR")
    settings_dir = Path(override) if override else get_app_data_dir()
    settings_path = settings_dir / SETTINGS_FILENAME
    legacy_path = get_app_dir() / SETTINGS_FILENAME

    if not settings_path.exists() and legacy_path.exists():
        settings_dir.mkdir(parents=True, exist_ok=True)
        try:
            settings_path.write_bytes(legacy_path.read_bytes())
        except OSError:
            # The legacy file is optional; a failed migration must not block startup.
            pass

    return settings_path


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
    server_branch: Optional[str] = None,
    validate_server_files: Optional[bool] = None,
) -> None:
    """Persist non-secret settings using an atomic file replacement.

    Branch passwords intentionally are never accepted or written here.
    """
    data = load_settings()

    if steamcmd_path is not None:
        data["steamcmd_path"] = str(Path(steamcmd_path).resolve())

    if server_dir is not None:
        data["server_dir"] = str(Path(server_dir).resolve())

    if server_branch is not None:
        data["server_branch"] = server_branch

    if validate_server_files is not None:
        data["validate_server_files"] = validate_server_files

    path = get_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as handle:
            temp_path = Path(handle.name)
            json.dump(data, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink(missing_ok=True)


def get_saved_path(key: str) -> Optional[Path]:
    value = load_settings().get(key, "")
    if not value:
        return None

    path = Path(value)
    return path if path.exists() else None


def get_saved_value(key: str, default: Any = None) -> Any:
    """Return a non-path setting without treating a missing value as an error."""
    return load_settings().get(key, default)

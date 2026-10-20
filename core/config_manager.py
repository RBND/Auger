"""
XML Parsing, Reading, Saving, Backup, and Resetting for 7 Days to Die serverconfig.xml.
"""

import os
import re
import shutil
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from .config_schema import GROUPS, default_values

_SANDBOX_XML_VALUE = re.compile(r'name\s*=\s*"SandboxCode"[^>]*?value\s*=\s*"([^"]*)"', re.IGNORECASE)
_SANDBOX_ALLOWED = re.compile(r"[A-Za-z0-9+/=_.\-]{1,4096}")


def normalize_sandbox_code(raw: str) -> str:
    """Clean a pasted Sandbox Code. Returns "" when the text is not code-like.

    Accepts a bare code, a quoted code, or a whole pasted
    ``<property name="SandboxCode" value="..."/>`` line.
    """
    if not raw:
        return ""
    text = raw.strip()
    match = _SANDBOX_XML_VALUE.search(text)
    if match:
        text = match.group(1)
    text = text.strip().strip("\"'")
    text = re.sub(r"\s+", "", text)
    return text if _SANDBOX_ALLOWED.fullmatch(text) else ""


# Default value for every known property, derived from the schema (single source of truth).
DEFAULT_CONFIG: Dict[str, str] = default_values()


class ConfigManager:
    """
    Manages loading, editing, saving, backing up, and resetting 7DTD serverconfig.xml files.
    Preserves XML comments and proper indentation formatting.
    """

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path: Optional[Path] = Path(config_path).resolve() if config_path else None
        self.tree: Optional[ET.ElementTree] = None
        self.root: Optional[ET.Element] = None
        self.settings: Dict[str, str] = {}

    def set_config_path(self, path: Path) -> None:
        new_path = Path(path).resolve()
        if new_path != self.config_path:
            # Drop the tree parsed from the previous file.
            self.tree = None
            self.root = None
            self.settings = {}
        self.config_path = new_path

    def load_config_raw(self) -> Dict[str, str]:
        """Parse the file and return exactly the properties it contains (no defaults added).

        Comments are preserved in the in-memory tree (Python 3.8+) so a later save keeps them.
        """
        if not self.config_path or not self.config_path.exists():
            self.tree = None
            self.root = None
            return {}

        try:
            parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
            self.tree = ET.parse(str(self.config_path), parser=parser)
            self.root = self.tree.getroot()
        except Exception as err:
            raise RuntimeError(f"Failed to parse {self.config_path.name}: {err}") from err

        values: Dict[str, str] = {}
        for elem in self.root.iter("property"):
            name = elem.get("name")
            value = elem.get("value")
            if name is not None:
                values[name] = value if value is not None else ""
        return values

    def load_config(self) -> Dict[str, str]:
        """
        Parses serverconfig.xml while preserving XML comments (Python 3.8+).
        Returns a dictionary of key-value property settings, with defaults for any missing keys.
        """
        if not self.config_path or not self.config_path.exists():
            self.tree = None
            self.root = None
            self.settings = DEFAULT_CONFIG.copy()
            return self.settings

        self.settings = self.load_config_raw()
        # Ensure all default keys exist
        for key, val in DEFAULT_CONFIG.items():
            if key not in self.settings:
                self.settings[key] = val
        return self.settings

    def create_backup(self) -> Optional[Path]:
        """
        Creates a timestamped backup copy of serverconfig.xml in the same directory.
        """
        if not self.config_path or not self.config_path.exists():
            return None

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        stem = self.config_path.name[: -len(".xml")] if self.config_path.name.endswith(".xml") else self.config_path.name
        backup_path = self.config_path.parent / f"{stem}_{timestamp}.xml.bak"
        latest_bak = self.config_path.parent / f"{self.config_path.name}.bak"

        try:
            shutil.copy2(self.config_path, backup_path)
            shutil.copy2(self.config_path, latest_bak)
            return backup_path
        except Exception as err:
            print(f"[Warning] Failed to create backup: {err}")
            return None

    def save_config(self, new_settings: Dict[str, str], make_backup: bool = True) -> bool:
        """
        Updates property elements in memory and writes to serverconfig.xml.
        Creates a backup before saving if make_backup is True.
        """
        if not self.config_path:
            raise ValueError("No configuration file path specified.")

        if make_backup and self.config_path.exists():
            self.create_backup()

        # Never replace an existing file with only the keys being changed.
        if self.root is None and self.config_path.exists():
            self.load_config_raw()

        self.settings.update(new_settings)

        if self.root is None:
            self.root = ET.Element("ServerSettings")
            self.tree = ET.ElementTree(self.root)

        existing_keys = set()
        for elem in self.root.iter("property"):
            name = elem.get("name")
            if name in new_settings:
                elem.set("value", str(new_settings[name]))
                existing_keys.add(name)

        for key, val in new_settings.items():
            if key not in existing_keys:
                prop = ET.SubElement(self.root, "property")
                prop.set("name", key)
                prop.set("value", str(val))

        try:
            ET.indent(self.tree, space="  ")
        except AttributeError:
            pass

        temp_path: Optional[Path] = None
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=self.config_path.parent, delete=False
            ) as handle:
                temp_path = Path(handle.name)
                handle.write(b'<?xml version="1.0"?>\n')
                self.tree.write(handle, encoding="utf-8", xml_declaration=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self.config_path)
            return True
        except Exception as err:
            raise IOError(f"Failed to save serverconfig.xml: {err}") from err
        finally:
            if temp_path and temp_path.exists():
                temp_path.unlink(missing_ok=True)

    def reset_to_defaults(self, make_backup: bool = True, keep: Optional[Dict[str, str]] = None) -> bool:
        """Restores configuration to default settings.

        ``keep`` values (e.g. Auger-managed file locations) override the defaults so a
        reset never moves the server's saves.
        """
        values = dict(DEFAULT_CONFIG)
        values.update(keep or {})
        existing = self.load_config_raw() if self.config_path and self.config_path.exists() else {}
        # Don't add empty properties the file never had (e.g. a commented-out UserDataFolder).
        values = {k: v for k, v in values.items() if str(v).strip() or k in existing}
        return self.save_config(values, make_backup=make_backup)

    def generate_default_file(self, target_path: Path) -> bool:
        """
        Generates a fresh serverconfig.xml with default parameters and inline section comments.
        """
        self.config_path = target_path
        self.root = ET.Element("ServerSettings")
        self.tree = ET.ElementTree(self.root)

        for group in GROUPS:
            comment = ET.Comment(f" {group.title} ")
            self.root.append(comment)
            for key in group.keys:
                if key == "UserDataFolder" and not DEFAULT_CONFIG.get(key):
                    continue  # the game treats this as "unset" only when the property is absent
                prop = ET.SubElement(self.root, "property")
                prop.set("name", key)
                prop.set("value", DEFAULT_CONFIG.get(key, ""))

        defaults = {k: v for k, v in DEFAULT_CONFIG.items() if k != "UserDataFolder" or v}
        return self.save_config(defaults, make_backup=False)

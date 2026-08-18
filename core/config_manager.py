"""
XML Parsing, Reading, Saving, Backup, and Resetting for 7 Days to Die serverconfig.xml.
"""

import os
import shutil
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List


# Default configuration dictionary — covers every property in the standard serverconfig.xml
DEFAULT_CONFIG: Dict[str, str] = {
    # --- Server Representation ---
    "ServerName": "My Game Host",
    "ServerDescription": "A 7 Days to Die server",
    "ServerWebsiteURL": "",
    "ServerPassword": "",
    "ServerLoginConfirmationText": "",
    "Region": "NorthAmericaEast",
    "Language": "English",
    # --- Networking ---
    "ServerPort": "26900",
    "ServerVisibility": "2",
    "ServerDisabledNetworkProtocols": "",
    "ServerMaxWorldTransferSpeedKiBs": "512",
    # --- Slots ---
    "ServerMaxPlayerCount": "8",
    "ServerReservedSlots": "0",
    "ServerReservedSlotsPermission": "100",
    "ServerAdminSlots": "0",
    "ServerAdminSlotsPermission": "0",
    # --- Web Dashboard ---
    "WebDashboardEnabled": "false",
    "WebDashboardPort": "8080",
    "WebDashboardUrl": "",
    "EnableMapRendering": "false",
    # --- Telnet ---
    "TelnetEnabled": "true",
    "TelnetPort": "8081",
    "TelnetPassword": "",
    "TelnetFailedLoginLimit": "10",
    "TelnetFailedLoginsBlocktime": "10",
    # --- Terminal ---
    "TerminalWindowEnabled": "true",
    # --- File Locations ---
    "AdminFileName": "serveradmin.xml",
    "UserDataFolder": "",
    # --- Other Technical ---
    "ServerAllowCrossplay": "false",
    "EACEnabled": "true",
    "IgnoreEOSSanctions": "false",
    "HideCommandExecutionLog": "0",
    "MaxUncoveredMapChunksPerPlayer": "131072",
    "PersistentPlayerProfiles": "false",
    "MaxChunkAge": "-1",
    "SaveDataLimit": "-1",
    # --- World ---
    "GameWorld": "Navezgane",
    "WorldGenSeed": "MyGame",
    "WorldGenSize": "6144",
    "GameName": "MyGame",
    "GameMode": "GameModeSurvival",
    # --- Difficulty ---
    "PlayerSafeZoneLevel": "5",
    "PlayerSafeZoneHours": "5",
    # --- Game Rules ---
    "BuildCreate": "false",
    "BedrollDeadZoneSize": "15",
    "BedrollExpiryTime": "45",
    "AllowSpawnNearFriend": "2",
    "CameraRestrictionMode": "0",
    # --- Performance ---
    "MaxSpawnedZombies": "64",
    "MaxSpawnedAnimals": "50",
    "ServerMaxAllowedViewDistance": "12",
    "MaxQueuedMeshLayers": "1000",
    # --- Multiplayer ---
    "PartySharedKillRange": "100",
    "PlayerKillingMode": "3",
    # --- Land Claims ---
    "LandClaimCount": "5",
    "LandClaimSize": "41",
    "LandClaimDeadZone": "30",
    "LandClaimExpiryTime": "7",
    "LandClaimDecayMode": "0",
    "LandClaimOnlineDurabilityModifier": "4",
    "LandClaimOfflineDurabilityModifier": "4",
    "LandClaimOfflineDelay": "0",
    # --- Dynamic Mesh ---
    "DynamicMeshEnabled": "true",
    "DynamicMeshLandClaimOnly": "true",
    "DynamicMeshLandClaimBuffer": "3",
    "DynamicMeshMaxItemCache": "3",
    # --- Twitch ---
    "TwitchServerPermission": "90",
    "TwitchBloodMoonAllowed": "false",
    # --- Sandbox ---
    "SandboxCode": "AAAJABJACJADJARFBNC",
}


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
        self.config_path = Path(path).resolve()

    def load_config(self) -> Dict[str, str]:
        """
        Parses serverconfig.xml while preserving XML comments (Python 3.8+).
        Returns a dictionary of key-value property settings.
        """
        if not self.config_path or not self.config_path.exists():
            self.settings = DEFAULT_CONFIG.copy()
            return self.settings

        try:
            parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
            self.tree = ET.parse(str(self.config_path), parser=parser)
            self.root = self.tree.getroot()

            self.settings = {}
            for elem in self.root.iter("property"):
                name = elem.get("name")
                value = elem.get("value")
                if name is not None:
                    self.settings[name] = value if value is not None else ""

            # Ensure all default keys exist
            for key, val in DEFAULT_CONFIG.items():
                if key not in self.settings:
                    self.settings[key] = val

            return self.settings

        except Exception as err:
            raise RuntimeError(f"Failed to parse serverconfig.xml: {err}") from err

    def create_backup(self) -> Optional[Path]:
        """
        Creates a timestamped backup copy of serverconfig.xml in the same directory.
        """
        if not self.config_path or not self.config_path.exists():
            return None

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = self.config_path.parent / f"serverconfig_{timestamp}.xml.bak"
        latest_bak = self.config_path.parent / "serverconfig.xml.bak"

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

    def reset_to_defaults(self, make_backup: bool = True) -> bool:
        """Restores configuration to default settings."""
        return self.save_config(DEFAULT_CONFIG, make_backup=make_backup)

    def generate_default_file(self, target_path: Path) -> bool:
        """
        Generates a fresh serverconfig.xml with default parameters and inline section comments.
        """
        self.config_path = target_path
        self.root = ET.Element("ServerSettings")
        self.tree = ET.ElementTree(self.root)

        sections: List[Tuple[str, List[str]]] = [
            ("Server Representation", [
                "ServerName", "ServerDescription", "ServerWebsiteURL",
                "ServerPassword", "ServerLoginConfirmationText", "Region", "Language",
            ]),
            ("Networking", [
                "ServerPort", "ServerVisibility", "ServerDisabledNetworkProtocols",
                "ServerMaxWorldTransferSpeedKiBs",
            ]),
            ("Slots", [
                "ServerMaxPlayerCount", "ServerReservedSlots", "ServerReservedSlotsPermission",
                "ServerAdminSlots", "ServerAdminSlotsPermission",
            ]),
            ("Web Dashboard", [
                "WebDashboardEnabled", "WebDashboardPort", "WebDashboardUrl", "EnableMapRendering",
            ]),
            ("Telnet", [
                "TelnetEnabled", "TelnetPort", "TelnetPassword",
                "TelnetFailedLoginLimit", "TelnetFailedLoginsBlocktime",
            ]),
            ("Terminal", ["TerminalWindowEnabled"]),
            ("File Locations", ["AdminFileName", "UserDataFolder"]),
            ("Other Technical", [
                "ServerAllowCrossplay", "EACEnabled", "IgnoreEOSSanctions",
                "HideCommandExecutionLog", "MaxUncoveredMapChunksPerPlayer",
                "PersistentPlayerProfiles", "MaxChunkAge", "SaveDataLimit",
            ]),
            ("World", ["GameWorld", "WorldGenSeed", "WorldGenSize", "GameName", "GameMode"]),
            ("Difficulty", ["PlayerSafeZoneLevel", "PlayerSafeZoneHours"]),
            ("Game Rules", [
                "BuildCreate", "BedrollDeadZoneSize", "BedrollExpiryTime",
                "AllowSpawnNearFriend", "CameraRestrictionMode",
            ]),
            ("Performance", [
                "MaxSpawnedZombies", "MaxSpawnedAnimals",
                "ServerMaxAllowedViewDistance", "MaxQueuedMeshLayers",
            ]),
            ("Multiplayer", ["PartySharedKillRange", "PlayerKillingMode"]),
            ("Land Claims", [
                "LandClaimCount", "LandClaimSize", "LandClaimDeadZone",
                "LandClaimExpiryTime", "LandClaimDecayMode",
                "LandClaimOnlineDurabilityModifier", "LandClaimOfflineDurabilityModifier",
                "LandClaimOfflineDelay",
            ]),
            ("Dynamic Mesh", [
                "DynamicMeshEnabled", "DynamicMeshLandClaimOnly",
                "DynamicMeshLandClaimBuffer", "DynamicMeshMaxItemCache",
            ]),
            ("Twitch", ["TwitchServerPermission", "TwitchBloodMoonAllowed"]),
            ("Sandbox", ["SandboxCode"]),
        ]

        for section_title, keys in sections:
            comment = ET.Comment(f" {section_title} ")
            self.root.append(comment)
            for key in keys:
                prop = ET.SubElement(self.root, "property")
                prop.set("name", key)
                prop.set("value", DEFAULT_CONFIG.get(key, ""))

        return self.save_config(DEFAULT_CONFIG, make_backup=False)

    def ensure_server_folder_layout(self, server_dir: Path, make_backup: bool = False) -> Dict[str, str]:
        """
        Configure serverconfig.xml so serveradmin.xml lives beside serverconfig.xml.
        Sets UserDataFolder to the server install directory and AdminFileName to serveradmin.xml.
        """
        server_dir = server_dir.resolve()
        updates = {
            "AdminFileName": "serveradmin.xml",
            "UserDataFolder": str(server_dir),
        }
        self.save_config(updates, make_backup=make_backup)
        return updates

"""
Manages serveradmin.xml — reading, writing, and creating a default file.

Current 7DTD serveradmin.xml format:
  <users>      — admins/mods with platform, userid, name, permission_level
  <whitelist>  — whitelisted users/groups
  <blacklist>  — banned users
  <commands>   — permission overrides via <permission cmd="" permission_level="" />
  <apitokens>  — API tokens (read-only in this tool)
  <webmodules /> / <webusers /> — web dashboard entries (preserved on save)
"""

import shutil
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

DEFAULT_ADMIN_FILENAME = "serveradmin.xml"

ADMIN_XML_HEADER = """<!--
\tThis file holds the settings for who is banned, whitelisted, admins and server command permissions. The
\tadmin and whitelist sections can contain both individual Steam users as well as Steam groups.

\tIt is recommended to modify this file only through the respective console commands, like "admin", or
\tthe Web Dashboard.


\tUSER ID INSTRUCTIONS:
\t===============================================================
\tAny user entry uses two elements to identify whom it applies to.
\t- platform: Identifier of the platform the User ID belongs to, i.e. "EOS", "Steam", "XBL", "PSN"
\t- userid: The actual ID of the user on that platform. Examples:
\t  - EOS: "0002604bc42244e099c1bf05145fb71f"
\t  - Steam: SteamID64, e.g. "76561198021925107", see below
\tYou can look up the IDs in the logs, e.g. whenever a user logs in the ID is logged.

\tSTEAM ID INSTRUCTIONS:
\t===============================================================
\tYou can find the SteamID64 of any user with one of the following pages:
\thttps://steamdb.info/calculator/, https://steamid.io/lookup, https://steamid.co/
\thttps://steamid.co/ instructions:
\tInput the player's name in the search field. example: Kinyajuu
\tIf the name doesn't work, you can also use the url of their steam page.
\tYou will want the STEAM64ID. example: 76561198021925107

\tSTEAM GROUP ID INSTRUCTIONS:
\t===============================================================
\tYou can find the SteamID64 of any group by taking its address and adding
\t  /memberslistxml/?xml=1
\tto the end. You will get the XML information of the group which should have an entry
\tmemberList->groupID64.
\tExample: The 'Steam Universe' group has the address
\t  https://steamcommunity.com/groups/steamuniverse
\tSo you point your browser to
\t  https://steamcommunity.com/groups/steamuniverse/memberslistxml/?xml=1
\tAnd see that the groupID64 is 103582791434672565.

\tPERMISSION LEVEL INSTRUCTIONS:
\t===============================================================
\tpermission level : 0-1000, a user may run any command equal to or above their permission level.
\tUsers not given a permission level in this file will have a default permission level of 1000!

\tCOMMAND PERMISSIONS INSTRUCTIONS:
\t===============================================================
\tcmd : This is the command name, any command not in this list will not be usable by anyone but the server.
\tpermission level : 0-1000, a user may run any command equal to or above their permission level.
\tCommands not specified in this file will have a default permission level of 0!

\tEVERYTHING BETWEEN <!- - and - -> IS COMMENTED OUT! THE ENTRIES BELOW ARE EXAMPLES THAT ARE NOT ACTIVE!!!
-->
"""

DEFAULT_COMMAND_PERMISSIONS: List[Dict[str, str]] = [
    {"cmd": "chunkcache", "permission_level": "1000"},
    {"cmd": "createwebuser", "permission_level": "1000"},
    {"cmd": "debugshot", "permission_level": "1000"},
    {"cmd": "debugweather", "permission_level": "1000"},
    {"cmd": "decomgr", "permission_level": "1000"},
    {"cmd": "getgamepref", "permission_level": "1000"},
    {"cmd": "getgamestat", "permission_level": "1000"},
    {"cmd": "getlogpath", "permission_level": "1000"},
    {"cmd": "getoptions", "permission_level": "1000"},
    {"cmd": "gettime", "permission_level": "1000"},
    {"cmd": "gfx", "permission_level": "1000"},
    {"cmd": "graph", "permission_level": "1000"},
    {"cmd": "help", "permission_level": "1000"},
    {"cmd": "listplayerids", "permission_level": "1000"},
    {"cmd": "listthreads", "permission_level": "1000"},
    {"cmd": "loot", "permission_level": "1000"},
    {"cmd": "memcl", "permission_level": "1000"},
    {"cmd": "meshdatamanager", "permission_level": "1000"},
    {"cmd": "settempunit", "permission_level": "1000"},
    {"cmd": "uioptions", "permission_level": "1000"},
    {"cmd": "debugmenu", "permission_level": "0"},
    {"cmd": "giveself", "permission_level": "0"},
    {"cmd": "cvar", "permission_level": "1000"},
    {"cmd": "automation", "permission_level": "1000"},
    {"cmd": "ccphysics", "permission_level": "1000"},
    {"cmd": "exportcurrentconfigs", "permission_level": "1000"},
    {"cmd": "fallingblocks", "permission_level": "1000"},
    {"cmd": "getsandboxoptions", "permission_level": "1000"},
    {"cmd": "performanceprofiler", "permission_level": "1000"},
    {"cmd": "signeditordebug", "permission_level": "1000"},
    {"cmd": "signtexman", "permission_level": "1000"},
]


def _make_user(
    platform: str = "Steam",
    userid: str = "",
    name: str = "",
    permission_level: str = "0",
) -> Dict[str, str]:
    return {
        "platform": platform,
        "userid": userid,
        "name": name,
        "permission_level": permission_level,
    }


def _make_whitelist_user(platform: str = "Steam", userid: str = "", name: str = "") -> Dict[str, str]:
    return {"platform": platform, "userid": userid, "name": name}


def _make_blacklisted(
    platform: str = "Steam",
    userid: str = "",
    name: str = "",
    unbandate: str = "2099-12-31 00:00:00",
    reason: str = "",
) -> Dict[str, str]:
    return {
        "platform": platform,
        "userid": userid,
        "name": name,
        "unbandate": unbandate,
        "reason": reason,
    }


def _make_command(cmd: str = "", permission_level: str = "1000") -> Dict[str, str]:
    return {"cmd": cmd, "permission_level": permission_level}


def _xml_attr(value: str) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def resolve_admin_file_path(server_dir: Path, settings: Optional[Dict[str, str]] = None) -> Path:
    """
    Resolve serveradmin.xml beside serverconfig.xml when UserDataFolder is the server dir.
    """
    settings = settings or {}
    admin_filename = settings.get("AdminFileName", DEFAULT_ADMIN_FILENAME).strip() or DEFAULT_ADMIN_FILENAME

    admin_path = Path(admin_filename)
    if admin_path.is_absolute():
        return admin_path

    server_dir = server_dir.resolve()
    userdata = settings.get("UserDataFolder", "").strip()

    if userdata and Path(userdata).resolve() == server_dir:
        return server_dir / admin_filename

    if userdata:
        return Path(userdata) / "Saves" / admin_filename

    for candidate_dir in (server_dir, server_dir / "Saves"):
        candidate = candidate_dir / admin_filename
        if candidate.exists():
            return candidate

    return server_dir / admin_filename


class AdminManager:
    """Reads and writes serveradmin.xml for 7 Days to Die."""

    DEFAULT_ADMIN_FILENAME = DEFAULT_ADMIN_FILENAME

    def __init__(self, admin_path: Optional[Path] = None):
        self.admin_path: Optional[Path] = Path(admin_path).resolve() if admin_path else None
        self.users: List[Dict[str, str]] = []
        self.whitelist: List[Dict[str, str]] = []
        self.blacklist: List[Dict[str, str]] = []
        self.commands: List[Dict[str, str]] = []

    def set_path(self, path: Path) -> None:
        self.admin_path = Path(path).resolve()

    def ensure_exists(
        self,
        server_dir: Optional[Path] = None,
        settings: Optional[Dict[str, str]] = None,
    ) -> Path:
        if self.admin_path is None:
            if server_dir is None:
                raise ValueError("Either admin_path or server_dir must be provided.")
            self.admin_path = resolve_admin_file_path(server_dir, settings)

        if not self.admin_path.exists():
            self.admin_path.parent.mkdir(parents=True, exist_ok=True)
            self.commands = [entry.copy() for entry in DEFAULT_COMMAND_PERMISSIONS]
            self._write_file()

        return self.admin_path

    def _write_file(self) -> None:
        if not self.admin_path:
            raise ValueError("No admin file path set.")

        lines = ['<?xml version="1.0" encoding="UTF-8"?>', ADMIN_XML_HEADER, "<adminTools>"]

        lines.append("  <!-- Name in any entries is optional for display purposes only -->")
        lines.append("  <users>")
        if not self.users:
            lines.append(
                '    <!-- <user platform="Steam" userid="76561198021925107" '
                'name="Hint on who this user is" permission_level="0" /> -->'
            )
            lines.append(
                '    <!-- <group steamID="103582791434672565" name="Steam Universe" '
                'permission_level_default="1000" permission_level_mod="0" /> -->'
            )
        else:
            for entry in self.users:
                attrs = [
                    f'platform="{_xml_attr(entry["platform"])}"',
                    f'userid="{_xml_attr(entry["userid"])}"',
                ]
                if entry.get("name"):
                    attrs.append(f'name="{_xml_attr(entry["name"])}"')
                attrs.append(f'permission_level="{_xml_attr(entry["permission_level"])}"')
                lines.append(f'    <user {" ".join(attrs)} />')

        lines.append("  </users>")

        lines.append("  <whitelist>")
        lines.append("    <!-- ONLY PUT ITEMS IN WHITELIST IF YOU WANT WHITELIST ONLY ENABLED!!! -->")
        lines.append("    <!-- If there are any items in the whitelist, the whitelist only mode is enabled -->")
        lines.append("    <!-- Nobody can join that ISN'T in the whitelist or admins once whitelist only mode is enabled -->")
        lines.append("    <!-- Name is optional for display purposes only -->")
        if not self.whitelist:
            lines.append('    <!-- <user platform="" userid="" name="" /> -->')
            lines.append('    <!-- <group steamID="" name="" /> -->')
        else:
            for entry in self.whitelist:
                attrs = [
                    f'platform="{_xml_attr(entry["platform"])}"',
                    f'userid="{_xml_attr(entry["userid"])}"',
                ]
                if entry.get("name"):
                    attrs.append(f'name="{_xml_attr(entry["name"])}"')
                lines.append(f'    <user {" ".join(attrs)} />')
        lines.append("  </whitelist>")

        lines.append("  <blacklist>")
        if not self.blacklist:
            lines.append('    <!-- <blacklisted platform="" userid="" name="" unbandate="" reason="" /> -->')
        else:
            for entry in self.blacklist:
                attrs = [
                    f'platform="{_xml_attr(entry["platform"])}"',
                    f'userid="{_xml_attr(entry["userid"])}"',
                ]
                if entry.get("name"):
                    attrs.append(f'name="{_xml_attr(entry["name"])}"')
                attrs.append(f'unbandate="{_xml_attr(entry.get("unbandate", "2099-12-31 00:00:00"))}"')
                if entry.get("reason"):
                    attrs.append(f'reason="{_xml_attr(entry["reason"])}"')
                lines.append(f'    <blacklisted {" ".join(attrs)} />')
        lines.append("  </blacklist>")

        lines.append("  <commands>")
        if not self.commands:
            lines.append('    <!-- <permission cmd="dm" permission_level="0" /> -->')
            lines.append('    <!-- <permission cmd="kick" permission_level="1" /> -->')
            lines.append('    <!-- <permission cmd="say" permission_level="1000" /> -->')
        for entry in self.commands:
            lines.append(
                f'    <permission cmd="{_xml_attr(entry["cmd"])}" '
                f'permission_level="{_xml_attr(entry["permission_level"])}" />'
            )
        lines.append("  </commands>")

        lines.append("  <apitokens>")
        lines.append('    <!-- <token name="adminuser1" secret="supersecrettoken" permission_level="0" /> -->')
        lines.append("  </apitokens>")
        lines.append("  <webmodules />")
        lines.append("  <webusers />")
        lines.append("</adminTools>")

        self.admin_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.admin_path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write("\n".join(lines) + "\n")

    def load(self) -> None:
        self.users = []
        self.whitelist = []
        self.blacklist = []
        self.commands = []

        if not self.admin_path or not self.admin_path.exists():
            return

        try:
            tree = ET.parse(str(self.admin_path))
            root = tree.getroot()

            users_el = root.find("users")
            if users_el is not None:
                for el in users_el.findall("user"):
                    self.users.append(_make_user(
                        platform=el.get("platform", "Steam"),
                        userid=el.get("userid", el.get("steamID", el.get("steamId", ""))),
                        name=el.get("name", el.get("displayName", "")),
                        permission_level=el.get("permission_level", el.get("permissionLevel", "0")),
                    ))
            else:
                self._load_legacy_users(root)

            whitelist_el = root.find("whitelist")
            if whitelist_el is not None:
                for el in whitelist_el.findall("user"):
                    self.whitelist.append(_make_whitelist_user(
                        platform=el.get("platform", "Steam"),
                        userid=el.get("userid", el.get("steamID", el.get("steamId", ""))),
                        name=el.get("name", el.get("displayName", "")),
                    ))
                for el in whitelist_el.findall("wb"):
                    self.whitelist.append(_make_whitelist_user(
                        platform=el.get("platform", "Steam"),
                        userid=el.get("userid", el.get("steamID", el.get("steamId", ""))),
                        name=el.get("name", el.get("displayName", "")),
                    ))

            blacklist_el = root.find("blacklist")
            if blacklist_el is not None:
                for el in blacklist_el.findall("blacklisted"):
                    self.blacklist.append(_make_blacklisted(
                        platform=el.get("platform", "Steam"),
                        userid=el.get("userid", el.get("steamID", el.get("steamId", ""))),
                        name=el.get("name", el.get("displayName", "")),
                        unbandate=el.get("unbandate", "2099-12-31 00:00:00"),
                        reason=el.get("reason", ""),
                    ))
            else:
                self._load_legacy_blacklist(root)

            commands_el = root.find("commands")
            if commands_el is not None:
                for el in commands_el.findall("permission"):
                    self.commands.append(_make_command(
                        cmd=el.get("cmd", ""),
                        permission_level=el.get("permission_level", el.get("permissionLevel", "1000")),
                    ))
                for el in commands_el.findall("command"):
                    self.commands.append(_make_command(
                        cmd=el.get("command", el.get("cmd", "")),
                        permission_level=el.get("permission_level", el.get("permissionLevel", "1000")),
                    ))

        except Exception as err:
            raise RuntimeError(f"Failed to parse serveradmin.xml: {err}") from err

    def _load_legacy_users(self, root: ET.Element) -> None:
        for section, default_level in (("admins", "0"), ("moderators", "10")):
            section_el = root.find(section)
            if section_el is None:
                continue
            tag = "admin" if section == "admins" else "moderator"
            for el in section_el.findall(tag):
                self.users.append(_make_user(
                    platform="Steam",
                    userid=el.get("steamID", el.get("steamId", "")),
                    name=el.get("name", el.get("displayName", "")),
                    permission_level=el.get("permission_level", el.get("permissionLevel", default_level)),
                ))

    def _load_legacy_blacklist(self, root: ET.Element) -> None:
        banned_el = root.find("banned")
        if banned_el is None:
            return
        for el in banned_el.findall("ban"):
            self.blacklist.append(_make_blacklisted(
                platform="Steam",
                userid=el.get("steamID", el.get("steamId", "")),
                name=el.get("name", el.get("displayName", "")),
                unbandate=el.get("unbandate", "2099-12-31 00:00:00"),
                reason=el.get("reason", ""),
            ))

    def save(self) -> None:
        if not self.admin_path:
            raise ValueError("No admin file path set.")

        if self.admin_path.exists():
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            bak = self.admin_path.parent / f"serveradmin_{timestamp}.xml.bak"
            shutil.copy2(self.admin_path, bak)
            shutil.copy2(self.admin_path, self.admin_path.parent / "serveradmin.xml.bak")

        self._write_file()

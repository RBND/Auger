"""
Single source of truth for every serverconfig.xml property Auger knows about:
label, help text, input kind, choices (raw value + plain-English label), group,
tier, default value, and validation.

Previously this information was duplicated across FIELD_META / DROPDOWN_OPTIONS /
CONFIG_GROUPS (GUI) and DEFAULT_CONFIG / section lists (config manager).
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

# Input kinds
TEXT = "text"
INT = "int"
CHOICE = "choice"

# Tiers (used by the Quick / Advanced split in a later phase)
SIMPLE = "simple"      # shown to beginners
ADVANCED = "advanced"  # shown behind an "Advanced" toggle
MANAGED = "managed"    # controlled by Auger; hidden from beginners

ON_OFF: Tuple[Tuple[str, str], ...] = (("true", "On"), ("false", "Off"))
OFF_ON: Tuple[Tuple[str, str], ...] = (("false", "Off"), ("true", "On"))


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    help: str
    default: str
    kind: str = TEXT
    choices: Tuple[Tuple[str, str], ...] = ()
    tier: str = ADVANCED
    min_value: Optional[int] = None
    max_value: Optional[int] = None

    @property
    def choice_values(self) -> List[str]:
        return [raw for raw, _ in self.choices]

    def choice_label(self, raw: str) -> str:
        for value, label in self.choices:
            if value == raw:
                return label
        return raw


@dataclass(frozen=True)
class Group:
    title: str          # plain title, used for XML section comments
    icon: str           # emoji prefix for the GUI
    keys: Tuple[str, ...] = field(default_factory=tuple)

    @property
    def display_title(self) -> str:
        return f"{self.icon} {self.title}"


def _int(key, label, help_, default, tier=ADVANCED, lo=None, hi=None) -> Field:
    return Field(key, label, help_, default, INT, tier=tier, min_value=lo, max_value=hi)


def _choice(key, label, help_, default, choices, tier=ADVANCED) -> Field:
    return Field(key, label, help_, default, CHOICE, tuple(choices), tier)


_PORT = dict(lo=1, hi=65535)

FIELDS: Tuple[Field, ...] = (
    # --- Server Representation ---
    Field("ServerName", "Server Name:", "Name displayed in the server browser", "My Game Host", tier=SIMPLE),
    Field("ServerDescription", "Description:", "Short description shown in the server browser", "A 7 Days to Die server", tier=SIMPLE),
    Field("ServerWebsiteURL", "Website URL:", "Optional website/Discord link shown in browser", ""),
    Field("ServerPassword", "Password:", "Leave empty for no password", "", tier=SIMPLE),
    Field("ServerLoginConfirmationText", "Join Confirmation:", "Message player must confirm on join (leave empty to skip)", ""),
    _choice("Region", "Region:", "Geographic region for matchmaking", "NorthAmericaEast", [
        (r, r) for r in (
            "NorthAmericaEast", "NorthAmericaWest", "CentralAmerica", "SouthAmerica",
            "Europe", "Russia", "Asia", "MiddleEast", "Africa", "Oceania",
        )
    ]),
    Field("Language", "Language:", "Primary language for players (English name, e.g. German)", "English"),
    # --- Networking ---
    _int("ServerPort", "Server Port:", "Default: 26900 — keep in range 26900-26905 or 27015-27020 for LAN", "26900", **_PORT),
    _choice("ServerVisibility", "Visibility:", "2 = Public, 1 = Friends Only, 0 = Not Listed", "2",
            [("2", "Public"), ("1", "Friends only"), ("0", "Not listed")], tier=SIMPLE),
    _choice("ServerDisabledNetworkProtocols", "Disabled Protocols:", "Comma-separated: LiteNetLib, SteamNetworking", "SteamNetworking", [
        ("SteamNetworking", "SteamNetworking (game default)"),
        ("", "None"),
        ("LiteNetLib", "LiteNetLib"),
        ("LiteNetLib,SteamNetworking", "LiteNetLib + SteamNetworking"),
    ]),
    _int("ServerMaxWorldTransferSpeedKiBs", "Max World Transfer (KiB/s):", "Max speed to transfer world to new clients (max ~1300)", "512", lo=1),
    # --- Slots ---
    _int("ServerMaxPlayerCount", "Max Players:", "Maximum concurrent player slots", "8", tier=SIMPLE, lo=1),
    _int("ServerReservedSlots", "Reserved Slots:", "Slots reserved for privileged players", "0", lo=0),
    _int("ServerReservedSlotsPermission", "Reserved Slots Permission:", "Permission level required to use reserved slots", "100", lo=0, hi=1000),
    _int("ServerAdminSlots", "Admin Slots:", "Admin slots above the player limit", "0", lo=0),
    _int("ServerAdminSlotsPermission", "Admin Slots Permission:", "Permission level required for admin slots", "0", lo=0, hi=1000),
    # --- Web Dashboard ---
    _choice("WebDashboardEnabled", "Web Dashboard:", "Enable/disable the web dashboard", "false", OFF_ON),
    _int("WebDashboardPort", "Dashboard Port:", "Default: 8080", "8080", **_PORT),
    Field("WebDashboardUrl", "Dashboard URL:", "External URL if behind a reverse proxy (full URL required)", ""),
    _choice("EnableMapRendering", "Map Rendering:", "Render map tiles for the web dashboard", "false", OFF_ON),
    # --- Telnet ---
    _choice("TelnetEnabled", "Telnet Enabled:", "Enable/disable the Telnet remote console", "true", ON_OFF, tier=MANAGED),
    Field("TelnetPort", "Telnet Port:", "Default: 8081", "8081", INT, tier=MANAGED, min_value=1, max_value=65535),
    Field("TelnetPassword", "Telnet Password:", "Empty = loopback only; set password to allow remote access", "", tier=MANAGED),
    _int("TelnetFailedLoginLimit", "Telnet Login Limit:", "Wrong password attempts before IP block", "10", lo=0),
    _int("TelnetFailedLoginsBlocktime", "Telnet Block Time (s):", "How long an IP stays blocked after failed logins", "10", lo=0),
    # --- Terminal ---
    _choice("TerminalWindowEnabled", "Terminal Window:", "Show a console window for log/command input (Windows only)", "true", ON_OFF, tier=MANAGED),
    # --- File Locations ---
    Field("AdminFileName", "Admin File Name:", "Filename for serveradmin.xml (default: serveradmin.xml)", "serveradmin.xml", tier=MANAGED),
    Field("UserDataFolder", "User Data Folder:", "Where worlds, saves and serveradmin.xml are stored (set by Auger)", "", tier=MANAGED),
    # --- Other Technical ---
    _choice("ServerAllowCrossplay", "Allow Crossplay:", "Enable cross-platform play (may restrict some features)", "false", OFF_ON, tier=SIMPLE),
    _choice("EACEnabled", "EAC Enabled:", "Enable/disable Easy Anti-Cheat", "true", ON_OFF),
    _choice("IgnoreEOSSanctions", "Ignore EOS Sanctions:", "Allow sanctioned players to join", "false", OFF_ON),
    _choice("HideCommandExecutionLog", "Hide Command Log:", "0=Show all, 1=Hide Telnet, 2=Hide remote, 3=Hide all", "0", [
        ("0", "Show all"), ("1", "Hide Telnet"), ("2", "Hide remote"), ("3", "Hide all"),
    ]),
    _int("MaxUncoveredMapChunksPerPlayer", "Max Map Chunks/Player:", "Max chunks uncovered per player (default 131072 ≈ 32 km²)", "131072", lo=0),
    _choice("PersistentPlayerProfiles", "Persistent Profiles:", "Players must use the same profile they last joined with", "false", OFF_ON),
    _int("MaxChunkAge", "Max Chunk Age:", "In-game days before unvisited chunk resets (-1 = disabled)", "-1", lo=-1),
    _int("SaveDataLimit", "Save Data Limit (MB):", "Max disk space per saved game in MB (-1 = unlimited)", "-1", lo=-1),
    # --- World ---
    Field("GameWorld", "Game World:", "Navezgane, Pregen maps, or RWG for random generation", "Navezgane", tier=SIMPLE),
    Field("WorldGenSeed", "World Seed:", "Seed string for RWG world generation", "MyGame"),
    _choice("WorldGenSize", "World Size:", "RWG size: 6144, 8192, or 10240", "6144", [
        ("6144", "Small (6 km)"), ("8192", "Medium (8 km)"), ("10240", "Large (10 km)"),
    ], tier=SIMPLE),
    Field("GameName", "Save Game Name:", "Unique name for this save (alphanumeric + _-. )", "MyGame"),
    _choice("GameMode", "Game Mode:", "GameModeSurvival", "GameModeSurvival", [("GameModeSurvival", "Survival")]),
    # --- Difficulty ---
    _int("PlayerSafeZoneLevel", "Safe Zone Max Level:", "Players at or below this level get a spawn safe zone", "5", lo=0),
    _int("PlayerSafeZoneHours", "Safe Zone Hours:", "World-time hours the spawn safe zone lasts", "5", lo=0),
    # --- Game Rules ---
    _choice("BuildCreate", "Cheat Mode:", "Enable build/create cheat mode (god mode building)", "false", OFF_ON),
    _int("BedrollDeadZoneSize", "Bedroll Dead Zone:", "Radius (blocks) around bedroll where zombies won't spawn", "15", lo=0),
    _int("BedrollExpiryTime", "Bedroll Expiry (days):", "Real-world days before bedroll expires after owner goes offline", "45", lo=0),
    _choice("AllowSpawnNearFriend", "Spawn Near Friend:", "0=Off, 1=Always, 2=Friends in forest only", "2", [
        ("2", "Only in forest"), ("1", "Always"), ("0", "Off"),
    ]),
    _choice("CameraRestrictionMode", "Camera Mode:", "0=Free, 1=First person only, 2=Third person only", "0", [
        ("0", "Free"), ("1", "First person only"), ("2", "Third person only"),
    ]),
    # --- Performance ---
    _int("MaxSpawnedZombies", "Max Zombies:", "Global zombie cap — high values impact performance heavily", "64", lo=0),
    _int("MaxSpawnedAnimals", "Max Animals:", "Global animal cap — lower impact than zombies", "50", lo=0),
    _choice("ServerMaxAllowedViewDistance", "Max View Distance:", "Max client view distance in chunks (6–12)", "12",
            [(str(n), str(n)) for n in range(6, 13)]),
    _int("MaxQueuedMeshLayers", "Max Queued Mesh Layers:", "Concurrent chunk mesh layers — lower = less RAM, slower generation", "1000", lo=0),
    # --- Multiplayer ---
    _int("PartySharedKillRange", "Party Kill Share Range:", "Distance (m) to receive shared kill XP in party", "100", lo=0),
    _choice("PlayerKillingMode", "PvP Mode:", "0=No PvP, 1=Allies, 2=Strangers, 3=Everyone", "3", [
        ("3", "Everyone"), ("2", "Strangers only"), ("1", "Allies only"), ("0", "No PvP"),
    ], tier=SIMPLE),
    # --- Land Claims ---
    _int("LandClaimCount", "Land Claims Per Player:", "Max land claims allowed per player", "5", lo=0),
    _int("LandClaimSize", "Claim Size:", "Box radius of the protected keystone area (blocks)", "41", lo=0),
    _int("LandClaimDeadZone", "Claim Dead Zone:", "Minimum distance between keystones (blocks)", "30", lo=0),
    _int("LandClaimExpiryTime", "Claim Expiry (days):", "Real-world offline days before claims expire", "7", lo=0),
    _choice("LandClaimDecayMode", "Claim Decay Mode:", "0=Slow/Linear, 1=Fast/Exponential, 2=None (full protection)", "0", [
        ("0", "Slow (linear)"), ("1", "Fast (exponential)"), ("2", "None (full protection)"),
    ]),
    _int("LandClaimOnlineDurabilityModifier", "Online Hardness Modifier:", "Block hardness multiplier when owner is online (0=infinite)", "4", lo=0),
    _int("LandClaimOfflineDurabilityModifier", "Offline Hardness Modifier:", "Block hardness multiplier when owner is offline (0=infinite)", "4", lo=0),
    _int("LandClaimOfflineDelay", "Offline Delay (min):", "Minutes after logout before hardness transitions to offline value", "0", lo=0),
    # --- Dynamic Mesh ---
    _choice("DynamicMeshEnabled", "Dynamic Mesh:", "Enable the dynamic mesh system for detailed geometry", "true", ON_OFF),
    _choice("DynamicMeshLandClaimOnly", "Mesh in LCB Only:", "Restrict dynamic mesh to land claim areas", "true", ON_OFF),
    _int("DynamicMeshLandClaimBuffer", "Mesh LCB Radius:", "Chunk radius around LCB to apply dynamic mesh", "3", lo=0),
    _int("DynamicMeshMaxItemCache", "Mesh Item Cache:", "Concurrent mesh items processed (higher = more RAM)", "3", lo=0),
    # --- Twitch ---
    _int("TwitchServerPermission", "Twitch Permission Level:", "Permission level required to use Twitch integration", "90", lo=0, hi=1000),
    _choice("TwitchBloodMoonAllowed", "Twitch Blood Moon:", "Allow Twitch actions during blood moon (may cause lag)", "false", OFF_ON),
    # --- Sandbox ---
    Field(
        "SandboxCode", "Sandbox Code:",
        "All gameplay rules in one code (difficulty, loot, XP, day length, blood moons...). "
        "Copy it from the game's Sandbox Options screen; click ❓ for step-by-step help.",
        "AAAJABJACJADJARFBNC", tier=SIMPLE,
    ),
)

FIELDS_BY_KEY: Dict[str, Field] = {f.key: f for f in FIELDS}

SANDBOX_GROUP_TITLE = "Gameplay Rules (Sandbox Code)"

GROUPS: Tuple[Group, ...] = (
    Group("Server Representation", "🏷️", (
        "ServerName", "ServerDescription", "ServerWebsiteURL",
        "ServerPassword", "ServerLoginConfirmationText", "Region", "Language",
    )),
    Group(SANDBOX_GROUP_TITLE, "🧩", ("SandboxCode",)),
    Group("Networking", "🌐", (
        "ServerPort", "ServerVisibility", "ServerDisabledNetworkProtocols", "ServerMaxWorldTransferSpeedKiBs",
    )),
    Group("Slots", "👥", (
        "ServerMaxPlayerCount", "ServerReservedSlots", "ServerReservedSlotsPermission",
        "ServerAdminSlots", "ServerAdminSlotsPermission",
    )),
    Group("Web Dashboard", "📊", ("WebDashboardEnabled", "WebDashboardPort", "WebDashboardUrl", "EnableMapRendering")),
    Group("Telnet Console", "💻", (
        "TelnetEnabled", "TelnetPort", "TelnetPassword", "TelnetFailedLoginLimit", "TelnetFailedLoginsBlocktime",
    )),
    Group("Terminal Window", "🪟", ("TerminalWindowEnabled",)),
    Group("File Locations", "📁", ("AdminFileName", "UserDataFolder")),
    Group("Other Technical Settings", "⚙️", (
        "ServerAllowCrossplay", "EACEnabled", "IgnoreEOSSanctions", "HideCommandExecutionLog",
        "MaxUncoveredMapChunksPerPlayer", "PersistentPlayerProfiles", "MaxChunkAge", "SaveDataLimit",
    )),
    Group("World", "🌍", ("GameWorld", "WorldGenSeed", "WorldGenSize", "GameName", "GameMode")),
    Group("Difficulty", "⚠️", ("PlayerSafeZoneLevel", "PlayerSafeZoneHours")),
    Group("Game Rules", "📜", (
        "BuildCreate", "BedrollDeadZoneSize", "BedrollExpiryTime", "AllowSpawnNearFriend", "CameraRestrictionMode",
    )),
    Group("Performance", "🖥️", ("MaxSpawnedZombies", "MaxSpawnedAnimals", "ServerMaxAllowedViewDistance", "MaxQueuedMeshLayers")),
    Group("Multiplayer", "🤝", ("PartySharedKillRange", "PlayerKillingMode")),
    Group("Land Claims", "🏠", (
        "LandClaimCount", "LandClaimSize", "LandClaimDeadZone", "LandClaimExpiryTime", "LandClaimDecayMode",
        "LandClaimOnlineDurabilityModifier", "LandClaimOfflineDurabilityModifier", "LandClaimOfflineDelay",
    )),
    Group("Dynamic Mesh", "🔷", (
        "DynamicMeshEnabled", "DynamicMeshLandClaimOnly", "DynamicMeshLandClaimBuffer", "DynamicMeshMaxItemCache",
    )),
    Group("Twitch Integration", "📺", ("TwitchServerPermission", "TwitchBloodMoonAllowed")),
)


def default_values() -> Dict[str, str]:
    """Default value for every known property (insertion-ordered like FIELDS)."""
    return {f.key: f.default for f in FIELDS}


def fields_in_tier(*tiers: str) -> List[Field]:
    return [f for f in FIELDS if f.tier in tiers]


def validate_values(
    values: Dict[str, str],
    keys: Optional[Sequence[str]] = None,
    strict_choices: bool = False,
) -> List[str]:
    """Return human-readable problems with ``values`` (empty list = valid).

    Only known fields are checked; unknown properties (from newer game versions) pass through.
    Choice values are only checked when ``strict_choices`` is set, because an existing
    config may legitimately contain values Auger doesn't list yet.
    """
    problems: List[str] = []
    for key in keys if keys is not None else values.keys():
        spec = FIELDS_BY_KEY.get(key)
        if spec is None:
            continue
        raw = str(values.get(key, "")).strip()
        name = spec.label.rstrip(":")
        if spec.kind == INT:
            try:
                number = int(raw)
            except ValueError:
                problems.append(f"{name} must be a whole number (got '{raw}').")
                continue
            if spec.min_value is not None and number < spec.min_value:
                problems.append(f"{name} must be at least {spec.min_value}.")
            if spec.max_value is not None and number > spec.max_value:
                problems.append(f"{name} must be at most {spec.max_value}.")
        elif strict_choices and spec.kind == CHOICE and spec.choices and raw not in spec.choice_values:
            problems.append(f"{name} has an unknown value '{raw}'.")
    return problems


def _self_check() -> None:
    grouped = [k for g in GROUPS for k in g.keys]
    assert len(grouped) == len(set(grouped)), "a field appears in two groups"
    assert set(grouped) == set(FIELDS_BY_KEY), "every field must be in exactly one group"
    for f in FIELDS:
        if f.kind == CHOICE:
            assert f.default in f.choice_values, f"default for {f.key} is not a valid choice"


_self_check()

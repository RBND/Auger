"""
Main Tkinter application window, layout, tabs, state management, and thread event loop integration.
"""

import queue
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Dict, List, Optional, Tuple

from core.admin_manager import AdminManager, resolve_admin_file_path
from core.config_manager import ConfigManager
from core.detector import find_7dtd_server, find_steamcmd
from core.installer import InstallationManager
from core.utils import (
    get_app_dir,
    get_executable_name,
    launch_batch_in_new_window,
    launch_detached_process,
    open_folder,
)
from core.settings_store import get_saved_path, get_saved_value, save_settings
from gui.views import LoggerTextBox, SteamCMDMissingModal

PLATFORM_OPTIONS = ["Steam", "EOS", "XBL", "PSN"]
SERVER_BRANCH_STABLE = "Stable (public)"
SERVER_BRANCH_EXPERIMENTAL = "Latest Experimental"
SERVER_BRANCH_CUSTOM = "Custom branch"
SERVER_BRANCH_OPTIONS = [
    SERVER_BRANCH_STABLE,
    SERVER_BRANCH_EXPERIMENTAL,
    SERVER_BRANCH_CUSTOM,
]
SERVER_BRANCH_VALUES = {
    SERVER_BRANCH_STABLE: "public",
    SERVER_BRANCH_EXPERIMENTAL: "latest_experimental",
}
# Dropdown options for config fields with a small discrete set of choices
# ---------------------------------------------------------------------------
DROPDOWN_OPTIONS: Dict[str, List[str]] = {
    "Region": [
        "NorthAmericaEast", "NorthAmericaWest", "CentralAmerica", "SouthAmerica",
        "Europe", "Russia", "Asia", "MiddleEast", "Africa", "Oceania",
    ],
    "ServerVisibility": ["2", "1", "0"],
    "ServerDisabledNetworkProtocols": [
        "",
        "LiteNetLib",
        "SteamNetworking",
        "LiteNetLib,SteamNetworking",
    ],
    "WebDashboardEnabled": ["false", "true"],
    "EnableMapRendering": ["false", "true"],
    "TelnetEnabled": ["true", "false"],
    "TerminalWindowEnabled": ["true", "false"],
    "ServerAllowCrossplay": ["false", "true"],
    "EACEnabled": ["true", "false"],
    "IgnoreEOSSanctions": ["false", "true"],
    "HideCommandExecutionLog": ["0", "1", "2", "3"],
    "PersistentPlayerProfiles": ["false", "true"],
    "GameWorld": ["Navezgane", "Pregen06k01", "Pregen06k02", "Pregen08k01", "Pregen08k02", "RWG"],
    "WorldGenSize": ["6144", "8192", "10240"],
    "GameMode": ["GameModeSurvival"],
    "BuildCreate": ["false", "true"],
    "AllowSpawnNearFriend": ["2", "1", "0"],
    "CameraRestrictionMode": ["0", "1", "2"],
    "ServerMaxAllowedViewDistance": ["6", "7", "8", "9", "10", "11", "12"],
    "PlayerKillingMode": ["3", "2", "1", "0"],
    "LandClaimDecayMode": ["0", "1", "2"],
    "DynamicMeshEnabled": ["true", "false"],
    "DynamicMeshLandClaimOnly": ["true", "false"],
    "TwitchBloodMoonAllowed": ["false", "true"],
}

# Human-readable labels and tooltips for every config property
# Each entry: (display_label, tooltip_text)
FIELD_META: Dict[str, Tuple[str, str]] = {
    # Server Representation
    "ServerName": ("Server Name:", "Name displayed in the server browser"),
    "ServerDescription": ("Description:", "Short description shown in the server browser"),
    "ServerWebsiteURL": ("Website URL:", "Optional website/Discord link shown in browser"),
    "ServerPassword": ("Password:", "Leave empty for no password"),
    "ServerLoginConfirmationText": ("Join Confirmation:", "Message player must confirm on join (leave empty to skip)"),
    "Region": ("Region:", "Geographic region for matchmaking"),
    "Language": ("Language:", "Primary language for players (English name, e.g. German)"),
    # Networking
    "ServerPort": ("Server Port:", "Default: 26900 — keep in range 26900-26905 or 27015-27020 for LAN"),
    "ServerVisibility": ("Visibility:", "2 = Public, 1 = Friends Only, 0 = Not Listed"),
    "ServerDisabledNetworkProtocols": ("Disabled Protocols:", "Comma-separated: LiteNetLib, SteamNetworking"),
    "ServerMaxWorldTransferSpeedKiBs": ("Max World Transfer (KiB/s):", "Max speed to transfer world to new clients (max ~1300)"),
    # Slots
    "ServerMaxPlayerCount": ("Max Players:", "Maximum concurrent player slots"),
    "ServerReservedSlots": ("Reserved Slots:", "Slots reserved for privileged players"),
    "ServerReservedSlotsPermission": ("Reserved Slots Permission:", "Permission level required to use reserved slots"),
    "ServerAdminSlots": ("Admin Slots:", "Admin slots above the player limit"),
    "ServerAdminSlotsPermission": ("Admin Slots Permission:", "Permission level required for admin slots"),
    # Web Dashboard
    "WebDashboardEnabled": ("Web Dashboard:", "Enable/disable the web dashboard"),
    "WebDashboardPort": ("Dashboard Port:", "Default: 8080"),
    "WebDashboardUrl": ("Dashboard URL:", "External URL if behind a reverse proxy (full URL required)"),
    "EnableMapRendering": ("Map Rendering:", "Render map tiles for the web dashboard"),
    # Telnet
    "TelnetEnabled": ("Telnet Enabled:", "Enable/disable the Telnet remote console"),
    "TelnetPort": ("Telnet Port:", "Default: 8081"),
    "TelnetPassword": ("Telnet Password:", "Empty = loopback only; set password to allow remote access"),
    "TelnetFailedLoginLimit": ("Telnet Login Limit:", "Wrong password attempts before IP block"),
    "TelnetFailedLoginsBlocktime": ("Telnet Block Time (s):", "How long an IP stays blocked after failed logins"),
    # Terminal
    "TerminalWindowEnabled": ("Terminal Window:", "Show a console window for log/command input (Windows only)"),
    # File Locations
    "AdminFileName": ("Admin File Name:", "Filename for serveradmin.xml (default: serveradmin.xml)"),
    "UserDataFolder": ("User Data Folder:", "Absolute path to server user data (auto-set to server install folder)"),
    # Other Technical
    "ServerAllowCrossplay": ("Allow Crossplay:", "Enable cross-platform play (may restrict some features)"),
    "EACEnabled": ("EAC Enabled:", "Enable/disable Easy Anti-Cheat"),
    "IgnoreEOSSanctions": ("Ignore EOS Sanctions:", "Allow sanctioned players to join"),
    "HideCommandExecutionLog": ("Hide Command Log:", "0=Show all, 1=Hide Telnet, 2=Hide remote, 3=Hide all"),
    "MaxUncoveredMapChunksPerPlayer": ("Max Map Chunks/Player:", "Max chunks uncovered per player (default 131072 ≈ 32 km²)"),
    "PersistentPlayerProfiles": ("Persistent Profiles:", "Players must use the same profile they last joined with"),
    "MaxChunkAge": ("Max Chunk Age:", "In-game days before unvisited chunk resets (-1 = disabled)"),
    "SaveDataLimit": ("Save Data Limit (MB):", "Max disk space per saved game in MB (-1 = unlimited)"),
    # World
    "GameWorld": ("Game World:", "Navezgane, Pregen maps, or RWG for random generation"),
    "WorldGenSeed": ("World Seed:", "Seed string for RWG world generation"),
    "WorldGenSize": ("World Size:", "RWG size: 6144, 8192, or 10240"),
    "GameName": ("Save Game Name:", "Unique name for this save (alphanumeric + _-. )"),
    "GameMode": ("Game Mode:", "GameModeSurvival"),
    # Difficulty
    "PlayerSafeZoneLevel": ("Safe Zone Max Level:", "Players at or below this level get a spawn safe zone"),
    "PlayerSafeZoneHours": ("Safe Zone Hours:", "World-time hours the spawn safe zone lasts"),
    # Game Rules
    "BuildCreate": ("Cheat Mode:", "Enable build/create cheat mode (god mode building)"),
    "BedrollDeadZoneSize": ("Bedroll Dead Zone:", "Radius (blocks) around bedroll where zombies won't spawn"),
    "BedrollExpiryTime": ("Bedroll Expiry (days):", "Real-world days before bedroll expires after owner goes offline"),
    "AllowSpawnNearFriend": ("Spawn Near Friend:", "0=Off, 1=Always, 2=Friends in forest only"),
    "CameraRestrictionMode": ("Camera Mode:", "0=Free, 1=First person only, 2=Third person only"),
    # Performance
    "MaxSpawnedZombies": ("Max Zombies:", "Global zombie cap — high values impact performance heavily"),
    "MaxSpawnedAnimals": ("Max Animals:", "Global animal cap — lower impact than zombies"),
    "ServerMaxAllowedViewDistance": ("Max View Distance:", "Max client view distance in chunks (6–12)"),
    "MaxQueuedMeshLayers": ("Max Queued Mesh Layers:", "Concurrent chunk mesh layers — lower = less RAM, slower generation"),
    # Multiplayer
    "PartySharedKillRange": ("Party Kill Share Range:", "Distance (m) to receive shared kill XP in party"),
    "PlayerKillingMode": ("PvP Mode:", "0=No PvP, 1=Allies, 2=Strangers, 3=Everyone"),
    # Land Claims
    "LandClaimCount": ("Land Claims Per Player:", "Max land claims allowed per player"),
    "LandClaimSize": ("Claim Size:", "Box radius of the protected keystone area (blocks)"),
    "LandClaimDeadZone": ("Claim Dead Zone:", "Minimum distance between keystones (blocks)"),
    "LandClaimExpiryTime": ("Claim Expiry (days):", "Real-world offline days before claims expire"),
    "LandClaimDecayMode": ("Claim Decay Mode:", "0=Slow/Linear, 1=Fast/Exponential, 2=None (full protection)"),
    "LandClaimOnlineDurabilityModifier": ("Online Hardness Modifier:", "Block hardness multiplier when owner is online (0=infinite)"),
    "LandClaimOfflineDurabilityModifier": ("Offline Hardness Modifier:", "Block hardness multiplier when owner is offline (0=infinite)"),
    "LandClaimOfflineDelay": ("Offline Delay (min):", "Minutes after logout before hardness transitions to offline value"),
    # Dynamic Mesh
    "DynamicMeshEnabled": ("Dynamic Mesh:", "Enable the dynamic mesh system for detailed geometry"),
    "DynamicMeshLandClaimOnly": ("Mesh in LCB Only:", "Restrict dynamic mesh to land claim areas"),
    "DynamicMeshLandClaimBuffer": ("Mesh LCB Radius:", "Chunk radius around LCB to apply dynamic mesh"),
    "DynamicMeshMaxItemCache": ("Mesh Item Cache:", "Concurrent mesh items processed (higher = more RAM)"),
    # Twitch
    "TwitchServerPermission": ("Twitch Permission Level:", "Permission level required to use Twitch integration"),
    "TwitchBloodMoonAllowed": ("Twitch Blood Moon:", "Allow Twitch actions during blood moon (may cause lag)"),
    # Sandbox
    "SandboxCode": ("Sandbox Code:", "Difficulty/sandbox options code — use in-game copy button to generate"),
}

# Ordered group definitions for the config editor tab
CONFIG_GROUPS: List[Tuple[str, List[str]]] = [
    ("🏷️ Server Representation", [
        "ServerName", "ServerDescription", "ServerWebsiteURL",
        "ServerPassword", "ServerLoginConfirmationText", "Region", "Language",
    ]),
    ("🌐 Networking", [
        "ServerPort", "ServerVisibility",
        "ServerDisabledNetworkProtocols", "ServerMaxWorldTransferSpeedKiBs",
    ]),
    ("👥 Slots", [
        "ServerMaxPlayerCount", "ServerReservedSlots", "ServerReservedSlotsPermission",
        "ServerAdminSlots", "ServerAdminSlotsPermission",
    ]),
    ("📊 Web Dashboard", [
        "WebDashboardEnabled", "WebDashboardPort", "WebDashboardUrl", "EnableMapRendering",
    ]),
    ("💻 Telnet Console", [
        "TelnetEnabled", "TelnetPort", "TelnetPassword",
        "TelnetFailedLoginLimit", "TelnetFailedLoginsBlocktime",
    ]),
    ("🪟 Terminal Window", ["TerminalWindowEnabled"]),
    ("📁 File Locations", ["AdminFileName", "UserDataFolder"]),
    ("⚙️ Other Technical Settings", [
        "ServerAllowCrossplay", "EACEnabled", "IgnoreEOSSanctions",
        "HideCommandExecutionLog", "MaxUncoveredMapChunksPerPlayer",
        "PersistentPlayerProfiles", "MaxChunkAge", "SaveDataLimit",
    ]),
    ("🌍 World", [
        "GameWorld", "WorldGenSeed", "WorldGenSize", "GameName", "GameMode",
    ]),
    ("⚠️ Difficulty", ["PlayerSafeZoneLevel", "PlayerSafeZoneHours"]),
    ("📜 Game Rules", [
        "BuildCreate", "BedrollDeadZoneSize", "BedrollExpiryTime",
        "AllowSpawnNearFriend", "CameraRestrictionMode",
    ]),
    ("🖥️ Performance", [
        "MaxSpawnedZombies", "MaxSpawnedAnimals",
        "ServerMaxAllowedViewDistance", "MaxQueuedMeshLayers",
    ]),
    ("🤝 Multiplayer", ["PartySharedKillRange", "PlayerKillingMode"]),
    ("🏠 Land Claims", [
        "LandClaimCount", "LandClaimSize", "LandClaimDeadZone",
        "LandClaimExpiryTime", "LandClaimDecayMode",
        "LandClaimOnlineDurabilityModifier", "LandClaimOfflineDurabilityModifier",
        "LandClaimOfflineDelay",
    ]),
    ("🔷 Dynamic Mesh", [
        "DynamicMeshEnabled", "DynamicMeshLandClaimOnly",
        "DynamicMeshLandClaimBuffer", "DynamicMeshMaxItemCache",
    ]),
    ("📺 Twitch Integration", ["TwitchServerPermission", "TwitchBloodMoonAllowed"]),
    ("🧩 Sandbox", ["SandboxCode"]),
]

ADMIN_PERMISSION_LEVELS = ["0 (Superadmin)", "10 (Admin)", "100 (Moderator)", "1000 (Player)"]
ADMIN_PERMISSION_VALUES = ["0", "10", "100", "1000"]

ADMIN_SECTION_META: Dict[str, str] = {
    "users": (
        "Admins and moderators with elevated permissions. Supports individual users and Steam groups. "
        "Users not listed here default to permission level 1000."
    ),
    "whitelist": (
        "Whitelist-only mode activates when any entry exists here. When active, only listed users "
        "and admins can join the server."
    ),
    "blacklist": (
        "Banned players. Use unbandate for temporary bans (format: YYYY-MM-DD HH:MM:SS) or a far-future "
        "date for permanent bans."
    ),
    "commands": (
        "Console command permission overrides. Commands not listed default to permission level 0. "
        "A user may run any command at or above their permission level."
    ),
}

ADMIN_COLUMN_META: Dict[str, str] = {
    "platform": "Platform: Steam, EOS, XBL, or PSN",
    "userid": "User ID on that platform (SteamID64 for Steam, EOS ID for EOS, etc.)",
    "name": "Optional display name for reference only",
    "permission_level": "0-1000 (0=superadmin, 1000=default player)",
    "unbandate": "Ban expiry date: YYYY-MM-DD HH:MM:SS",
    "reason": "Optional ban reason shown in logs",
    "cmd": "Console command name (e.g. kick, ban, giveself)",
}


def _perm_display(val: str) -> str:
    """Convert a raw permission level string to a display string."""
    mapping = {"0": "0 (Superadmin)", "10": "10 (Admin)", "100": "100 (Moderator)", "1000": "1000 (Player)"}
    return mapping.get(str(val), str(val))


def _perm_raw(display: str) -> str:
    """Convert a display string back to a raw permission level."""
    return display.split(" ")[0]


class MainWindow:
    """
    Main application UI class managing notebook tabs, path configuration,
    server control buttons, XML configuration editor, and thread log events.
    """

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("7 Days to Die - Dedicated Server Manager")
        self.root.geometry("980x720")
        self.root.minsize(820, 620)

        # Thread-safe queue for async logs & status updates
        self.log_queue: queue.Queue = queue.Queue()

        # Core Managers
        self.installer = InstallationManager(self.log_queue)
        self.config_manager = ConfigManager()
        self.admin_manager = AdminManager()

        # State Variables
        self.steamcmd_path: Optional[Path] = None
        self.server_dir: Optional[Path] = None
        self.form_entries: Dict[str, Any] = {}   # ttk.Entry OR ttk.Combobox
        self.form_vars: Dict[str, tk.StringVar] = {}

        # Admin tab row tracking
        self._admin_rows: Dict[str, List[Dict[str, Any]]] = {
            "users": [], "whitelist": [], "blacklist": [], "commands": []
        }

        # UI StringVars for path displays and status indicators
        self.steamcmd_path_var = tk.StringVar(value="Searching...")
        self.steamcmd_status_var = tk.StringVar(value="Checking...")
        self.server_path_var = tk.StringVar(value="Searching...")
        self.server_status_var = tk.StringVar(value="Checking...")

        saved_branch = str(get_saved_value("server_branch", "public")).strip()
        if saved_branch == "public":
            saved_branch_choice = SERVER_BRANCH_STABLE
            custom_branch = ""
        elif saved_branch == "latest_experimental":
            saved_branch_choice = SERVER_BRANCH_EXPERIMENTAL
            custom_branch = ""
        else:
            saved_branch_choice = SERVER_BRANCH_CUSTOM
            custom_branch = saved_branch
        self.server_branch_choice_var = tk.StringVar(value=saved_branch_choice)
        self.custom_branch_var = tk.StringVar(value=custom_branch)
        self.beta_password_var = tk.StringVar()
        self.validate_server_files_var = tk.BooleanVar(
            value=bool(get_saved_value("validate_server_files", True))
        )

        self._build_ui()

        # Start periodic Queue Polling loop
        self.root.after(50, self.poll_log_queue)

        # Run initial auto-detection
        self.root.after(200, self.run_initial_detection)

    def _build_ui(self) -> None:
        """Constructs the notebook tabbed layout."""
        header_frame = ttk.Frame(self.root, padding=12)
        header_frame.pack(fill=tk.X)

        ttk.Label(
            header_frame,
            text="🎮 7 Days to Die - Dedicated Server Manager",
            font=("Segoe UI", 14, "bold"),
        ).pack(side=tk.LEFT)

        ttk.Label(
            header_frame,
            text="v1.20 Beta",
            font=("Segoe UI", 9, "italic"),
        ).pack(side=tk.RIGHT, padx=5)

        ttk.Separator(self.root, orient=tk.HORIZONTAL).pack(fill=tk.X)

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.tab_control = ttk.Frame(self.notebook, padding=10)
        self.tab_config = ttk.Frame(self.notebook, padding=10)
        self.tab_admin = ttk.Frame(self.notebook, padding=10)
        self.tab_logs = ttk.Frame(self.notebook, padding=10)

        self.notebook.add(self.tab_control, text=" 🚀 Server Control & Setup ")
        self.notebook.add(self.tab_config, text=" ⚙️ Config Editor ")
        self.notebook.add(self.tab_admin, text=" 🛡️ Server Admin ")
        self.notebook.add(self.tab_logs, text=" 📜 Live Logs ")

        self._build_control_tab()
        self._build_config_tab()
        self._build_admin_tab()
        self._build_logs_tab()

    # ------------------------------------------------------------------
    # TAB 1: SERVER CONTROL & SETUP
    # ------------------------------------------------------------------
    def _build_control_tab(self) -> None:
        paths_group = ttk.LabelFrame(self.tab_control, text=" Installation Paths & Detection ", padding=12)
        paths_group.pack(fill=tk.X, pady=(0, 10))

        r1 = ttk.Frame(paths_group)
        r1.pack(fill=tk.X, pady=4)
        ttk.Label(r1, text="SteamCMD Location:", width=20, anchor=tk.W).pack(side=tk.LEFT)
        ttk.Entry(r1, textvariable=self.steamcmd_path_var, state="readonly").pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(r1, text="📁 Browse", command=self.browse_steamcmd).pack(side=tk.LEFT, padx=2)
        ttk.Button(r1, text="📂 Open Folder", command=self.open_steamcmd_folder).pack(side=tk.LEFT, padx=2)

        r2 = ttk.Frame(paths_group)
        r2.pack(fill=tk.X, pady=4)
        ttk.Label(r2, text="7DTD Server Folder:", width=20, anchor=tk.W).pack(side=tk.LEFT)
        ttk.Entry(r2, textvariable=self.server_path_var, state="readonly").pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(r2, text="📁 Browse", command=self.browse_server_dir).pack(side=tk.LEFT, padx=2)
        ttk.Button(r2, text="📂 Open Folder", command=self.open_server_folder).pack(side=tk.LEFT, padx=2)

        r3 = ttk.Frame(paths_group)
        r3.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(r3, text="SteamCMD Status:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT)
        ttk.Label(r3, textvariable=self.steamcmd_status_var, foreground="#0066CC").pack(side=tk.LEFT, padx=(5, 30))
        ttk.Label(r3, text="7DTD Server Status:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT)
        ttk.Label(r3, textvariable=self.server_status_var, foreground="#0066CC").pack(side=tk.LEFT, padx=5)

        actions_group = ttk.LabelFrame(self.tab_control, text=" Management Actions ", padding=12)
        actions_group.pack(fill=tk.X, pady=(0, 10))

        btn_row1 = ttk.Frame(actions_group)
        btn_row1.pack(fill=tk.X, pady=4)

        self.btn_dl_steam = ttk.Button(
            btn_row1, text="⬇️ Download / Update SteamCMD", command=self.action_download_steamcmd,
        )
        self.btn_dl_steam.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)

        self.btn_dl_server = ttk.Button(
            btn_row1, text="🎮 Install / Update 7DTD Dedicated Server", command=self.action_install_server,
        )
        self.btn_dl_server.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)

        version_group = ttk.LabelFrame(
            self.tab_control, text=" Server Version ", padding=12
        )
        version_group.pack(fill=tk.X, pady=(0, 10))

        version_row = ttk.Frame(version_group)
        version_row.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(version_row, text="Version / branch:", width=20, anchor=tk.W).pack(side=tk.LEFT)
        self.server_branch_selector = ttk.Combobox(
            version_row,
            textvariable=self.server_branch_choice_var,
            values=SERVER_BRANCH_OPTIONS,
            state="readonly",
            width=24,
        )
        self.server_branch_selector.pack(side=tk.LEFT, padx=(0, 12))
        self.server_branch_selector.bind("<<ComboboxSelected>>", self._on_branch_selection_changed)
        ttk.Checkbutton(
            version_row,
            text="Validate files after download",
            variable=self.validate_server_files_var,
        ).pack(side=tk.LEFT)

        custom_row = ttk.Frame(version_group)
        custom_row.pack(fill=tk.X, pady=2)
        ttk.Label(custom_row, text="Custom branch:", width=20, anchor=tk.W).pack(side=tk.LEFT)
        self.custom_branch_entry = ttk.Entry(
            custom_row, textvariable=self.custom_branch_var, width=28
        )
        self.custom_branch_entry.pack(side=tk.LEFT, padx=(0, 12))
        ttk.Label(custom_row, text="Use only a branch published by the game developer.").pack(side=tk.LEFT)

        password_row = ttk.Frame(version_group)
        password_row.pack(fill=tk.X, pady=(2, 0))
        ttk.Label(password_row, text="Beta password:", width=20, anchor=tk.W).pack(side=tk.LEFT)
        ttk.Entry(password_row, textvariable=self.beta_password_var, show="•", width=28).pack(
            side=tk.LEFT, padx=(0, 12)
        )
        ttk.Label(password_row, text="Optional. Never saved or shown in logs.").pack(side=tk.LEFT)
        self._on_branch_selection_changed()

        launch_group = ttk.LabelFrame(self.tab_control, text=" Quick Launch ", padding=12)
        launch_group.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(
            launch_group,
            text="Launch the 7DTD Dedicated Server from the server installation folder.",
        ).pack(anchor=tk.W, pady=(0, 10))

        self.btn_start_server = ttk.Button(
            launch_group, text="🚀 START 7DTD SERVER", command=self.action_start_server,
        )
        self.btn_start_server.pack(fill=tk.X, ipady=8)

        log_preview_group = ttk.LabelFrame(self.tab_control, text=" Recent Activity ", padding=8)
        log_preview_group.pack(fill=tk.BOTH, expand=True)

        self.mini_logger = LoggerTextBox(log_preview_group)
        self.mini_logger.pack(fill=tk.BOTH, expand=True)

    # ------------------------------------------------------------------
    # TAB 2: CONFIG EDITOR
    # ------------------------------------------------------------------
    def _build_config_tab(self) -> None:
        # Action toolbar at bottom (packed first to anchor at BOTTOM)
        btn_bar = ttk.Frame(self.tab_config, padding=8)
        btn_bar.pack(side=tk.BOTTOM, fill=tk.X)

        ttk.Button(btn_bar, text="💾 Save Config", command=self.save_config).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_bar, text="📋 Reload Config", command=self.load_config_into_ui).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_bar, text="🔄 Reset to Defaults", command=self.reset_config).pack(side=tk.RIGHT, padx=5)

        ttk.Separator(self.tab_config, orient=tk.HORIZONTAL).pack(side=tk.BOTTOM, fill=tk.X, pady=(0, 4))

        # Scrollable canvas
        canvas = tk.Canvas(self.tab_config, borderwidth=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.tab_config, orient="vertical", command=canvas.yview)
        scroll_frame = ttk.Frame(canvas, padding=10)

        scroll_frame.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas_win = canvas.create_window((0, 0), window=scroll_frame, anchor="nw")

        def _on_canvas_resize(event: tk.Event) -> None:
            canvas.itemconfig(canvas_win, width=event.width)

        canvas.bind("<Configure>", _on_canvas_resize)
        canvas.configure(yscrollcommand=scrollbar.set)

        # Mouse wheel scrolling
        def _on_mousewheel(event: tk.Event) -> None:
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Build all groups
        for group_title, field_keys in CONFIG_GROUPS:
            gbox = ttk.LabelFrame(scroll_frame, text=f" {group_title} ", padding=10)
            gbox.pack(fill=tk.X, expand=True, pady=4)

            gbox.columnconfigure(0, weight=0, minsize=220)
            gbox.columnconfigure(1, weight=1, minsize=180)
            gbox.columnconfigure(2, weight=2)

            for idx, key in enumerate(field_keys):
                label_text, tooltip = FIELD_META.get(key, (key + ":", ""))

                lbl = ttk.Label(gbox, text=label_text, anchor=tk.W)
                lbl.grid(row=idx, column=0, sticky="w", padx=(0, 8), pady=3)

                var = tk.StringVar()
                self.form_vars[key] = var

                if key in DROPDOWN_OPTIONS:
                    widget = ttk.Combobox(
                        gbox,
                        textvariable=var,
                        values=DROPDOWN_OPTIONS[key],
                        state="readonly",
                    )
                else:
                    widget = ttk.Entry(gbox, textvariable=var)

                widget.grid(row=idx, column=1, sticky="ew", padx=(0, 8), pady=3)
                self.form_entries[key] = widget

                tip_lbl = ttk.Label(
                    gbox,
                    text=tooltip,
                    font=("Segoe UI", 8, "italic"),
                    foreground="#7F8C8D",
                    wraplength=320,
                    justify=tk.LEFT,
                )
                tip_lbl.grid(row=idx, column=2, sticky="w", pady=3)

    # ------------------------------------------------------------------
    # TAB 3: SERVER ADMIN
    # ------------------------------------------------------------------
    def _build_admin_tab(self) -> None:
        # Bottom button bar
        btn_bar = ttk.Frame(self.tab_admin, padding=8)
        btn_bar.pack(side=tk.BOTTOM, fill=tk.X)

        ttk.Button(btn_bar, text="💾 Save Admin File", command=self.save_admin).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_bar, text="📋 Reload", command=self.load_admin_into_ui).pack(side=tk.LEFT, padx=5)

        ttk.Separator(self.tab_admin, orient=tk.HORIZONTAL).pack(side=tk.BOTTOM, fill=tk.X, pady=(0, 4))

        # Scrollable canvas
        canvas = tk.Canvas(self.tab_admin, borderwidth=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.tab_admin, orient="vertical", command=canvas.yview)
        scroll_frame = ttk.Frame(canvas, padding=8)

        scroll_frame.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas_win = canvas.create_window((0, 0), window=scroll_frame, anchor="nw")

        def _on_canvas_resize(event: tk.Event) -> None:
            canvas.itemconfig(canvas_win, width=event.width)

        canvas.bind("<Configure>", _on_canvas_resize)
        canvas.configure(yscrollcommand=scrollbar.set)

        def _on_mousewheel(event: tk.Event) -> None:
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Store reference for rebuilding sections
        self._admin_scroll_frame = scroll_frame

        # Build admin sections
        self._build_admin_section(
            scroll_frame, "users", "👑 Users (Admins / Mods)",
            columns=["Platform", "User ID", "Display Name (optional)", "Permission Level"],
            col_keys=["platform", "userid", "name", "permission_level"],
            use_perm_dropdown=True,
            use_platform_dropdown=True,
        )

        self._build_admin_section(
            scroll_frame, "whitelist", "✅ Whitelist",
            columns=["Platform", "User ID", "Display Name (optional)"],
            col_keys=["platform", "userid", "name"],
            use_perm_dropdown=False,
            use_platform_dropdown=True,
        )

        self._build_admin_section(
            scroll_frame, "blacklist", "🚫 Blacklist",
            columns=["Platform", "User ID", "Display Name (optional)", "Unban Date", "Reason"],
            col_keys=["platform", "userid", "name", "unbandate", "reason"],
            use_perm_dropdown=False,
            use_platform_dropdown=True,
        )

        self._build_admin_section(
            scroll_frame, "commands", "🔧 Command Permissions",
            columns=["Command", "Permission Level"],
            col_keys=["cmd", "permission_level"],
            use_perm_dropdown=True,
            use_platform_dropdown=False,
        )

    def _build_admin_section(
        self,
        parent: ttk.Frame,
        section_key: str,
        title: str,
        columns: List[str],
        col_keys: List[str],
        use_perm_dropdown: bool,
        use_platform_dropdown: bool = False,
    ) -> None:
        """Build a single admin section with description and column tooltips."""
        frame = ttk.LabelFrame(parent, text=f" {title} ", padding=10)
        frame.pack(fill=tk.X, expand=True, pady=6)

        section_desc = ADMIN_SECTION_META.get(section_key, "")
        if section_desc:
            ttk.Label(
                frame,
                text=section_desc,
                font=("Segoe UI", 8, "italic"),
                foreground="#7F8C8D",
                wraplength=820,
                justify=tk.LEFT,
            ).pack(anchor=tk.W, pady=(0, 8))

        header_row = ttk.Frame(frame)
        header_row.pack(fill=tk.X)
        for col_title in columns:
            ttk.Label(header_row, text=col_title, font=("Segoe UI", 9, "bold"), anchor=tk.W).pack(
                side=tk.LEFT, expand=True, fill=tk.X, padx=3
            )
        ttk.Label(header_row, text="", width=8).pack(side=tk.LEFT)

        tip_row = ttk.Frame(frame)
        tip_row.pack(fill=tk.X, pady=(2, 0))
        for key in col_keys:
            tip_text = ADMIN_COLUMN_META.get(key, "")
            ttk.Label(
                tip_row,
                text=tip_text,
                font=("Segoe UI", 8, "italic"),
                foreground="#7F8C8D",
                wraplength=160,
                justify=tk.LEFT,
            ).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=3)
        ttk.Label(tip_row, text="", width=8).pack(side=tk.LEFT)

        ttk.Separator(frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(4, 0))

        # Row container
        rows_frame = ttk.Frame(frame)
        rows_frame.pack(fill=tk.X, expand=True)

        # Store meta for dynamic row building
        self._admin_rows[section_key] = []
        self._admin_row_meta = getattr(self, "_admin_row_meta", {})
        self._admin_row_meta[section_key] = {
            "frame": rows_frame,
            "col_keys": col_keys,
            "use_perm_dropdown": use_perm_dropdown,
            "use_platform_dropdown": use_platform_dropdown,
        }

        # Add button
        btn_row = ttk.Frame(frame)
        btn_row.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(
            btn_row,
            text=f"➕ Add Entry",
            command=lambda sk=section_key: self._add_admin_row(sk),
        ).pack(side=tk.LEFT, padx=2)

    def _add_admin_row(self, section_key: str, initial_values: Optional[Dict[str, str]] = None) -> None:
        """Dynamically add a new editable row to an admin section."""
        meta = self._admin_row_meta[section_key]
        rows_frame: ttk.Frame = meta["frame"]
        col_keys: List[str] = meta["col_keys"]
        use_perm_dropdown: bool = meta["use_perm_dropdown"]
        use_platform_dropdown: bool = meta.get("use_platform_dropdown", False)

        row_frame = ttk.Frame(rows_frame)
        row_frame.pack(fill=tk.X, pady=2)

        row_vars: Dict[str, tk.StringVar] = {}

        for key in col_keys:
            var = tk.StringVar()
            initial = ""
            if initial_values:
                raw = initial_values.get(key, "")
                if key == "permission_level" and use_perm_dropdown:
                    initial = _perm_display(raw)
                else:
                    initial = raw
            if key == "platform" and not initial:
                initial = "Steam"
            var.set(initial)
            row_vars[key] = var

            if key == "permission_level" and use_perm_dropdown:
                widget = ttk.Combobox(
                    row_frame,
                    textvariable=var,
                    values=ADMIN_PERMISSION_LEVELS,
                    state="readonly",
                    width=18,
                )
            elif key == "platform" and use_platform_dropdown:
                widget = ttk.Combobox(
                    row_frame,
                    textvariable=var,
                    values=PLATFORM_OPTIONS,
                    state="readonly",
                    width=10,
                )
            else:
                widget = ttk.Entry(row_frame, textvariable=var)

            widget.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=3)

        row_record = {"frame": row_frame, "vars": row_vars}
        self._admin_rows[section_key].append(row_record)

        def _delete(rec=row_record, sk=section_key):
            rec["frame"].destroy()
            self._admin_rows[sk].remove(rec)

        ttk.Button(row_frame, text="✖", width=3, command=_delete).pack(side=tk.LEFT, padx=2)

    def _collect_admin_section(self, section_key: str) -> List[Dict[str, str]]:
        """Collect current values from all rows in a section."""
        meta = self._admin_row_meta[section_key]
        col_keys = meta["col_keys"]
        use_perm_dropdown = meta["use_perm_dropdown"]

        results = []
        for row_record in self._admin_rows[section_key]:
            entry: Dict[str, str] = {}
            for key in col_keys:
                raw_val = row_record["vars"][key].get()
                if key == "permission_level" and use_perm_dropdown:
                    raw_val = _perm_raw(raw_val)
                entry[key] = raw_val
            # Skip entirely empty rows
            primary_key = col_keys[0]
            if entry.get(primary_key, "").strip():
                results.append(entry)
        return results

    # ------------------------------------------------------------------
    # TAB 4: LIVE LOGS
    # ------------------------------------------------------------------
    def _build_logs_tab(self) -> None:
        self.main_logger = LoggerTextBox(self.tab_logs)
        self.main_logger.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        bar = ttk.Frame(self.tab_logs)
        bar.pack(fill=tk.X)

        ttk.Button(bar, text="🧹 Clear Logs", command=self.clear_logs).pack(side=tk.LEFT, padx=4)
        ttk.Button(bar, text="💾 Save Logs to File", command=self.save_logs_to_file).pack(side=tk.LEFT, padx=4)

    # ------------------------------------------------------------------
    # QUEUE POLLING & LOG DISPATCH
    # ------------------------------------------------------------------
    def poll_log_queue(self) -> None:
        """Reads async events sent from background threads and updates UI elements."""
        processed = 0
        try:
            while processed < 200:
                item = self.log_queue.get_nowait()
                msg_type = item[0]

                if msg_type == "log":
                    _, level, message = item
                    self.mini_logger.append_log(message, level)
                    self.main_logger.append_log(message, level)

                elif msg_type == "status":
                    _, component, status_val = item
                    if component == "steamcmd":
                        self.steamcmd_status_var.set(status_val)
                    elif component == "server":
                        self.server_status_var.set(status_val)

                self.log_queue.task_done()
                processed += 1
        except queue.Empty:
            pass

        self.root.after(50, self.poll_log_queue)

    # ------------------------------------------------------------------
    # DETECTION & INITIALIZATION
    # ------------------------------------------------------------------
    def run_initial_detection(self) -> None:
        """Executes initial SteamCMD and 7DTD server discovery."""
        self.log_message("Scanning environment for SteamCMD & 7DTD Dedicated Server...", "INFO")

        saved_steamcmd = get_saved_path("steamcmd_path")
        saved_server = get_saved_path("server_dir")

        steam_bin = saved_steamcmd or find_steamcmd()
        if steam_bin:
            self.steamcmd_path = steam_bin
            self.steamcmd_path_var.set(str(steam_bin))
            self.steamcmd_status_var.set("Ready")
            source = "saved settings" if saved_steamcmd else "auto-detection"
            self.log_message(f"SteamCMD located via {source}: {steam_bin}", "SUCCESS")
        else:
            self.steamcmd_path_var.set("Not Found")
            self.steamcmd_status_var.set("Missing")
            self.log_message("SteamCMD executable not found.", "WARNING")

        server_dir = saved_server or find_7dtd_server(steamcmd_path=self.steamcmd_path)
        if server_dir:
            self._set_server_dir(server_dir, from_saved=bool(saved_server))
        else:
            default_target = get_app_dir() / "7dtd_server"
            self.server_dir = default_target
            self.server_path_var.set(f"Default: {default_target}")
            self.server_status_var.set("Not Installed")
            self.log_message("7DTD Server not found in standard paths.", "INFO")

        if not self.steamcmd_path:
            modal = SteamCMDMissingModal(self.root)
            self.root.wait_window(modal)
            if modal.user_choice == "download":
                self.action_download_steamcmd()
            elif modal.user_choice == "browse" and modal.selected_path:
                p = Path(modal.selected_path).resolve()
                self._set_steamcmd_path(p)

    def _set_steamcmd_path(self, path: Path) -> None:
        self.steamcmd_path = path
        self.steamcmd_path_var.set(str(path))
        self.steamcmd_status_var.set("Ready")
        save_settings(steamcmd_path=path)
        self.log_message(f"SteamCMD path set to: {path}", "INFO")

    def _set_server_dir(self, path: Path, from_saved: bool = False) -> None:
        self.server_dir = path
        self.server_path_var.set(str(path))
        self.server_status_var.set("Installed & Ready")
        save_settings(server_dir=path)
        source = "saved settings" if from_saved else "auto-detection"
        self.log_message(f"7DTD Dedicated Server located via {source}: {path}", "SUCCESS")
        self.config_manager.set_config_path(path / "serverconfig.xml")
        self.load_config_into_ui()

    def _init_admin_manager(self, server_dir: Path) -> None:
        """
        Configure serverconfig.xml folder paths, create serveradmin.xml if missing,
        and load it into the admin editor.
        """
        try:
            config_path = server_dir / "serverconfig.xml"
            self.config_manager.set_config_path(config_path)

            layout_updates = self.config_manager.ensure_server_folder_layout(server_dir, make_backup=False)
            for key, value in layout_updates.items():
                if key in self.form_vars:
                    self.form_vars[key].set(value)

            settings = self.config_manager.load_config()
            admin_path = resolve_admin_file_path(server_dir, settings)

            self.admin_manager.set_path(admin_path)
            created = not admin_path.exists()
            self.admin_manager.ensure_exists(server_dir=server_dir, settings=settings)

            if created:
                self.log_message(
                    f"serveradmin.xml did not exist — created at: {admin_path}", "INFO"
                )

            self.admin_manager.load()
            self.load_admin_into_ui()
            self.log_message(f"Loaded serveradmin.xml from: {admin_path}", "SUCCESS")

        except Exception as err:
            self.log_message(f"Could not initialize admin file: {err}", "WARNING")

    def log_message(self, message: str, level: str = "INFO") -> None:
        self.mini_logger.append_log(message, level)
        self.main_logger.append_log(message, level)

    # ------------------------------------------------------------------
    # ACTIONS & EVENT HANDLERS
    # ------------------------------------------------------------------
    def browse_steamcmd(self) -> None:
        path = filedialog.askopenfilename(
            title="Select steamcmd.exe or steamcmd.sh",
            filetypes=[("SteamCMD Executable", "steamcmd.exe;steamcmd.sh;steamcmd"), ("All Files", "*.*")],
        )
        if path:
            self._set_steamcmd_path(Path(path).resolve())

    def browse_server_dir(self) -> None:
        path = filedialog.askdirectory(title="Select 7DTD Server Directory")
        if path:
            p = Path(path).resolve()
            self.log_message(f"Updated 7DTD Server folder to: {p}", "INFO")

            config_file = p / "serverconfig.xml"
            if not config_file.exists():
                self.config_manager.generate_default_file(config_file)
                self.log_message("Created default serverconfig.xml in selected folder.", "INFO")

            self._set_server_dir(p)

    def open_steamcmd_folder(self) -> None:
        target = self.steamcmd_path.parent if self.steamcmd_path else (get_app_dir() / "steamcmd")
        if not open_folder(target):
            messagebox.showwarning("Folder Missing", f"Folder does not exist: {target}")

    def open_server_folder(self) -> None:
        target = self.server_dir if self.server_dir else (get_app_dir() / "7dtd_server")
        if not open_folder(target):
            messagebox.showwarning("Folder Missing", f"Folder does not exist: {target}")

    def action_download_steamcmd(self) -> None:
        initial_dir = self.steamcmd_path.parent if self.steamcmd_path else (get_app_dir() / "steamcmd")
        target_dir_str = filedialog.askdirectory(
            title="Select SteamCMD Installation Folder",
            initialdir=str(initial_dir),
        )
        if not target_dir_str:
            return

        target_dir = Path(target_dir_str).resolve()

        def _on_done(steam_path: Optional[Path]):
            if steam_path:
                self._set_steamcmd_path(steam_path)

        self.installer.download_and_setup_steamcmd_async(target_dir=target_dir, on_complete=_on_done)

    def _on_branch_selection_changed(self, event: Optional[tk.Event] = None) -> None:
        """Enables or disables the custom branch entry based on current dropdown selection."""
        choice = self.server_branch_choice_var.get()
        if choice == SERVER_BRANCH_CUSTOM:
            self.custom_branch_entry.config(state=tk.NORMAL)
        else:
            self.custom_branch_entry.config(state=tk.DISABLED)

    def get_selected_branch(self) -> Optional[str]:
        """Returns the normalized branch name to use for SteamCMD, or None if invalid."""
        choice = self.server_branch_choice_var.get()
        if choice == SERVER_BRANCH_CUSTOM:
            branch = self.custom_branch_var.get().strip()
            if not branch:
                messagebox.showerror(
                    "Branch Name Required",
                    "Please enter a valid custom branch name or select Stable / Latest Experimental.",
                )
                return None
            return branch
        return SERVER_BRANCH_VALUES.get(choice, "public")

    def action_install_server(self) -> None:
        if not self.steamcmd_path or not self.steamcmd_path.exists():
            messagebox.showerror(
                "SteamCMD Required",
                "SteamCMD must be downloaded or located before installing the game server.",
            )
            return

        branch = self.get_selected_branch()
        if not branch:
            return

        beta_password = self.beta_password_var.get().strip() or None
        validate = self.validate_server_files_var.get()

        target_dir: Optional[Path] = None

        _server_binary = get_executable_name("7DaysToDieServer")
        if self.server_dir and self.server_dir.exists() and (
            (self.server_dir / _server_binary).exists()
            or (self.server_dir / "startdedicated.bat").exists()
            or (self.server_dir / "startserver.bat").exists()
        ):
            use_detected = messagebox.askyesno(
                "Detected Server Location",
                f"An existing 7DTD Dedicated Server installation was found at:\n\n{self.server_dir}\n\nWould you like to use this folder?",
                icon="question",
            )
            if use_detected:
                target_dir = self.server_dir
            else:
                default_new_dir = get_app_dir() / "7dtd_server"
                target_dir_str = filedialog.askdirectory(
                    title="Select 7DTD Dedicated Server Download Folder",
                    initialdir=str(default_new_dir),
                )
                if not target_dir_str:
                    return
                target_dir = Path(target_dir_str).resolve()
        else:
            initial_dir = self.server_dir if self.server_dir else (get_app_dir() / "7dtd_server")
            target_dir_str = filedialog.askdirectory(
                title="Select 7DTD Dedicated Server Download Folder",
                initialdir=str(initial_dir),
            )
            if not target_dir_str:
                return
            target_dir = Path(target_dir_str).resolve()

        save_settings(server_branch=branch, validate_server_files=validate)

        def _on_done(success: bool):
            if success:
                self._set_server_dir(target_dir)

        self.installer.install_or_update_server_async(
            steamcmd_path=self.steamcmd_path,
            server_dir=target_dir,
            branch=branch,
            beta_password=beta_password,
            validate=validate,
            on_complete=_on_done,
        )

    def action_start_server(self) -> None:
        if not self.server_dir or not self.server_dir.exists():
            messagebox.showerror("Error", "7DTD Server directory does not exist.")
            return

        bat_file = self.server_dir / "startdedicated.bat"
        fallback_bat = self.server_dir / "startserver.bat"
        exe_file = self.server_dir / get_executable_name("7DaysToDieServer")

        if bat_file.exists():
            self.log_message(f"Launching batch script: {bat_file}", "INFO")
            if not launch_batch_in_new_window(bat_file, cwd=self.server_dir):
                messagebox.showerror("Launch Failed", f"Could not start {bat_file.name}.")
                return
            messagebox.showinfo("Server Started", "Server launched via startdedicated.bat in a new console window.")
        elif fallback_bat.exists():
            self.log_message(f"Launching batch script: {fallback_bat}", "INFO")
            if not launch_batch_in_new_window(fallback_bat, cwd=self.server_dir):
                messagebox.showerror("Launch Failed", f"Could not start {fallback_bat.name}.")
                return
            messagebox.showinfo("Server Started", "Server launched via startserver.bat in a new console window.")
        elif exe_file.exists():
            cmd = [str(exe_file), "-logfile", "7DaysToDieServer_Data/output_log.txt", "-configfile=serverconfig.xml"]
            self.log_message(f"Launching executable: {' '.join(cmd)}", "INFO")
            launch_detached_process(cmd, cwd=self.server_dir)
            messagebox.showinfo("Server Started", f"Server launched: {exe_file.name}")
        else:
            _binary_name = get_executable_name("7DaysToDieServer")
            messagebox.showerror(
                "Binary Not Found",
                f"Could not locate startdedicated.bat, startserver.bat, or {_binary_name}.",
            )

    # ------------------------------------------------------------------
    # CONFIG MANAGER INTEGRATION
    # ------------------------------------------------------------------
    def load_config_into_ui(self) -> None:
        if not self.server_dir:
            return

        config_path = self.server_dir / "serverconfig.xml"
        if not config_path.exists():
            self.log_message("serverconfig.xml not found. Creating default template...", "WARNING")
            self.config_manager.generate_default_file(config_path)

        self.config_manager.set_config_path(config_path)

        try:
            settings = self.config_manager.load_config()
            for key, var in self.form_vars.items():
                var.set(settings.get(key, ""))
            self.log_message(f"Loaded configuration settings from {config_path.name}", "SUCCESS")
            self._init_admin_manager(self.server_dir)
        except Exception as err:
            self.log_message(f"Error loading config: {err}", "ERROR")

    def save_config(self) -> None:
        if not self.server_dir:
            messagebox.showerror("Error", "No server directory selected.")
            return

        config_path = self.server_dir / "serverconfig.xml"
        self.config_manager.set_config_path(config_path)

        new_settings = {key: var.get() for key, var in self.form_vars.items()}

        try:
            self.config_manager.save_config(new_settings, make_backup=True)
            self.log_message("Saved updated serverconfig.xml with timestamped backup!", "SUCCESS")
            messagebox.showinfo("Config Saved", "serverconfig.xml successfully updated!\nA backup copy was created.")
        except Exception as err:
            self.log_message(f"Error saving config: {err}", "ERROR")
            messagebox.showerror("Save Failed", f"Could not save configuration: {err}")

    def reset_config(self) -> None:
        confirm = messagebox.askyesno(
            "Confirm Reset",
            "Are you sure you want to reset serverconfig.xml to default settings?\n\nA backup copy of your existing configuration will be saved.",
            icon="warning",
        )
        if confirm:
            try:
                self.config_manager.reset_to_defaults(make_backup=True)
                self.load_config_into_ui()
                self.log_message("Configuration reset to default settings.", "SUCCESS")
                messagebox.showinfo("Reset Complete", "Configuration successfully restored to default settings.")
            except Exception as err:
                self.log_message(f"Error resetting config: {err}", "ERROR")

    # ------------------------------------------------------------------
    # ADMIN MANAGER INTEGRATION
    # ------------------------------------------------------------------
    def load_admin_into_ui(self) -> None:
        """Populate all admin section rows from admin_manager's in-memory lists."""
        if not self.admin_manager.admin_path:
            return

        # Clear existing rows in each section
        for section_key in ("users", "whitelist", "blacklist", "commands"):
            for row_record in list(self._admin_rows[section_key]):
                row_record["frame"].destroy()
            self._admin_rows[section_key] = []

        for entry in self.admin_manager.users:
            self._add_admin_row("users", initial_values=entry)

        for entry in self.admin_manager.whitelist:
            self._add_admin_row("whitelist", initial_values=entry)

        for entry in self.admin_manager.blacklist:
            self._add_admin_row("blacklist", initial_values=entry)

        for entry in self.admin_manager.commands:
            self._add_admin_row("commands", initial_values=entry)

    def save_admin(self) -> None:
        if not self.server_dir:
            messagebox.showerror("Error", "No server directory selected.")
            return

        settings = {key: var.get() for key, var in self.form_vars.items()}
        admin_path = resolve_admin_file_path(self.server_dir, settings)
        self.admin_manager.set_path(admin_path)

        if not admin_path.exists():
            self.admin_manager.ensure_exists(server_dir=self.server_dir, settings=settings)

        try:
            self.admin_manager.users = self._collect_admin_section("users")
            self.admin_manager.whitelist = self._collect_admin_section("whitelist")
            self.admin_manager.blacklist = self._collect_admin_section("blacklist")
            self.admin_manager.commands = self._collect_admin_section("commands")

            self.admin_manager.save()
            self.log_message(f"Saved serveradmin.xml to {self.admin_manager.admin_path}", "SUCCESS")
            messagebox.showinfo("Admin Saved", "serveradmin.xml successfully updated!\nA backup was created.")
        except Exception as err:
            self.log_message(f"Error saving admin file: {err}", "ERROR")
            messagebox.showerror("Save Failed", f"Could not save serveradmin.xml: {err}")

    # ------------------------------------------------------------------
    # LOG UTILITIES
    # ------------------------------------------------------------------
    def clear_logs(self) -> None:
        self.mini_logger.clear_logs()
        self.main_logger.clear_logs()

    def save_logs_to_file(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Save Log File",
            defaultextension=".txt",
            filetypes=[("Text File", "*.txt"), ("Log File", "*.log"), ("All Files", "*.*")],
        )
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(self.main_logger.get_logs())
                messagebox.showinfo("Logs Saved", f"Logs successfully saved to {path}")
            except Exception as err:
                messagebox.showerror("Error", f"Failed to save logs: {err}")

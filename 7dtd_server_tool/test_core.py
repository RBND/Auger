"""
Automated unit verification script for core components of 7DTD Server Management Tool.
"""

import sys
import queue
import tempfile
from pathlib import Path

# Add project root to sys.path
script_dir = Path(__file__).resolve().parent
if str(script_dir) not in sys.path:
    sys.path.insert(0, str(script_dir))

from core.utils import get_app_dir, get_executable_name, set_dpi_awareness
from core.detector import find_steamcmd, find_7dtd_server
from core.installer import InstallationManager
from core.config_manager import ConfigManager, DEFAULT_CONFIG
from core.admin_manager import AdminManager, resolve_admin_file_path
from core.settings_store import load_settings, save_settings, get_saved_path


def test_utils():
    print("Testing core/utils.py...")
    app_dir = get_app_dir()
    assert app_dir.exists(), "App dir does not exist"
    
    exe_win = get_executable_name("steamcmd")
    print(f"  App directory: {app_dir}")
    print(f"  Executable name helper: {exe_win}")
    
    set_dpi_awareness()
    print("  High-DPI awareness check passed.")


def test_detector():
    print("\nTesting core/detector.py...")
    steamcmd_bin = find_steamcmd()
    print(f"  SteamCMD detection result: {steamcmd_bin}")
    
    server_dir = find_7dtd_server()
    print(f"  7DTD Server detection result: {server_dir}")


def test_installer():
    print("\nTesting core/installer.py...")
    test_queue = queue.Queue()
    installer = InstallationManager(test_queue)
    assert not installer.is_busy(), "Installer should not be busy initially"
    
    installer.log("Test log message", "INFO")
    msg_type, level, msg = test_queue.get_nowait()
    assert msg_type == "log" and level == "INFO" and msg == "Test log message"
    print("  Installer thread-safe queue dispatch verified.")


def test_config_manager():
    print("\nTesting core/config_manager.py...")
    with tempfile.TemporaryDirectory() as tmp_dir:
        config_path = Path(tmp_dir) / "serverconfig.xml"
        cm = ConfigManager()
        
        # 1. Generate default file
        success = cm.generate_default_file(config_path)
        assert success and config_path.exists(), "Failed to generate default XML file"
        print("  Default XML file generation passed.")
        
        # 2. Load config
        settings = cm.load_config()
        assert settings.get("ServerName") == DEFAULT_CONFIG["ServerName"], "Loaded ServerName mismatch"
        assert settings.get("ServerPort") == "26900", "Loaded ServerPort mismatch"
        print("  XML loading and parsing passed.")
        
        # 3. Save config with custom values
        updated_values = {
            "ServerName": "Test Production Server",
            "ServerPort": "26902",
            "ServerMaxPlayerCount": "16",
        }
        cm.save_config(updated_values, make_backup=True)
        
        # Verify backup creation
        baks = list(Path(tmp_dir).glob("*.bak"))
        assert len(baks) >= 1, "Backup file was not created"
        print(f"  Backup creation verified ({baks[0].name}).")
        
        # Reload and check values
        reloaded = cm.load_config()
        assert reloaded.get("ServerName") == "Test Production Server"
        assert reloaded.get("ServerPort") == "26902"
        assert reloaded.get("ServerMaxPlayerCount") == "16"
        print("  XML updating & saving passed.")
        
        # 4. Reset config to defaults
        cm.reset_to_defaults(make_backup=False)
        reset_settings = cm.load_config()
        assert reset_settings.get("ServerName") == DEFAULT_CONFIG["ServerName"]
        print("  XML reset to defaults passed.")

        # 5. Ensure server folder layout
        server_dir = Path(tmp_dir)
        cm.ensure_server_folder_layout(server_dir, make_backup=False)
        layout = cm.load_config()
        assert layout.get("AdminFileName") == "serveradmin.xml"
        assert layout.get("UserDataFolder") == str(server_dir.resolve())
        print("  Server folder layout configuration passed.")


def test_settings_store():
    print("\nTesting core/settings_store.py...")
    from core.settings_store import get_settings_path
    import json

    settings_path = get_settings_path()
    original = None
    if settings_path.exists():
        with open(settings_path, encoding="utf-8") as handle:
            original = json.load(handle)

    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            steam = Path(tmp_dir) / "steamcmd.exe"
            server = Path(tmp_dir) / "server"
            steam.touch()
            server.mkdir()

            save_settings(steamcmd_path=steam, server_dir=server)
            assert get_saved_path("steamcmd_path") == steam.resolve()
            assert get_saved_path("server_dir") == server.resolve()
            print("  Settings persistence passed.")
    finally:
        if original is None:
            settings_path.unlink(missing_ok=True)
        else:
            with open(settings_path, "w", encoding="utf-8") as handle:
                json.dump(original, handle, indent=2)


def test_admin_manager():
    print("\nTesting core/admin_manager.py...")
    with tempfile.TemporaryDirectory() as tmp_dir:
        server_dir = Path(tmp_dir)
        settings = {
            "AdminFileName": "serveradmin.xml",
            "UserDataFolder": str(server_dir.resolve()),
        }

        admin_path = resolve_admin_file_path(server_dir, settings)
        assert admin_path == server_dir / "serveradmin.xml", f"Unexpected path: {admin_path}"

        am = AdminManager()
        created_path = am.ensure_exists(server_dir=server_dir, settings=settings)
        assert created_path.exists(), "serveradmin.xml was not created"
        print("  Default serveradmin.xml creation passed.")

        am.load()
        assert am.users == [], "New admin file should have no users"
        assert len(am.commands) > 0, "Default command permissions should be created"

        am.users.append({
            "platform": "Steam",
            "userid": "76561198000000000",
            "name": "TestAdmin",
            "permission_level": "0",
        })
        am.save()

        am2 = AdminManager(created_path)
        am2.load()
        assert len(am2.users) == 1
        assert am2.users[0]["userid"] == "76561198000000000"
        print("  Admin save/load round-trip passed.")


if __name__ == "__main__":
    print("=========================================")
    print(" Running Core Unit Verification Suite")
    print("=========================================")
    test_utils()
    test_detector()
    test_installer()
    test_config_manager()
    test_settings_store()
    test_admin_manager()
    print("\n[SUCCESS] ALL CORE VERIFICATION TESTS PASSED SUCCESSFULLY!")

"""Tests for the Phase 1 core: schema, instance model, admin file location, AugerService."""
import os
import queue
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core import config_schema as schema
from core.admin_manager import migrate_legacy_admin_file, resolve_admin_file_path
from core.config_manager import ConfigManager
from core.instance import AUGER_CONFIG_NAME, ServerInstance
from core.utils import server_binary_name

STOCK_CONFIG = """<?xml version="1.0"?>
<ServerSettings>
	<property name="ServerName"		value="My Game Host"/>		<!-- Whatever you want the name of the server to be. -->
	<property name="ServerPort"		value="26900"/>
	<property name="AdminFileName"	value="serveradmin.xml"/>	<!-- Server admin file name. Path relative to UserDataFolder/Saves -->
	<!-- <property name="UserDataFolder"	value="absolute_path"/> -->
	<property name="SandboxCode"	value="AAAJABJACJADJARFBNC"/>
</ServerSettings>
"""


class IsolatedEnvTestCase(unittest.TestCase):
    """Redirects every per-user folder Auger touches into a temp dir."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        env = {
            "LOCALAPPDATA": str(self.tmp / "localappdata"),
            "APPDATA": str(self.tmp / "appdata"),
            "XDG_DATA_HOME": str(self.tmp / "xdg_data"),
            "XDG_CONFIG_HOME": str(self.tmp / "xdg_config"),
            "AUGER_SETTINGS_DIR": str(self.tmp / "settings"),
        }
        self._env = mock.patch.dict(os.environ, env)
        self._env.start()

    def tearDown(self):
        self._env.stop()
        self._tmp.cleanup()

    def make_server(self, name="server", stock=True) -> Path:
        server = self.tmp / name
        server.mkdir(parents=True)
        (server / server_binary_name()).write_bytes(b"")
        if stock:
            (server / "serverconfig.xml").write_text(STOCK_CONFIG, encoding="utf-8")
        return server


class SchemaTests(unittest.TestCase):
    def test_every_field_grouped_once_and_defaults_valid(self):
        schema._self_check()
        self.assertEqual(set(schema.default_values()), set(schema.FIELDS_BY_KEY))

    def test_int_validation(self):
        problems = schema.validate_values({"ServerPort": "abc", "ServerMaxPlayerCount": "0", "TelnetPort": "70000"})
        self.assertEqual(len(problems), 3)
        self.assertEqual(schema.validate_values({"ServerPort": "26900", "MaxChunkAge": "-1"}), [])

    def test_unknown_keys_and_choice_values_pass_by_default(self):
        self.assertEqual(schema.validate_values({"SomeNewGameSetting": "x", "Region": "Mars"}), [])
        self.assertTrue(schema.validate_values({"Region": "Mars"}, strict_choices=True))

    def test_choice_labels(self):
        self.assertEqual(schema.FIELDS_BY_KEY["PlayerKillingMode"].choice_label("0"), "No PvP")
        self.assertEqual(schema.FIELDS_BY_KEY["ServerVisibility"].choice_label("2"), "Public")


class InstanceTests(IsolatedEnvTestCase):
    def test_fresh_config_copies_stock_and_sets_managed_values(self):
        inst = ServerInstance(self.make_server())
        self.assertEqual(inst.ensure_config(fresh=True), "created")
        values = ConfigManager(inst.config_path).load_config_raw()
        self.assertEqual(values["ServerName"], "My Game Host")
        self.assertEqual(values["UserDataFolder"], str(inst.userdata_dir))
        self.assertTrue(inst.userdata_dir.is_dir())
        # The game's own file is untouched.
        self.assertEqual((inst.server_dir / "serverconfig.xml").read_text(encoding="utf-8"), STOCK_CONFIG)

    def test_adopted_config_keeps_userdata_unset(self):
        inst = ServerInstance(self.make_server())
        self.assertEqual(inst.ensure_config(fresh=False), "adopted")
        self.assertNotIn("UserDataFolder", ConfigManager(inst.config_path).load_config_raw())
        self.assertIsNone(inst.ensure_config(fresh=False))  # second call is a no-op

    def test_merge_adds_only_new_keys(self):
        inst = ServerInstance(self.make_server())
        inst.ensure_config(fresh=True)
        manager = ConfigManager(inst.config_path)
        manager.load_config()
        manager.save_config({"ServerName": "Mine"}, make_backup=False)

        updated = STOCK_CONFIG.replace(
            "</ServerSettings>", '\t<property name="BrandNewSetting" value="42"/>\n</ServerSettings>'
        ).replace('value="My Game Host"', 'value="Stock Name"')
        (inst.server_dir / "serverconfig.xml").write_text(updated, encoding="utf-8")

        self.assertEqual(inst.merge_new_stock_keys(), ["BrandNewSetting"])
        values = ConfigManager(inst.config_path).load_config_raw()
        self.assertEqual(values["BrandNewSetting"], "42")
        self.assertEqual(values["ServerName"], "Mine")


class AdminPathTests(IsolatedEnvTestCase):
    def test_uses_userdata_saves_folder(self):
        path = resolve_admin_file_path(Path("/srv"), {"UserDataFolder": str(self.tmp / "ud"), "AdminFileName": "serveradmin.xml"})
        self.assertEqual(path, self.tmp / "ud" / "Saves" / "serveradmin.xml")

    def test_unset_userdata_uses_game_default(self):
        path = resolve_admin_file_path(Path("/srv"), {"AdminFileName": "serveradmin.xml"})
        self.assertEqual(path.parent.name, "Saves")
        self.assertEqual(path.parent.parent.name, "7DaysToDie")
        self.assertTrue(str(path).startswith(str(self.tmp)))

    def test_migrates_legacy_file(self):
        server = self.make_server()
        (server / "serveradmin.xml").write_text("<adminTools/>", encoding="utf-8")
        settings = {"UserDataFolder": str(self.tmp / "ud")}
        moved = migrate_legacy_admin_file(server, settings)
        self.assertEqual(moved, self.tmp / "ud" / "Saves" / "serveradmin.xml")
        self.assertTrue(moved.is_file())
        self.assertIsNone(migrate_legacy_admin_file(server, settings))  # never overwrites


class ServiceTests(IsolatedEnvTestCase):
    def make_service(self):
        from core.service import AugerService
        return AugerService(queue.Queue())

    def drain(self, service):
        events = []
        service.dispatch_pending(events.append)
        return events

    def test_set_server_dir_adopts_config_and_creates_admin_file(self):
        service = self.make_service()
        server = self.make_server()
        service.set_server_dir(server)
        self.assertTrue((server / AUGER_CONFIG_NAME).is_file())
        self.assertTrue(service.admin_ready())
        self.assertTrue(service.admin_path().is_file())
        kinds = {e[1] for e in self.drain(service) if e[0] == "changed"}
        self.assertTrue({"server", "config", "admin"} <= kinds)

    def test_load_config_never_writes(self):
        service = self.make_service()
        server = self.make_server()
        service.set_server_dir(server)
        cfg = server / AUGER_CONFIG_NAME
        before = cfg.read_bytes()
        os.utime(cfg, (1_000_000_000, 1_000_000_000))
        service.load_config()
        self.assertEqual(cfg.read_bytes(), before)
        self.assertEqual(int(cfg.stat().st_mtime), 1_000_000_000)

    def test_save_config_validates_and_cleans(self):
        from core.service import ServiceError
        service = self.make_service()
        service.set_server_dir(self.make_server())
        values = service.load_config()

        bad = dict(values, ServerPort="not-a-port")
        with self.assertRaises(ServiceError):
            service.save_config(bad)

        with self.assertRaises(ServiceError):
            service.save_config(dict(values, SandboxCode="<b>nope</b>"))

        saved = service.save_config(dict(values, SandboxCode=' "ABCD EFG" ', ServerName="Friends"))
        self.assertEqual(saved["SandboxCode"], "ABCDEFG")
        raw = ConfigManager(service.config_path).load_config_raw()
        self.assertEqual(raw["ServerName"], "Friends")
        self.assertNotIn("UserDataFolder", raw)  # empty value not introduced

    def test_reset_keeps_saves_folder(self):
        service = self.make_service()
        server = self.make_server()
        service.set_server_dir(server)
        values = service.load_config()
        service.save_config(dict(values, UserDataFolder=str(self.tmp / "worlds"), ServerName="X"))
        service.reset_config()
        raw = ConfigManager(service.config_path).load_config_raw()
        self.assertEqual(raw["UserDataFolder"], str(self.tmp / "worlds"))
        self.assertEqual(raw["ServerName"], schema.FIELDS_BY_KEY["ServerName"].default)

    def test_after_fresh_install_uses_instance_userdata(self):
        service = self.make_service()
        server = self.make_server()
        service._after_install(server, fresh=True)
        raw = ConfigManager(server / AUGER_CONFIG_NAME).load_config_raw()
        self.assertEqual(raw["UserDataFolder"], str(service.instance.userdata_dir))
        self.assertEqual(service.admin_path(), service.instance.userdata_dir / "Saves" / "serveradmin.xml")

    def test_start_and_install_guards(self):
        from core.service import ServiceError
        service = self.make_service()
        service.set_server_dir(self.tmp / "empty")
        with self.assertRaises(ServiceError):
            service.start_server()
        with self.assertRaises(ServiceError):
            service.install_server_async()  # no download tool yet
        with self.assertRaises(ServiceError):
            service.save_config({"ServerName": "x"})  # nothing installed

    def test_start_uses_auger_config(self):
        service = self.make_service()
        server = self.make_server()
        service.set_server_dir(server)
        with mock.patch.object(service.process, "start", return_value=server / "log.txt") as start:
            service.start_server()
        start.assert_called_once_with(server, config_file=AUGER_CONFIG_NAME)

    def test_detection_finds_saved_server(self):
        from core.settings_store import save_settings
        server = self.make_server()
        save_settings(server_dir=server)
        service = self.make_service()
        with mock.patch("core.service.find_download_tool", return_value=None):
            service.detect_blocking()
        self.assertEqual(service.server_dir, server)
        self.assertTrue(service.config_available())


if __name__ == "__main__":
    unittest.main()

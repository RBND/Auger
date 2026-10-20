import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core.config_manager import ConfigManager, normalize_sandbox_code
from core.installer import preserve_user_files, restore_user_files
from core.server_launcher import build_server_launch, is_server_installed


class ServerLaunchTests(unittest.TestCase):
    def test_linux_launch_uses_x86_64_binary_and_library_path(self):
        with mock.patch("platform.system", return_value="Linux"):
            cmd, env, log_file = build_server_launch(Path("/srv/7dtd"), base_env={"LD_LIBRARY_PATH": "/opt/lib"})
        self.assertEqual(Path(cmd[0]).name, "7DaysToDieServer.x86_64")
        for flag in ("-quit", "-batchmode", "-nographics", "-dedicated", "-configfile=serverconfig.xml"):
            self.assertIn(flag, cmd)
        self.assertTrue(env["LD_LIBRARY_PATH"].startswith(str(Path("/srv/7dtd"))))
        self.assertTrue(env["LD_LIBRARY_PATH"].endswith("/opt/lib"))
        self.assertEqual(cmd[cmd.index("-logfile") + 1], str(log_file))
        self.assertFalse(any(part.endswith(".bat") for part in cmd))

    def test_windows_launch_uses_exe_and_no_library_path(self):
        with mock.patch("platform.system", return_value="Windows"):
            cmd, env, _ = build_server_launch(Path("C:/srv"), base_env={})
        self.assertEqual(Path(cmd[0]).name, "7DaysToDieServer.exe")
        self.assertNotIn("LD_LIBRARY_PATH", env)

    def test_is_server_installed_requires_binary(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "startdedicated.bat").write_text("echo", encoding="utf-8")
            self.assertFalse(is_server_installed(tmp_path))
            from core.utils import server_binary_name
            (tmp_path / server_binary_name()).write_bytes(b"")
            self.assertTrue(is_server_installed(tmp_path))
        self.assertFalse(is_server_installed(None))


class PreserveConfigTests(unittest.TestCase):
    def test_serverconfig_survives_an_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            server_dir = Path(tmp)
            cfg = server_dir / "serverconfig.xml"
            cfg.write_text("<ServerSettings>USER</ServerSettings>", encoding="utf-8")

            preserved = preserve_user_files(server_dir)
            cfg.write_text("<ServerSettings>STOCK</ServerSettings>", encoding="utf-8")  # simulated update
            restore_user_files(preserved)

            self.assertIn("USER", cfg.read_text(encoding="utf-8"))
            self.assertFalse((server_dir / "serverconfig.xml.auger-preserve").exists())

    def test_nothing_to_preserve_on_first_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(preserve_user_files(Path(tmp)), {})


class ConfigManagerTests(unittest.TestCase):
    def test_raw_load_returns_only_file_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "c.xml"
            cfg.write_text('<ServerSettings><property name="ServerName" value="X"/></ServerSettings>', encoding="utf-8")
            manager = ConfigManager(cfg)
            self.assertEqual(manager.load_config_raw(), {"ServerName": "X"})
            self.assertIn("ServerPort", manager.load_config())  # defaults filled in

    def test_switching_files_never_writes_old_contents(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "a.xml", Path(tmp) / "b.xml"
            a.write_text('<ServerSettings><property name="ServerName" value="A"/></ServerSettings>', encoding="utf-8")
            b.write_text('<ServerSettings><property name="ServerName" value="B"/><property name="Extra" value="1"/></ServerSettings>', encoding="utf-8")
            manager = ConfigManager(a)
            manager.load_config()
            manager.set_config_path(b)
            manager.save_config({"ServerName": "B2"}, make_backup=False)
            self.assertEqual(ConfigManager(b).load_config_raw(), {"ServerName": "B2", "Extra": "1"})

    def test_partial_save_without_load_keeps_other_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "c.xml"
            cfg.write_text('<ServerSettings><property name="A" value="1"/><property name="B" value="2"/></ServerSettings>', encoding="utf-8")
            ConfigManager(cfg).save_config({"B": "3"}, make_backup=False)
            self.assertEqual(ConfigManager(cfg).load_config_raw(), {"A": "1", "B": "3"})

    def test_backup_named_after_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "serverconfig.auger.xml"
            ConfigManager().generate_default_file(cfg)
            manager = ConfigManager(cfg)
            manager.load_config()
            manager.save_config({"ServerName": "Y"}, make_backup=True)
            self.assertTrue((Path(tmp) / "serverconfig.auger.xml.bak").exists())
            self.assertTrue(list(Path(tmp).glob("serverconfig.auger_*.xml.bak")))

    def test_round_trip_keeps_comments_and_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "serverconfig.xml"
            manager = ConfigManager()
            manager.generate_default_file(cfg)
            manager.load_config()
            manager.save_config({"ServerName": "Friends & Family", "SandboxCode": "ABCDEF"}, make_backup=False)

            reloaded = ConfigManager(cfg).load_config()
            self.assertEqual(reloaded["ServerName"], "Friends & Family")
            self.assertEqual(reloaded["SandboxCode"], "ABCDEF")
            self.assertIn("<!-- Server Representation -->", cfg.read_text(encoding="utf-8"))


class SandboxCodeTests(unittest.TestCase):
    def test_plain_code(self):
        self.assertEqual(normalize_sandbox_code("AAAJABJACJADJARFBNC"), "AAAJABJACJADJARFBNC")

    def test_whitespace_and_quotes_removed(self):
        self.assertEqual(normalize_sandbox_code('  "AAAJ ABJ\nACJ"  '), "AAAJABJACJ")

    def test_whole_xml_line_pasted(self):
        line = '<property name="SandboxCode" value="AAAJABJACJADJARFBNC" />'
        self.assertEqual(normalize_sandbox_code(line), "AAAJABJACJADJARFBNC")

    def test_rejects_non_code_text(self):
        self.assertEqual(normalize_sandbox_code("Hello there, <b>friend</b>!"), "")
        self.assertEqual(normalize_sandbox_code(""), "")


if __name__ == "__main__":
    unittest.main()

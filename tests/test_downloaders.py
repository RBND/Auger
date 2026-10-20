import unittest
from pathlib import Path
from unittest import mock

from core import downloaders as d


class SteamCmdCommandTests(unittest.TestCase):
    def setUp(self):
        self.exe = Path("C:/tools/steamcmd/steamcmd.exe")
        self.dir = Path("C:/Games/7 Days To Die Dedicated Server")

    def test_force_install_dir_comes_before_login(self):
        cmd = d.build_steamcmd_command(self.exe, self.dir)
        self.assertLess(cmd.index("+force_install_dir"), cmd.index("+login"))
        self.assertEqual(cmd[cmd.index("+force_install_dir") + 1], str(self.dir))

    def test_every_token_is_a_separate_argument(self):
        cmd = d.build_steamcmd_command(self.exe, self.dir, branch="latest_experimental", validate=True)
        i = cmd.index("+app_update")
        self.assertEqual(cmd[i + 1 : i + 5], ["294420", "-beta", "latest_experimental", "validate"])
        self.assertEqual(cmd[-1], "+quit")
        # No element (other than the path) may contain a space-joined command.
        for token in cmd[3:]:
            if token != str(self.dir):
                self.assertNotIn(" ", token)

    def test_validate_is_off_by_default(self):
        self.assertNotIn("validate", d.build_steamcmd_command(self.exe, self.dir))

    def test_beta_password_is_its_own_token(self):
        cmd = d.build_steamcmd_command(self.exe, self.dir, branch="private", beta_password="s3cr et")
        i = cmd.index("-betapassword")
        self.assertEqual(cmd[i + 1], "s3cr et")

    def test_rejects_bad_branch_and_password(self):
        with self.assertRaises(ValueError):
            d.build_steamcmd_command(self.exe, self.dir, branch="public; rm -rf /")
        with self.assertRaises(ValueError):
            d.build_steamcmd_command(self.exe, self.dir, beta_password="bad\npass")


class DepotDownloaderCommandTests(unittest.TestCase):
    def test_linux_command(self):
        cmd = d.build_depotdownloader_command(
            Path("/home/u/.local/share/auger/depotdownloader/DepotDownloader"),
            Path("/srv/7dtd"),
            branch="public",
            validate=True,
            target_os="linux",
        )
        self.assertEqual(cmd[1:3], ["-app", "294420"])
        self.assertEqual(cmd[cmd.index("-os") + 1], "linux")
        self.assertEqual(cmd[cmd.index("-osarch") + 1], "64")
        self.assertEqual(cmd[cmd.index("-dir") + 1], str(Path("/srv/7dtd")))
        self.assertEqual(cmd[cmd.index("-branch") + 1], "public")
        self.assertIn("-validate", cmd)
        self.assertNotIn("-branchpassword", cmd)

    def test_branch_password_requires_branch_and_is_passed(self):
        cmd = d.build_depotdownloader_command(
            Path("DepotDownloader"), Path("/srv"), branch="beta", beta_password="pw", target_os="linux"
        )
        self.assertIn("-branch", cmd)
        self.assertEqual(cmd[cmd.index("-branchpassword") + 1], "pw")


class PlatformToolSelectionTests(unittest.TestCase):
    def test_windows_uses_steamcmd(self):
        with mock.patch("platform.system", return_value="Windows"):
            self.assertEqual(d.default_tool_for_platform(), d.TOOL_STEAMCMD)
            self.assertEqual(d.tool_binary_name(d.TOOL_STEAMCMD), "steamcmd.exe")

    def test_linux_uses_depotdownloader(self):
        with mock.patch("platform.system", return_value="Linux"):
            self.assertEqual(d.default_tool_for_platform(), d.TOOL_DEPOTDOWNLOADER)
            self.assertEqual(d.tool_binary_name(d.TOOL_DEPOTDOWNLOADER), "DepotDownloader")
            self.assertEqual(d.tool_binary_name(d.TOOL_STEAMCMD), "steamcmd.sh")
            self.assertTrue(d.tool_download_url(d.TOOL_DEPOTDOWNLOADER).endswith("linux-x64.zip"))

    def test_depotdownloader_env_avoids_icu_dependency(self):
        env = d.tool_environment(d.TOOL_DEPOTDOWNLOADER, {})
        self.assertEqual(env["DOTNET_SYSTEM_GLOBALIZATION_INVARIANT"], "1")
        self.assertEqual(d.tool_environment(d.TOOL_STEAMCMD, {}), {})


class OutputTrackerTests(unittest.TestCase):
    def test_steamcmd_success_even_with_nonzero_exit(self):
        t = d.InstallOutputTracker(d.TOOL_STEAMCMD)
        self.assertEqual(t.feed(" Update state (0x61) downloading, progress: 42.50 (1 / 2)"), "PROGRESS")
        self.assertAlmostEqual(t.last_percent, 42.5)
        self.assertEqual(t.feed("Success! App '294420' fully installed."), "SUCCESS")
        self.assertTrue(t.succeeded(7))

    def test_steamcmd_error_means_failure_even_with_zero_exit(self):
        t = d.InstallOutputTracker(d.TOOL_STEAMCMD)
        self.assertEqual(t.feed("ERROR! Failed to install app '294420' (Disk write failure)"), "ERROR")
        self.assertFalse(t.succeeded(0))

    def test_steamcmd_without_success_line_is_failure(self):
        t = d.InstallOutputTracker(d.TOOL_STEAMCMD)
        t.feed("Loading Steam API...OK")
        self.assertFalse(t.succeeded(0))

    def test_depotdownloader_success(self):
        t = d.InstallOutputTracker(d.TOOL_DEPOTDOWNLOADER)
        self.assertEqual(t.feed(" 12.34% Data/Config/items.xml"), "PROGRESS")
        self.assertAlmostEqual(t.last_percent, 12.34)
        t.feed("Depot 294422 - Downloaded 100 bytes (200 bytes uncompressed)")
        self.assertEqual(t.feed("Total downloaded: 100 bytes (200 bytes uncompressed) from 1 depots"), "SUCCESS")
        self.assertTrue(t.succeeded(0))
        self.assertFalse(t.succeeded(1))

    def test_depotdownloader_abort_is_failure(self):
        t = d.InstallOutputTracker(d.TOOL_DEPOTDOWNLOADER)
        self.assertEqual(t.feed("Encountered error downloading chunk abc: 503"), "WARNING")
        self.assertEqual(t.feed("Encountered 404 for depot manifest 294422 123. Aborting."), "ERROR")
        t.feed("Total downloaded: 0 bytes (0 bytes uncompressed) from 0 depots")
        self.assertFalse(t.succeeded(0))


if __name__ == "__main__":
    unittest.main()

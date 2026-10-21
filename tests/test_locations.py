import os
import subprocess
import sys
import tempfile
import unittest

DAEMON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "daemon")

sys.path.insert(0, DAEMON)

from locations import config_dir, data_dir, state_dir

HOME = os.path.expanduser("~")


class LinuxLocationsTest(unittest.TestCase):
    def test_xdg_variables_win_over_the_home_defaults(self):
        environ = {"XDG_CONFIG_HOME": "/cfg", "XDG_DATA_HOME": "/data", "XDG_STATE_HOME": "/state"}
        self.assertEqual(config_dir(environ, "linux"), os.path.join("/cfg", "stray-ps5-haptics"))
        self.assertEqual(data_dir(environ, "linux"), os.path.join("/data", "stray-ps5-haptics"))
        self.assertEqual(state_dir(environ, "linux"), os.path.join("/state", "stray-ps5-haptics"))

    def test_unset_or_empty_xdg_variables_fall_back_like_the_shell_does(self):
        environ = {"XDG_DATA_HOME": ""}
        self.assertEqual(config_dir(environ, "linux"), os.path.join(HOME, ".config", "stray-ps5-haptics"))
        self.assertEqual(data_dir(environ, "linux"), os.path.join(HOME, ".local", "share", "stray-ps5-haptics"))
        self.assertEqual(state_dir(environ, "linux"), os.path.join(HOME, ".local", "state", "stray-ps5-haptics"))


class WindowsLocationsTest(unittest.TestCase):
    def test_settings_roam_and_sounds_and_logs_stay_local(self):
        environ = {"APPDATA": "C:/Users/cat/AppData/Roaming", "LOCALAPPDATA": "C:/Users/cat/AppData/Local",
                   "XDG_DATA_HOME": "/ignored"}
        self.assertEqual(config_dir(environ, "win32"), os.path.join(environ["APPDATA"], "stray-ps5-haptics"))
        self.assertEqual(data_dir(environ, "win32"), os.path.join(environ["LOCALAPPDATA"], "stray-ps5-haptics"))
        self.assertEqual(state_dir(environ, "win32"), os.path.join(environ["LOCALAPPDATA"], "stray-ps5-haptics"))


class DaemonDefaultsTest(unittest.TestCase):
    def test_the_daemon_looks_for_the_sounds_where_the_installer_puts_them(self):
        with tempfile.TemporaryDirectory() as directory:
            environ = dict(os.environ, XDG_DATA_HOME=directory, LOCALAPPDATA=directory, APPDATA=directory)
            finished = subprocess.run([sys.executable, "-I", os.path.join(DAEMON, "stray_haptics.py"), "events.log"],
                                      env=environ, capture_output=True, text=True, timeout=30)
        self.assertNotEqual(finished.returncode, 0)
        self.assertIn(repr(os.path.join(directory, "stray-ps5-haptics", "manifest.json")), finished.stderr)


if __name__ == "__main__":
    unittest.main()

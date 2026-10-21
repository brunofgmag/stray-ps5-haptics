import json
import os
import stat
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "daemon"))

import install
from locations import config_dir, data_dir, state_dir

EVENTS = ("Hk_project", "Binaries", "Win64", "ue4ss", "Mods", "StrayHaptics", "events.log")


def prepare(environ, platform, game_dir):
    os.makedirs(config_dir(environ, platform))
    with open(os.path.join(config_dir(environ, platform), "game_dir"), "w") as handle:
        handle.write(game_dir + "\n")
    os.makedirs(data_dir(environ, platform), exist_ok=True)
    with open(os.path.join(data_dir(environ, platform), "manifest.json"), "w") as handle:
        json.dump({"sounds": {}, "cues": {}}, handle)
    os.makedirs(os.path.dirname(os.path.join(game_dir, *EVENTS)))
    return os.path.join(state_dir(environ, platform), "daemon.log")


def game_that_scratches(daemon_log, events, status):
    script = (f"import sys, time\n"
              f"deadline = time.time() + 60\n"
              f"while time.time() < deadline and 'following' not in open({daemon_log!r}).read():\n"
              f"    time.sleep(0.2)\n"
              f"with open({events!r}, 'a') as handle:\n"
              f"    handle.write('TRIGGERS\\t1\\t1\\n')\n"
              f"time.sleep(1)\n"
              f"sys.exit({status})\n")
    return [sys.executable, "-c", script]


def wait_for(path, text, seconds=30):
    deadline = time.time() + seconds
    while time.time() < deadline:
        with open(path) as handle:
            content = handle.read()
        if text in content:
            return content
        time.sleep(0.2)
    return content


@unittest.skipUnless(sys.platform.startswith("linux"), "the shell wrapper runs on Linux")
class LinuxLaunchTest(unittest.TestCase):
    def test_the_wrapper_follows_the_game_events_and_returns_the_game_status(self):
        with tempfile.TemporaryDirectory() as directory:
            stubs = os.path.join(directory, "stubs")
            os.makedirs(stubs)
            pactl = os.path.join(stubs, "pactl")
            with open(pactl, "w") as handle:
                handle.write("#!/bin/sh\nexit 0\n")
            os.chmod(pactl, stat.S_IRWXU)
            environ = dict(os.environ, PATH=stubs + os.pathsep + os.environ["PATH"],
                           XDG_CONFIG_HOME=os.path.join(directory, "config"),
                           XDG_DATA_HOME=os.path.join(directory, "data"),
                           XDG_STATE_HOME=os.path.join(directory, "state"))
            game_dir = os.path.join(directory, "Stray")
            daemon_log = prepare(environ, "linux", game_dir)
            game = [sys.executable, "-c", "import sys, time; time.sleep(2); sys.exit(3)"]
            finished = subprocess.run([os.path.join(ROOT, "bin", "stray-haptics-run"), *game], env=environ, timeout=60)
            self.assertEqual(finished.returncode, 3)
            with open(daemon_log) as handle:
                self.assertIn(f"following {os.path.join(game_dir, *EVENTS)}", handle.read())


@unittest.skipUnless(sys.platform == "win32", "the pythonw wrapper runs on Windows")
class WindowsLaunchTest(unittest.TestCase):
    def windows_environ(self, directory):
        return dict(os.environ, APPDATA=os.path.join(directory, "Roaming"), LOCALAPPDATA=os.path.join(directory, "Local"))

    def test_the_wrapper_runs_the_daemon_from_the_installed_environment_until_the_game_ends(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            environ = self.windows_environ(directory)
            game_dir = os.path.join(directory, "Stray")
            daemon_log = prepare(environ, "win32", game_dir)
            pythonw = install.install_daemon_environment(data_dir(environ, "win32"))
            game = game_that_scratches(daemon_log, os.path.join(game_dir, *EVENTS), 3)
            wrapper = os.path.join(ROOT, "bin", "stray-haptics-run.pyw")
            finished = subprocess.run([pythonw, wrapper, *game], env=environ, timeout=180)
            self.assertEqual(finished.returncode, 3)
            log = wait_for(daemon_log, "triggers right none")
            self.assertIn(f"following {os.path.join(game_dir, *EVENTS)}", log)
            self.assertIn("triggers right scratchable", log)
            self.assertIn("game process ended", log)
            self.assertIn("triggers right none", log)

    def test_the_game_still_starts_when_the_daemon_cannot(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            environ = self.windows_environ(directory)
            wrapper = os.path.join(ROOT, "bin", "stray-haptics-run.pyw")
            game = [sys.executable, "-c", "import sys; sys.exit(4)"]
            finished = subprocess.run([sys.executable, wrapper, *game], env=environ, timeout=60)
            self.assertEqual(finished.returncode, 4)
            with open(os.path.join(state_dir(environ, "win32"), "daemon.log")) as handle:
                self.assertIn("game_dir", handle.read())


if __name__ == "__main__":
    unittest.main()

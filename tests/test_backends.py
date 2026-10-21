import argparse
import os
import queue
import subprocess
import sys
import threading
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "daemon"))

import stray_haptics
from stray_haptics import Mixer, Triggers, load_backend, play


class FakeSounds:
    def get(self, name):
        info = {"group": "speaker", "looping": True, "volume": 1.0}
        return info, np.full((480, 2), 0.25, np.float32)


class FakeOutput:
    name = "fake output"

    def __init__(self):
        self.blocks = []
        self.closed = False

    def alive(self):
        return not self.closed

    def write(self, block):
        self.blocks.append(block.copy())
        return True

    def close(self):
        self.closed = True


class FakeBackend:
    def __init__(self, polls_while_alive):
        self.output = FakeOutput()
        self.reports = []
        self.polls_left = polls_while_alive
        self.watched = None
        self.pattern = None

    def open_output(self, pattern):
        self.pattern = pattern
        return self.output

    def write_trigger_report(self, report):
        self.reports.append(report)
        return True

    def watch_process(self, pid):
        self.watched = pid

        def alive():
            self.polls_left -= 1
            return self.polls_left >= 0

        return alive


def sleeper():
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])


class BackendSelectionTest(unittest.TestCase):
    def test_the_running_platform_gets_its_own_backend(self):
        backend = load_backend()
        self.assertEqual(type(backend).__module__, stray_haptics.BACKENDS[sys.platform])

    def test_an_unsupported_platform_stops_with_its_name(self):
        with self.assertRaises(SystemExit) as stopped:
            load_backend("darwin")
        self.assertIn("darwin", str(stopped.exception))


class PlayTest(unittest.TestCase):
    def test_plays_through_the_backend_until_the_watched_process_ends(self):
        backend = FakeBackend(polls_while_alive=5)
        events = queue.Queue()
        events.put(["START", "a", "meow", "0", "1"])
        events.put(["TRIGGERS", "1", "1"])
        args = argparse.Namespace(events="events.log", sink="pattern", exit_with_pid=4321)
        mixer, triggers = Mixer(FakeSounds(), 1.0, 1.0), Triggers(backend.write_trigger_report)
        player = threading.Thread(target=play, args=(args, mixer, triggers, events, backend), daemon=True)
        player.start()
        player.join(timeout=5)
        self.assertFalse(player.is_alive())
        self.assertEqual(backend.watched, 4321)
        self.assertEqual(backend.pattern, "pattern")
        self.assertEqual(len(backend.output.blocks), 5)
        self.assertAlmostEqual(float(backend.output.blocks[-1][:, 0].max()), 0.25, places=3)
        self.assertEqual(backend.reports[0][1], 0x04)
        self.assertTrue(backend.output.closed)


@unittest.skipUnless(sys.platform.startswith("linux"), "/proc is Linux only")
class LinuxProcessWatchTest(unittest.TestCase):
    def test_a_process_counts_as_alive_until_it_ends(self):
        process = sleeper()
        alive = load_backend("linux").watch_process(process.pid)
        self.assertTrue(alive())
        process.kill()
        process.wait()
        self.assertFalse(alive())


if __name__ == "__main__":
    unittest.main()

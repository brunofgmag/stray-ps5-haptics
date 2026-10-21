import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "daemon"))

from stray_haptics import Mixer, soft_limit


class FakeSounds:
    def __init__(self):
        frames = 4800
        self.sounds = {
            "meow": ({"group": "speaker", "looping": False, "volume": 1.0}, np.full((frames, 2), 0.25, np.float32)),
            "loud": ({"group": "speaker", "looping": False, "volume": 1.0}, np.full((frames, 2), 0.66, np.float32)),
            "rain": ({"group": "haptic", "looping": True, "volume": 1.0}, np.full((frames, 2), 0.5, np.float32)),
        }

    def get(self, name):
        return self.sounds.get(name, (None, None))


def render(mixer, blocks):
    return np.vstack([mixer.render(240) for _ in range(blocks)])


class MixerTest(unittest.TestCase):
    def test_speaker_gain_reaches_only_speaker_channels(self):
        mixer = Mixer(FakeSounds(), haptic_gain=1.0, speaker_gain=3.0)
        mixer.handle(["START", "a", "meow", "0", "1"])
        out = render(mixer, 4)
        self.assertAlmostEqual(float(out[:, 0].max()), 0.75, places=3)
        self.assertEqual(float(np.abs(out[:, 2:]).max()), 0.0)

    def test_limiter_keeps_loud_speaker_sounds_inside_full_scale(self):
        mixer = Mixer(FakeSounds(), haptic_gain=1.0, speaker_gain=4.0)
        mixer.handle(["START", "a", "loud", "0", "1"])
        out = render(mixer, 4)
        self.assertLessEqual(float(np.abs(out).max()), 1.0)
        self.assertGreater(float(out[:, 0].max()), 0.9)

    def test_limiter_leaves_quiet_samples_untouched(self):
        samples = np.array([[0.1, -0.5, 0.79, -0.2]], np.float32)
        np.testing.assert_array_equal(soft_limit(samples.copy()), samples)

    def test_level_stop_and_one_shot_lifecycle(self):
        mixer = Mixer(FakeSounds(), haptic_gain=1.0, speaker_gain=1.0)
        mixer.handle(["START", "rain", "rain", "0", "0"])
        self.assertEqual(float(np.abs(render(mixer, 2)).max()), 0.0)
        mixer.handle(["LEVEL", "rain", "1"])
        self.assertAlmostEqual(float(render(mixer, 2)[-1, 2]), 0.5, places=3)
        mixer.handle(["STOP", "rain", "0.05"])
        render(mixer, 20)
        self.assertNotIn("rain", mixer.voices)
        mixer.handle(["START", "m", "meow", "0", "1"])
        render(mixer, 30)
        self.assertNotIn("m", mixer.voices)


class FollowTest(unittest.TestCase):
    def test_ignores_events_left_by_a_previous_session(self):
        import queue
        import tempfile
        import threading
        import time

        from stray_haptics import follow

        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "events.log")
            with open(path, "w") as handle:
                handle.write("START\told\tmeow\t0\t1\n")
            events = queue.Queue()
            threading.Thread(target=follow, args=(path, events), daemon=True).start()
            time.sleep(0.1)
            with open(path, "a") as handle:
                handle.write("START\tnew\tmeow\t0\t1\n")
            self.assertEqual(events.get(timeout=1)[1], "new")

    def test_follows_a_log_the_game_truncates_and_keeps_open_in_text_mode(self):
        import queue
        import tempfile
        import threading
        import time

        from stray_haptics import follow

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            path = os.path.join(directory, "events.log")
            with open(path, "w") as handle:
                handle.write("START\told\tmeow\t0\t1\n" * 10)
            events = queue.Queue()
            threading.Thread(target=follow, args=(path, events), daemon=True).start()
            time.sleep(0.1)
            with open(path, "w") as game:
                game.write("START\tnew\tmeow\t0\t1\n")
                game.flush()
                self.assertEqual(events.get(timeout=1), ["RESET"])
                self.assertEqual(events.get(timeout=1), ["START", "new", "meow", "0", "1"])


@unittest.skipUnless(sys.platform.startswith("linux"), "the pipe to pw-cat is Linux only")
class OutputTest(unittest.TestCase):
    def test_output_opens_when_the_kernel_refuses_to_resize_the_pipe(self):
        import fcntl
        from unittest import mock

        import backend_linux

        real_fcntl = fcntl.fcntl

        def refuse_resize(fd, command, *args):
            if command == fcntl.F_SETPIPE_SZ:
                raise PermissionError(1, "Operation not permitted")
            return real_fcntl(fd, command, *args)

        reader, writer = os.pipe()
        self.addCleanup(os.close, reader)
        process = mock.Mock()
        process.stdin = os.fdopen(writer, "wb", buffering=0)
        self.addCleanup(process.stdin.close)
        logged = []
        with mock.patch.object(backend_linux.subprocess, "Popen", return_value=process), \
                mock.patch.object(backend_linux.fcntl, "fcntl", side_effect=refuse_resize):
            output = backend_linux.PipeWireOutput("sink", 48000, logged.append)
        self.assertIs(output.process, process)
        self.assertIn("pipe kept at", logged[0])


if __name__ == "__main__":
    unittest.main()

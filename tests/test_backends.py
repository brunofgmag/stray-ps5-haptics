import argparse
import os
import queue
import subprocess
import sys
import threading
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "daemon"))

import backend_windows
import stray_haptics
from stray_haptics import Mixer, Triggers, load_backend, play, trigger_report

DUALSENSE_PATH = b"\\\\?\\HID#VID_054C&PID_0CE6&MI_03#8&1a2b3c4d&0&0000#{4d1e55b2-f16f-11cf-88cb-001111000030}"
WASAPI_HOSTAPIS = ({"name": "MME"}, {"name": "Windows DirectSound"}, {"name": "Windows WASAPI"})


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


class FakeHidDevice:
    def __init__(self, hid):
        self.hid = hid
        self.path = None
        self.closed = False

    def open_path(self, path):
        if self.hid.open_error:
            raise OSError("open failed")
        self.path = path

    def write(self, report):
        self.hid.written.append((self.path, bytes(report)))
        return self.hid.write_result

    def error(self):
        return "the device stopped answering"

    def close(self):
        self.closed = True


class FakeHid:
    def __init__(self, devices, open_error=False, write_result=48):
        self.devices = devices
        self.open_error = open_error
        self.write_result = write_result
        self.asked_vendor = None
        self.written = []
        self.handles = []

    def enumerate(self, vendor_id=0, product_id=0):
        self.asked_vendor = vendor_id
        return list(self.devices)

    def device(self):
        handle = FakeHidDevice(self)
        self.handles.append(handle)
        return handle


class FakePortAudioError(Exception):
    pass


class FakeStream:
    def __init__(self, sounddevice, settings):
        self.sounddevice = sounddevice
        self.settings = settings
        self.started = False
        self.closed = False

    def start(self):
        self.started = True

    def write(self, block):
        if self.sounddevice.write_error:
            raise FakePortAudioError("Unanticipated host error")

    def close(self):
        self.closed = True


class FakeSoundDevice:
    PortAudioError = FakePortAudioError

    def __init__(self, devices, open_error=None):
        self.devices = devices
        self.open_error = open_error
        self.write_error = False
        self.calls = []
        self.stream = None

    def _terminate(self):
        self.calls.append("terminate")

    def _initialize(self):
        self.calls.append("initialize")

    def query_devices(self):
        self.calls.append("query")
        return self.devices

    def query_hostapis(self):
        return WASAPI_HOSTAPIS

    def WasapiSettings(self, **settings):
        return ("wasapi", settings)

    def OutputStream(self, **settings):
        if self.open_error:
            raise FakePortAudioError(self.open_error)
        self.stream = FakeStream(self, settings)
        return self.stream


def audio_device(name, hostapi, channels):
    return {"name": name, "hostapi": hostapi, "max_output_channels": channels}


CONTROLLER_DEVICES = [
    audio_device("Speakers (Realtek(R) Audio)", 2, 2),
    audio_device("Speakers (DualSense Wireless Co", 0, 4),
    audio_device("Speakers (DualSense Wireless Controller)", 1, 4),
    audio_device("Speakers (DualSense Wireless Controller)", 2, 4),
]


def windows_backend(**modules):
    logged = []
    return backend_windows.Backend(logged.append, 48000, **modules), logged


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


class WindowsOutputDeviceTest(unittest.TestCase):
    def test_picks_the_four_channel_wasapi_endpoint_of_the_controller(self):
        found = backend_windows.find_output_device(CONTROLLER_DEVICES, WASAPI_HOSTAPIS, "DualSense Wireless Controller")
        self.assertEqual(found, (3, "Speakers (DualSense Wireless Controller)"))

    def test_a_stereo_or_unrelated_endpoint_is_not_the_controller(self):
        devices = [audio_device("Speakers (DualSense Wireless Controller)", 2, 2),
                   audio_device("Speakers (Realtek(R) Audio)", 2, 8)]
        self.assertIsNone(backend_windows.find_output_device(devices, WASAPI_HOSTAPIS, "DualSense Wireless Controller"))


class WindowsTriggerWriteTest(unittest.TestCase):
    def test_writes_the_report_to_the_first_sony_hid_device(self):
        hid = FakeHid([{"path": DUALSENSE_PATH}, {"path": b"second"}])
        backend, logged = windows_backend(hid=hid)
        report = trigger_report(1, bytes([0x01, 0x00, 0xA0]))
        self.assertTrue(backend.write_trigger_report(report))
        self.assertEqual(hid.asked_vendor, 0x054C)
        self.assertEqual(hid.written, [(DUALSENSE_PATH, report)])
        self.assertTrue(hid.handles[0].closed)
        self.assertEqual(logged, [])

    def test_a_missing_controller_is_reported_not_raised(self):
        backend, logged = windows_backend(hid=FakeHid([]))
        self.assertFalse(backend.write_trigger_report(b"\x02"))
        self.assertEqual(logged, ["triggers: no DualSense among the HID devices"])

    def test_a_refused_open_or_write_is_reported_and_the_device_closed(self):
        for hid, reason in ((FakeHid([{"path": DUALSENSE_PATH}], open_error=True), "open failed"),
                            (FakeHid([{"path": DUALSENSE_PATH}], write_result=-1), "the device stopped answering")):
            backend, logged = windows_backend(hid=hid)
            self.assertFalse(backend.write_trigger_report(b"\x02"))
            self.assertTrue(logged[0].startswith("triggers: could not write \\\\?\\HID#VID_054C"))
            self.assertTrue(logged[0].endswith(reason))
            self.assertTrue(hid.handles[0].closed)


class WindowsAudioOutputTest(unittest.TestCase):
    def test_opens_a_four_channel_float_stream_on_the_controller(self):
        sounddevice = FakeSoundDevice(CONTROLLER_DEVICES)
        backend, _ = windows_backend(sounddevice=sounddevice)
        output = backend.open_output("DualSense Wireless Controller")
        self.assertEqual(output.name, "Speakers (DualSense Wireless Controller)")
        settings = sounddevice.stream.settings
        self.assertEqual((settings["device"], settings["channels"], settings["samplerate"], settings["dtype"]),
                         (3, 4, 48000, "float32"))
        self.assertEqual(settings["extra_settings"], ("wasapi", {"auto_convert": True}))
        self.assertTrue(sounddevice.stream.started)

    def test_rescans_the_devices_and_finds_nothing_without_the_controller(self):
        sounddevice = FakeSoundDevice(CONTROLLER_DEVICES[:1])
        backend, _ = windows_backend(sounddevice=sounddevice)
        self.assertIsNone(backend.open_output("DualSense Wireless Controller"))
        self.assertEqual(sounddevice.calls, ["terminate", "initialize", "query"])

    def test_a_write_error_ends_the_output_so_the_daemon_reopens_it(self):
        sounddevice = FakeSoundDevice(CONTROLLER_DEVICES)
        backend, _ = windows_backend(sounddevice=sounddevice)
        output = backend.open_output("DualSense Wireless Controller")
        block = np.zeros((240, 4), np.float32)
        self.assertTrue(output.write(block))
        sounddevice.write_error = True
        self.assertFalse(output.write(block))
        self.assertFalse(output.alive())
        output.close()
        self.assertTrue(sounddevice.stream.closed)

    def test_a_stream_that_will_not_open_is_logged_once(self):
        sounddevice = FakeSoundDevice(CONTROLLER_DEVICES, open_error="Invalid number of channels")
        backend, logged = windows_backend(sounddevice=sounddevice)
        for _ in range(3):
            self.assertIsNone(backend.open_output("DualSense Wireless Controller"))
        self.assertEqual(logged, ["output could not open on Speakers (DualSense Wireless Controller): "
                                  "Invalid number of channels"])


@unittest.skipUnless(sys.platform == "win32", "needs Windows")
class WindowsSystemTest(unittest.TestCase):
    def test_a_process_counts_as_alive_until_it_ends(self):
        process = sleeper()
        alive = load_backend().watch_process(process.pid)
        self.assertTrue(alive())
        process.kill()
        process.wait()
        self.assertFalse(alive())

    def test_a_process_that_cannot_be_opened_counts_as_ended(self):
        self.assertFalse(load_backend().watch_process(0)())

    def test_the_real_hid_and_audio_libraries_load_and_report_no_controller(self):
        logged = []
        backend = backend_windows.Backend(logged.append, 48000)
        self.assertFalse(backend.write_trigger_report(trigger_report(0, bytes([0x05]))))
        self.assertIsNone(backend.open_output(backend.default_sink))
        self.assertEqual(logged, ["triggers: no DualSense among the HID devices"])


if __name__ == "__main__":
    unittest.main()

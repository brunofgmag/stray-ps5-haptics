import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "daemon"))

from stray_haptics import Triggers, write_to_dualsense

SCRATCHABLE = "1"
NONE = "0"
LEFT = "0"
RIGHT = "1"


def triggers_with_log():
    written = []
    return Triggers(write=written.append), written


class TriggersTest(unittest.TestCase):
    def test_scratchable_right_trigger_gets_continuous_resistance(self):
        triggers, written = triggers_with_log()
        triggers.handle(["TRIGGERS", SCRATCHABLE, RIGHT])
        self.assertEqual(len(written), 1)
        report = written[0]
        self.assertEqual(len(report), 48)
        self.assertEqual(report[0], 0x02)
        self.assertEqual(report[1], 0x04)
        self.assertEqual(report[11:14], bytes([0x01, 0x00, 0xA0]))
        self.assertEqual(report[22:25], bytes(3))

    def test_none_left_trigger_turns_the_effect_off(self):
        triggers, written = triggers_with_log()
        triggers.handle(["TRIGGERS", NONE, LEFT])
        report = written[0]
        self.assertEqual(report[1], 0x08)
        self.assertEqual(report[22], 0x05)
        self.assertEqual(report[11], 0x00)

    def test_reset_releases_only_the_triggers_left_engaged(self):
        triggers, written = triggers_with_log()
        triggers.handle(["TRIGGERS", SCRATCHABLE, LEFT])
        triggers.handle(["TRIGGERS", SCRATCHABLE, RIGHT])
        triggers.handle(["TRIGGERS", NONE, RIGHT])
        del written[:]
        triggers.handle(["RESET"])
        self.assertEqual([(report[1], report[22]) for report in written], [(0x08, 0x05)])
        del written[:]
        triggers.handle(["RESET"])
        self.assertEqual(written, [])

    def test_malformed_or_unknown_events_write_nothing(self):
        triggers, written = triggers_with_log()
        for fields in (["TRIGGERS", "x", RIGHT], ["TRIGGERS", "7", RIGHT], ["TRIGGERS", SCRATCHABLE, "5"],
                       ["TRIGGERS", SCRATCHABLE], ["START", "a", "meow", "0", "1"]):
            triggers.handle(fields)
        self.assertEqual(written, [])


class WriteToDualSenseTest(unittest.TestCase):
    def test_writes_the_report_to_the_device_found(self):
        with tempfile.TemporaryDirectory() as directory:
            device = os.path.join(directory, "hidraw")
            open(device, "wb").close()
            self.assertTrue(write_to_dualsense(b"\x02report", find_device=lambda: device))
            with open(device, "rb") as handle:
                self.assertEqual(handle.read(), b"\x02report")

    def test_missing_or_unwritable_device_is_reported_not_raised(self):
        self.assertFalse(write_to_dualsense(b"\x02", find_device=lambda: None))
        self.assertFalse(write_to_dualsense(b"\x02", find_device=lambda: "/nonexistent/hidraw"))


if __name__ == "__main__":
    unittest.main()

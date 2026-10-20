import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "daemon"))

from stray_haptics import (TRIGGER_EFFECTS, TRIGGER_LEFT, TRIGGER_NONE, TRIGGER_RIGHT, trigger_report,
                           write_to_dualsense)

ZONES = 10
HOLD_SECONDS = 10
REST_SECONDS = 3


def zone_bytes(first_zone, level):
    active = 0
    packed = 0
    for zone in range(first_zone, ZONES):
        active |= 1 << zone
        packed |= (level & 0x07) << (3 * zone)
    return [active & 0xFF, (active >> 8) & 0xFF] + [(packed >> shift) & 0xFF for shift in (0, 8, 16, 24)]


def feedback(first_zone, strength):
    return bytes([0x21] + zone_bytes(first_zone, strength - 1) + [0, 0, 0, 0])


def weapon(start_zone, end_zone, strength):
    edges = (1 << start_zone) | (1 << end_zone)
    return bytes([0x25, edges & 0xFF, (edges >> 8) & 0xFF, strength - 1, 0, 0, 0, 0, 0, 0, 0])


def vibration(first_zone, amplitude, frequency):
    return bytes([0x26] + zone_bytes(first_zone, amplitude - 1) + [0, 0, frequency, 0])


OPTIONS = [
    ("1", "feedback: firm resistance from 30% of the travel (strength 5 of 8)", feedback(3, 5)),
    ("2", "weapon: one snap between 20% and 60% of the travel (strength 6 of 8)", weapon(2, 6, 6)),
    ("3", "vibration: the trigger buzzes from the start of the travel (amplitude 6 of 8, 40 Hz)", vibration(0, 6, 40)),
    ("4", "continuous medium resistance from the start of the travel (the scratch effect)", bytes([0x01, 0x00, 0xA0])),
]


def apply(effect):
    return all(write_to_dualsense(trigger_report(side, effect)) for side in (TRIGGER_LEFT, TRIGGER_RIGHT))


def main():
    chosen = [option for option in OPTIONS if len(sys.argv) < 2 or option[0] in sys.argv[1:]]
    for number, label, effect in chosen:
        print(f"\noption {number}: {label}", flush=True)
        if not apply(effect):
            return 1
        print(f"{time.strftime('%H:%M:%S')} on ({effect.hex()}), press L2 and R2", flush=True)
        time.sleep(HOLD_SECONDS)
        apply(TRIGGER_EFFECTS[TRIGGER_NONE])
        print(f"{time.strftime('%H:%M:%S')} off", flush=True)
        time.sleep(REST_SECONDS)
    return 0


if __name__ == "__main__":
    sys.exit(main())

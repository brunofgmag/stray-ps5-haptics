import argparse
import fcntl
import glob
import json
import os
import queue
import signal
import subprocess
import sys
import threading
import time

import numpy as np

RATE = 48000
BLOCK = 240
PIPE_BYTES = 16384
GROUP_CHANNELS = {"speaker": (0, 1), "haptic": (2, 3)}
MIN_FADE = 0.01
DUALSENSE_VENDOR = "054C"
TRIGGER_REPORT_ID = 0x02
TRIGGER_REPORT_SIZE = 48
TRIGGER_LEFT = 0
TRIGGER_RIGHT = 1
TRIGGER_SLOTS = {TRIGGER_LEFT: (0x08, 22), TRIGGER_RIGHT: (0x04, 11)}
TRIGGER_SIDE_NAMES = {TRIGGER_LEFT: "left", TRIGGER_RIGHT: "right"}
TRIGGER_NONE = 0
TRIGGER_SCRATCHABLE = 1
TRIGGER_EFFECTS = {TRIGGER_NONE: bytes([0x05]), TRIGGER_SCRATCHABLE: bytes([0x01, 0x00, 0xA0])}
TRIGGER_STATE_NAMES = {TRIGGER_NONE: "none", TRIGGER_SCRATCHABLE: "scratchable"}


def soft_limit(samples, knee=0.8):
    magnitude = np.abs(samples)
    over = magnitude > knee
    if over.any():
        headroom = 1.0 - knee
        limited = knee + headroom * np.tanh((magnitude[over] - knee) / headroom)
        samples[over] = np.sign(samples[over]) * limited
    return samples


def log(message):
    print(time.strftime("%H:%M:%S"), message, flush=True)


class Sounds:
    def __init__(self, directory):
        self.directory = directory
        with open(os.path.join(directory, "manifest.json")) as manifest:
            self.manifest = json.load(manifest)["sounds"]
        self.cache = {}

    def get(self, name):
        info = self.manifest.get(name)
        if info is None:
            return None, None
        if name not in self.cache:
            data = np.fromfile(os.path.join(self.directory, info["file"]), dtype=np.float32).reshape(-1, 2)
            self.cache[name] = data
        return info, self.cache[name]


class Voice:
    def __init__(self, info, data, level, fade_in):
        self.data = data
        self.looping = info["looping"]
        self.volume = info["volume"]
        self.channels = GROUP_CHANNELS[info["group"]]
        self.position = 0
        self.level = level
        self.fading_in = fade_in > 0
        self.gain = 0.0 if self.fading_in else level
        self.fade_rate = 1.0 / max(fade_in, MIN_FADE)
        self.paused = False
        self.stopping = False
        self.finished = False

    def set_level(self, level):
        self.level = level

    def stop(self, fade_out):
        self.stopping = True
        self.fade_rate = 1.0 / max(fade_out, MIN_FADE)

    def next_gain(self, frames):
        step = self.fade_rate * frames / RATE
        if self.stopping:
            return max(0.0, self.gain - step)
        if self.fading_in:
            gain = min(self.level, self.gain + step)
            self.fading_in = gain < self.level
            return gain
        return self.level

    def render(self, frames):
        if self.paused or self.finished:
            return None
        end_gain = self.next_gain(frames)
        ramp = np.linspace(self.gain, end_gain, frames, endpoint=False, dtype=np.float32)
        self.gain = end_gain
        if self.stopping and self.gain <= 0.0:
            self.finished = True
        chunk = np.zeros((frames, 2), dtype=np.float32)
        filled = 0
        while filled < frames:
            available = len(self.data) - self.position
            if available <= 0:
                if self.looping:
                    self.position = 0
                    continue
                self.finished = True
                break
            take = min(available, frames - filled)
            chunk[filled:filled + take] = self.data[self.position:self.position + take]
            self.position += take
            filled += take
        return chunk * (ramp * self.volume)[:, None]


class Mixer:
    def __init__(self, sounds, haptic_gain, speaker_gain):
        self.sounds = sounds
        self.voices = {}
        self.group_gain = {(2, 3): haptic_gain, (0, 1): speaker_gain}
        self.global_pause = False

    def handle(self, fields):
        command = fields[0]
        if command == "START" and len(fields) >= 5:
            _, voice_id, sound, fade_in, level = fields[:5]
            info, data = self.sounds.get(sound)
            if info is None:
                log(f"unknown sound {sound}")
                return
            self.voices[voice_id] = Voice(info, data, float(level), float(fade_in))
            log(f"start {sound} level={float(level):.2f} fade={float(fade_in):.2f} id={voice_id}")
        elif command == "LEVEL" and len(fields) >= 3:
            voice = self.voices.get(fields[1])
            if voice:
                voice.set_level(float(fields[2]))
        elif command == "STOP" and len(fields) >= 2:
            voice = self.voices.get(fields[1])
            if voice:
                voice.stop(float(fields[2]) if len(fields) >= 3 else 0.0)
                log(f"stop id={fields[1]}")
        elif command == "PAUSE" and len(fields) >= 3:
            voice = self.voices.get(fields[1])
            if voice:
                voice.paused = fields[2] == "1"
        elif command == "PAUSEALL" and len(fields) >= 2:
            self.global_pause = fields[1] == "1"
            log(f"global pause {self.global_pause}")
        elif command == "RESET":
            self.voices.clear()
            self.global_pause = False
            log("reset")

    def render(self, frames):
        out = np.zeros((frames, 4), dtype=np.float32)
        if not self.global_pause:
            for voice_id in list(self.voices):
                voice = self.voices[voice_id]
                chunk = voice.render(frames)
                if chunk is not None:
                    left, right = voice.channels
                    gain = self.group_gain[voice.channels]
                    out[:, left] += chunk[:, 0] * gain
                    out[:, right] += chunk[:, 1] * gain
                if voice.finished:
                    del self.voices[voice_id]
        return soft_limit(out)


def follow(path, events):
    position = os.path.getsize(path) if os.path.exists(path) else 0
    pending = b""
    while True:
        try:
            size = os.path.getsize(path)
        except OSError:
            time.sleep(0.05)
            continue
        if size < position:
            position = 0
            pending = b""
            events.put(["RESET"])
        if size > position:
            with open(path, "rb") as handle:
                handle.seek(position)
                pending += handle.read(size - position)
                position = size
            *lines, pending = pending.split(b"\n")
            for line in lines:
                fields = line.decode("utf-8", "replace").rstrip("\r").split("\t")
                if fields and fields[0]:
                    events.put(fields)
        else:
            time.sleep(0.002)


def find_hidraw(vendor=DUALSENSE_VENDOR):
    for uevent in sorted(glob.glob("/sys/class/hidraw/hidraw*/device/uevent")):
        with open(uevent) as handle:
            if vendor in handle.read().upper():
                return "/dev/" + uevent.split("/")[4]
    return None


def write_to_dualsense(report, find_device=find_hidraw):
    device = find_device()
    if device is None:
        log("triggers: no DualSense in hidraw")
        return False
    try:
        descriptor = os.open(device, os.O_WRONLY)
        try:
            os.write(descriptor, report)
        finally:
            os.close(descriptor)
    except OSError as error:
        log(f"triggers: could not write {device}: {error}")
        return False
    return True


def trigger_report(side, effect):
    flag, offset = TRIGGER_SLOTS[side]
    report = bytearray(TRIGGER_REPORT_SIZE)
    report[0] = TRIGGER_REPORT_ID
    report[1] = flag
    report[offset:offset + len(effect)] = effect
    return bytes(report)


class Triggers:
    def __init__(self, write=write_to_dualsense):
        self.write = write
        self.engaged = set()

    def handle(self, fields):
        if fields[0] == "RESET":
            self.release()
            return
        if fields[0] != "TRIGGERS" or len(fields) < 3:
            return
        try:
            state, side = int(float(fields[1])), int(float(fields[2]))
        except ValueError:
            return
        if state not in TRIGGER_EFFECTS or side not in TRIGGER_SLOTS:
            return
        self.set(side, state)

    def set(self, side, state):
        self.write(trigger_report(side, TRIGGER_EFFECTS[state]))
        if state == TRIGGER_NONE:
            self.engaged.discard(side)
        else:
            self.engaged.add(side)
        log(f"triggers {TRIGGER_SIDE_NAMES[side]} {TRIGGER_STATE_NAMES[state]}")

    def release(self):
        for side in sorted(self.engaged):
            self.set(side, TRIGGER_NONE)


def find_sink(pattern):
    out = subprocess.run(["pactl", "list", "sinks", "short"], capture_output=True, text=True).stdout
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) > 1 and pattern in parts[1]:
            return parts[1]
    return None


def open_output(sink):
    process = subprocess.Popen(
        ["pw-cat", "--playback", "--raw", "--target", sink, "--rate", str(RATE), "--channels", "4",
         "--channel-map", "FL,FR,RL,RR", "--format", "f32", "--latency", "10ms",
         "--properties", '{ "media.name": "Stray PS5 haptics", "node.name": "stray-ps5-haptics" }', "-"],
        stdin=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
    pipe = process.stdin.fileno()
    try:
        fcntl.fcntl(pipe, fcntl.F_SETPIPE_SZ, PIPE_BYTES)
    except PermissionError:
        log(f"pipe kept at {fcntl.fcntl(pipe, fcntl.F_GETPIPE_SZ)} bytes: the user is over the kernel's pipe page limit")
    return process


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("events")
    parser.add_argument("--assets", default=os.path.expanduser("~/.local/share/stray-ps5-haptics"))
    parser.add_argument("--sink", default="DualSense_Wireless_Controller-00.pro-output-0")
    parser.add_argument("--haptic-gain", type=float, default=1.0)
    parser.add_argument("--speaker-gain", type=float, default=4.0)
    parser.add_argument("--exit-with-pid", type=int)
    args = parser.parse_args()

    mixer = Mixer(Sounds(args.assets), args.haptic_gain, args.speaker_gain)
    triggers = Triggers()
    events = queue.Queue()
    threading.Thread(target=follow, args=(args.events, events), daemon=True).start()
    signal.signal(signal.SIGTERM, lambda signum, frame: sys.exit(0))
    try:
        play(args, mixer, triggers, events)
    finally:
        triggers.release()


def play(args, mixer, triggers, events):
    output = None
    next_sink_check = 0.0
    log(f"following {args.events}")
    while True:
        if args.exit_with_pid and not os.path.exists(f"/proc/{args.exit_with_pid}"):
            log("game process ended")
            break
        while True:
            try:
                fields = events.get_nowait()
            except queue.Empty:
                break
            mixer.handle(fields)
            triggers.handle(fields)
        if output is None or output.poll() is not None:
            output = None
            now = time.monotonic()
            if now >= next_sink_check:
                next_sink_check = now + 2.0
                sink = find_sink(args.sink)
                if sink:
                    output = open_output(sink)
                    log(f"output open on {sink}")
            if output is None:
                mixer.render(BLOCK)
                time.sleep(BLOCK / RATE)
                continue
        try:
            output.stdin.write(mixer.render(BLOCK).tobytes())
        except BrokenPipeError:
            output = None
    if output:
        output.stdin.close()
        output.wait(timeout=2)


if __name__ == "__main__":
    sys.exit(main())

import fcntl
import glob
import os
import subprocess

DEFAULT_SINK = "DualSense_Wireless_Controller-00.pro-output-0"
DUALSENSE_VENDOR = "054C"
PIPE_BYTES = 16384


def find_hidraw(vendor=DUALSENSE_VENDOR):
    for uevent in sorted(glob.glob("/sys/class/hidraw/hidraw*/device/uevent")):
        with open(uevent) as handle:
            if vendor in handle.read().upper():
                return "/dev/" + uevent.split("/")[4]
    return None


def find_sink(pattern):
    out = subprocess.run(["pactl", "list", "sinks", "short"], capture_output=True, text=True).stdout
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) > 1 and pattern in parts[1]:
            return parts[1]
    return None


class PipeWireOutput:
    def __init__(self, sink, rate, log):
        self.name = sink
        self.process = subprocess.Popen(
            ["pw-cat", "--playback", "--raw", "--target", sink, "--rate", str(rate), "--channels", "4",
             "--channel-map", "FL,FR,RL,RR", "--format", "f32", "--latency", "10ms",
             "--properties", '{ "media.name": "Stray PS5 haptics", "node.name": "stray-ps5-haptics" }', "-"],
            stdin=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
        pipe = self.process.stdin.fileno()
        try:
            fcntl.fcntl(pipe, fcntl.F_SETPIPE_SZ, PIPE_BYTES)
        except PermissionError:
            log(f"pipe kept at {fcntl.fcntl(pipe, fcntl.F_GETPIPE_SZ)} bytes: the user is over the kernel's pipe page limit")

    def alive(self):
        return self.process.poll() is None

    def write(self, block):
        try:
            self.process.stdin.write(block.tobytes())
        except BrokenPipeError:
            return False
        return True

    def close(self):
        self.process.stdin.close()
        self.process.wait(timeout=2)


class Backend:
    default_sink = DEFAULT_SINK

    def __init__(self, log, rate, find_device=find_hidraw):
        self.log = log
        self.rate = rate
        self.find_device = find_device

    def write_trigger_report(self, report):
        device = self.find_device()
        if device is None:
            self.log("triggers: no DualSense in hidraw")
            return False
        try:
            descriptor = os.open(device, os.O_WRONLY)
            try:
                os.write(descriptor, report)
            finally:
                os.close(descriptor)
        except OSError as error:
            self.log(f"triggers: could not write {device}: {error}")
            return False
        return True

    def open_output(self, pattern):
        sink = find_sink(pattern)
        return PipeWireOutput(sink, self.rate, self.log) if sink else None

    def watch_process(self, pid):
        return lambda: os.path.exists(f"/proc/{pid}")

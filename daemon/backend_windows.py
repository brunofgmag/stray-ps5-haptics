import ctypes
import importlib

DEFAULT_SINK = "DualSense Wireless Controller"
DUALSENSE_VENDOR_ID = 0x054C
HOST_API = "Windows WASAPI"
CHANNELS = 4
SYNCHRONIZE = 0x00100000
WAIT_TIMEOUT = 0x00000102


def find_output_device(devices, hostapis, pattern):
    for index, device in enumerate(devices):
        if (hostapis[device["hostapi"]]["name"] == HOST_API and pattern in device["name"]
                and device["max_output_channels"] >= CHANNELS):
            return index, device["name"]
    return None


class WasapiOutput:
    def __init__(self, sounddevice, device, name, rate):
        self.name = name
        self.error = sounddevice.PortAudioError
        self.failed = False
        self.stream = sounddevice.OutputStream(
            device=device, samplerate=rate, channels=CHANNELS, dtype="float32", latency="low",
            extra_settings=sounddevice.WasapiSettings(auto_convert=True))
        self.stream.start()

    def alive(self):
        return not self.failed

    def write(self, block):
        try:
            self.stream.write(block)
        except self.error:
            self.failed = True
            return False
        return True

    def close(self):
        self.stream.close()


class Backend:
    default_sink = DEFAULT_SINK

    def __init__(self, log, rate, hid=None, sounddevice=None):
        self.log = log
        self.rate = rate
        self.hid = hid
        self.sounddevice = sounddevice
        self.last_output_failure = None

    def write_trigger_report(self, report):
        hid = self.hid or importlib.import_module("hid")
        found = hid.enumerate(DUALSENSE_VENDOR_ID)
        if not found:
            self.log("triggers: no DualSense among the HID devices")
            return False
        path = found[0]["path"]
        device = hid.device()
        try:
            device.open_path(path)
            if device.write(report) < 0:
                raise OSError(device.error())
        except OSError as error:
            self.log(f"triggers: could not write {path.decode(errors='replace')}: {error}")
            return False
        finally:
            device.close()
        return True

    def open_output(self, pattern):
        sounddevice = self.sounddevice or importlib.import_module("sounddevice")
        sounddevice._terminate()
        sounddevice._initialize()
        found = find_output_device(sounddevice.query_devices(), sounddevice.query_hostapis(), pattern)
        if found is None:
            return None
        device, name = found
        try:
            output = WasapiOutput(sounddevice, device, name, self.rate)
        except sounddevice.PortAudioError as error:
            failure = f"output could not open on {name}: {error}"
            if failure != self.last_output_failure:
                self.log(failure)
            self.last_output_failure = failure
            return None
        self.last_output_failure = None
        return output

    def watch_process(self, pid):
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel32.WaitForSingleObject.restype = wintypes.DWORD
        kernel32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        handle = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
        if not handle:
            return lambda: False
        return lambda: kernel32.WaitForSingleObject(handle, 0) == WAIT_TIMEOUT

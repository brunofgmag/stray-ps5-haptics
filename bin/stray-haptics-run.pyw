import os
import subprocess
import sys
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "daemon"))

from locations import config_dir, state_dir

EVENTS = ("Hk_project", "Binaries", "Win64", "ue4ss", "Mods", "StrayHaptics", "events.log")


def daemon_args(config):
    try:
        with open(os.path.join(config, "daemon_args")) as handle:
            return handle.readline().split()
    except FileNotFoundError:
        return []


def start_daemon(log):
    config = config_dir()
    with open(os.path.join(config, "game_dir")) as handle:
        game_dir = handle.read().strip()
    subprocess.Popen(
        [sys.executable, "-I", os.path.join(ROOT, "daemon", "stray_haptics.py"), os.path.join(game_dir, *EVENTS),
         "--exit-with-pid", str(os.getpid()), *daemon_args(config)],
        stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)


def main():
    state = state_dir()
    os.makedirs(state, exist_ok=True)
    with open(os.path.join(state, "daemon.log"), "w") as log:
        try:
            start_daemon(log)
        except Exception:
            traceback.print_exc(file=log)
    return subprocess.call(sys.argv[1:]) if len(sys.argv) > 1 else 0


if __name__ == "__main__":
    sys.exit(main())

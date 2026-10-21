import filecmp
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.join(ROOT, "daemon"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from locations import config_dir, data_dir
from pakextract import UNOODLE

WINDOWS = sys.platform == "win32"
STRAY_APP_ID = "1332010"
MOD_NAME = "StrayHaptics"
WIN64 = os.path.join("Hk_project", "Binaries", "Win64")
WINDOWS_STEAM = r"C:\Program Files (x86)\Steam"
WINDOWS_STEAM_KEYS = (("HKEY_CURRENT_USER", r"Software\Valve\Steam", "SteamPath"),
                      ("HKEY_LOCAL_MACHINE", r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"))


def run(command, **options):
    finished = subprocess.run(command, **options)
    if finished.returncode != 0:
        raise SystemExit(finished.returncode)


def library_paths(vdf):
    return [re.sub(r"\\(.)", r"\1", path) for path in re.findall(r'"path"\s+"((?:[^"\\]|\\.)*)"', vdf)]


def windows_steam_roots(winreg):
    roots = []
    for hive, key, value in WINDOWS_STEAM_KEYS:
        try:
            with winreg.OpenKey(getattr(winreg, hive), key) as handle:
                roots.append(winreg.QueryValueEx(handle, value)[0])
        except OSError:
            pass
    return roots + [WINDOWS_STEAM]


def steam_roots():
    if WINDOWS:
        import winreg

        return windows_steam_roots(winreg)
    return [os.path.join(os.path.expanduser("~"), ".local", "share", "Steam")]


def find_game_dir(roots):
    for steam in roots:
        try:
            with open(os.path.join(steam, "steamapps", "libraryfolders.vdf"), encoding="utf-8") as handle:
                libraries = library_paths(handle.read())
        except OSError:
            libraries = []
        for library in libraries + [steam]:
            if os.path.isfile(os.path.join(library, "steamapps", f"appmanifest_{STRAY_APP_ID}.acf")):
                return os.path.join(library, "steamapps", "common", "Stray")
    return None


def mods_dir(game_dir):
    return os.path.join(game_dir, WIN64, "ue4ss", "Mods")


def check_game(game_dir):
    win64 = os.path.join(game_dir, WIN64)
    if not os.path.isfile(os.path.join(win64, "Stray-Win64-Shipping.exe")):
        raise SystemExit(f"Stray not found in {game_dir}")
    if not (os.path.isfile(os.path.join(win64, "dwmapi.dll")) and os.path.isdir(mods_dir(game_dir))):
        raise SystemExit(f"UE4SS is not installed in {win64}")


def check_tools():
    tools = [] if os.path.isfile(UNOODLE) else ["cargo"]
    tools += ["ffmpeg"] if WINDOWS else ["ffmpeg", "pw-cat", "pactl", "python3"]
    for tool in tools:
        if shutil.which(tool) is None:
            raise SystemExit(f"missing {tool}")
    if not WINDOWS and subprocess.run(["python3", "-I", "-c", "import numpy"]).returncode != 0:
        raise SystemExit("missing python numpy")


def build_unoodle():
    if shutil.which("cargo"):
        run(["cargo", "build", "--release", "--quiet"], cwd=os.path.join(ROOT, "tools", "unoodle"))


def write_speaker_cues(manifest, target):
    with open(manifest) as handle:
        cues = json.load(handle)["cues"]
    with open(target, "w", newline="\n") as out:
        for name, cue in sorted(cues.items()):
            out.write(f"{name}\t{cue['send_level']}\n")


def enable_only(mods, name):
    with open(os.path.join(mods, "mods.txt")) as handle:
        lines = [line for line in handle.read().splitlines() if not line.startswith(name + " ")]
    lines = [line.split(" : ")[0] + " : 0" if " : " in line and not line.startswith(";") else line for line in lines]
    anchor = next((i for i, line in enumerate(lines) if line.startswith("; Built-in keybinds")), len(lines))
    lines.insert(anchor, f"{name} : 1")
    with open(os.path.join(mods, "mods.txt"), "w") as handle:
        handle.write("\n".join(lines) + "\n")
    with open(os.path.join(mods, "mods.json")) as handle:
        entries = [entry for entry in json.load(handle) if entry["mod_name"] != name]
    for entry in entries:
        entry["mod_enabled"] = False
    entries.insert(max(0, len(entries) - 1), {"mod_name": name, "mod_enabled": True})
    with open(os.path.join(mods, "mods.json"), "w") as handle:
        json.dump(entries, handle, indent=4)


def install_mod(mods, manifest):
    target = os.path.join(mods, MOD_NAME)
    if os.path.isdir(target):
        shutil.rmtree(target)
    shutil.copytree(os.path.join(ROOT, "mod", MOD_NAME), target)
    write_speaker_cues(manifest, os.path.join(target, "speaker_cues.txt"))
    enable_only(mods, MOD_NAME)


def install_wireplumber_rules(config_home):
    target_dir = os.path.join(config_home, "wireplumber", "wireplumber.conf.d")
    os.makedirs(target_dir, exist_ok=True)
    changed = False
    for rule in sorted(glob.glob(os.path.join(ROOT, "wireplumber", "*.conf"))):
        target = os.path.join(target_dir, os.path.basename(rule))
        if not (os.path.isfile(target) and filecmp.cmp(rule, target, shallow=False)):
            shutil.copyfile(rule, target)
            changed = True
    if changed:
        run(["systemctl", "--user", "restart", "wireplumber"])
        while subprocess.run(["pactl", "info"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode != 0:
            time.sleep(1)
        print(f"WirePlumber rules installed in {target_dir}")


def select_pro_audio():
    cards = subprocess.run(["pactl", "list", "cards", "short"], capture_output=True, text=True).stdout
    card = next((line.split()[1] for line in cards.splitlines() if "DualSense_Wireless_Controller" in line), None)
    if card:
        run(["pactl", "set-card-profile", card, "pro-audio"])
    else:
        print("No DualSense audio device found. Connect the controller and run this again to switch it to Pro Audio.")


def install_daemon_environment(data):
    venv = os.path.join(data, "venv")
    run([sys.executable, "-m", "venv", venv])
    run([os.path.join(venv, "Scripts", "python.exe"), "-m", "pip", "install", "--quiet", "--disable-pip-version-check",
         "-r", os.path.join(ROOT, "daemon", "requirements-windows.txt")])
    return os.path.join(venv, "Scripts", "pythonw.exe")


def windows_launch_options(pythonw):
    wrapper = os.path.join(ROOT, "bin", "stray-haptics-run.pyw")
    return ["Installed. Put this line in Stray's Steam launch options:",
            f'  "{pythonw}" "{wrapper}" %command%']


def linux_launch_options():
    return ["Installed. Steam launch options for Stray need these two pieces:",
            '  WINEDLLOVERRIDES="dwmapi=n,b" at the start',
            f"  {ROOT}/bin/stray-haptics-run right before %command%"]


def main():
    game_dir = next(iter(sys.argv[1:]), "") or find_game_dir(steam_roots())
    if not game_dir:
        raise SystemExit("Stray not found in your Steam libraries. Pass the game folder to the installer.")
    game_dir = os.path.abspath(game_dir)
    check_game(game_dir)
    check_tools()
    assets = data_dir()

    build_unoodle()
    run([sys.executable, "-I", os.path.join(ROOT, "tools", "build_assets.py"), game_dir, assets])
    install_mod(mods_dir(game_dir), os.path.join(assets, "manifest.json"))

    config = config_dir()
    os.makedirs(config, exist_ok=True)
    with open(os.path.join(config, "game_dir"), "w") as handle:
        handle.write(game_dir + "\n")

    if WINDOWS:
        message = windows_launch_options(install_daemon_environment(assets))
    else:
        install_wireplumber_rules(os.path.dirname(config))
        select_pro_audio()
        message = linux_launch_options()

    print()
    print("\n".join(message))


if __name__ == "__main__":
    main()

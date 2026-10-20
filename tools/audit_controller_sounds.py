import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from build_assets import PAK
from pakextract import read_entry
from paklist import list_pak

EXECUTABLE = "Hk_project/Binaries/Win64/Stray-Win64-Shipping.exe"
ROUTING_MARKERS = (b"Submix_controller", b"Submix_vibration", b"SCLASS_controller")
SOUND_FOLDER = "/Content/Sound/"
SOUND_SETTINGS = "/Content/Sound/tools/"


def asset_name(path):
    return os.path.basename(path)[:-len(".uasset")]


def executable_vibe_names(game_dir):
    with open(os.path.join(game_dir, EXECUTABLE), "rb") as executable:
        data = executable.read()
    found = re.findall(rb"(?:[A-Za-z0-9_]\x00){3,}_\x00V\x00I\x00B\x00E\x00", data)
    return {name.decode("utf-16-le") for name in found}


def main():
    game_dir, assets_dir = sys.argv[1:3]
    with open(os.path.join(assets_dir, "manifest.json")) as manifest_file:
        manifest = json.load(manifest_file)
    covered = set(manifest["sounds"]) | set(manifest["cues"])
    pak_path = os.path.join(game_dir, PAK)
    index = list_pak(pak_path)
    files = {name.replace("../../../", ""): entry for name, entry in index["files"].items()}
    uassets = sorted(name for name in files if name.endswith(".uasset"))
    named = {asset_name(name) for name in uassets if asset_name(name).endswith(("_VIBE", "_CONTROL"))}
    routed = set()
    with open(pak_path, "rb") as pak:
        for name in uassets:
            if SOUND_FOLDER not in name or SOUND_SETTINGS in name:
                continue
            data = read_entry(pak, files[name], index["methods"])
            if any(marker in data for marker in ROUTING_MARKERS):
                routed.add(asset_name(name))
    referenced = executable_vibe_names(game_dir)
    missing = {
        "named _VIBE or _CONTROL in the pak": sorted(named - covered),
        "routed to the controller in the pak": sorted(routed - covered),
        "named _VIBE in the executable": sorted(referenced - covered),
    }
    print(f"{len(uassets)} uassets, {len(named)} named, {len(routed)} routed, {len(referenced)} in the executable, "
          f"{len(covered)} covered by the manifest")
    for check, names in missing.items():
        print(f"missing ({check}): {', '.join(names) if names else 'none'}")
    return 1 if any(missing.values()) else 0


if __name__ == "__main__":
    sys.exit(main())

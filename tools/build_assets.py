import json
import os
import struct
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pakextract import read_entry
from paklist import list_pak
from uprops import Reader, name_map, read_properties

PAK = "Hk_project/Content/Paks/Hk_project-WindowsNoEditor.pak"
SOUND_ROOT = "Hk_project/Content/Sound/SFX/controllers/"
RATE = 48000


def ogg_stream(data):
    start = data.find(b"OggS")
    if start < 0:
        return None
    pos = start
    while data[pos:pos + 4] == b"OggS":
        header_type = data[pos + 5]
        segments = data[pos + 27:pos + 27 + data[pos + 26]]
        pos += 27 + len(segments) + sum(segments)
        if header_type & 4:
            break
    return data[start:pos]


def riff_stream(uexp, ubulk):
    start = uexp.find(b"RIFF")
    if start < 0:
        return None
    total = struct.unpack_from("<I", uexp, start + 4)[0] + 8
    inline_size = struct.unpack_from("<I", uexp, start - 16)[0]
    inline = uexp[start:start + inline_size]
    return inline + (ubulk or b"")[:total - len(inline)]


def decode(encoded, suffix, target):
    with tempfile.TemporaryDirectory() as directory:
        source = os.path.join(directory, "source" + suffix)
        with open(source, "wb") as handle:
            handle.write(encoded)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", source, "-ar", str(RATE), "-ac", "2",
                        "-c:a", "pcm_f32le", "-f", "f32le", target], check=True)


def sound_group(sound, names):
    if "SCLASS_controllerVibration" in names:
        return "haptic"
    if "SCLASS_controller" in names:
        return "speaker"
    return "haptic" if sound.endswith("_VIBE") else "speaker"


def cue_send_level(props):
    sends = props.get("SoundSubmixSends", {}).get("value") or {}
    for send in sends.get("items") or []:
        level = send.get("SendLevel", {}).get("value")
        if level is not None:
            return level
    return 1.0


def main():
    game_dir, out_dir = sys.argv[1:3]
    os.makedirs(out_dir, exist_ok=True)
    pak_path = os.path.join(game_dir, PAK)
    index = list_pak(pak_path)
    files = {name.replace("../../../", ""): entry for name, entry in index["files"].items()}
    uassets = [name[:-len(".uasset")] for name in files if name.endswith(".uasset") and "/Content/Sound/" in name]
    manifest = {"sounds": {}, "cues": {}}
    with open(pak_path, "rb") as pak:
        def read(name):
            entry = files.get(name)
            return read_entry(pak, entry, index["methods"]) if entry else None

        waves = {}
        for base in uassets:
            if base.startswith(SOUND_ROOT) or base.endswith("_VIBE"):
                waves[base] = None
        for base in uassets:
            if not base.endswith("_Cue"):
                continue
            uasset = read(base + ".uasset")
            if b"Submix_controller" not in uasset:
                continue
            names = name_map(uasset)
            props = read_properties(Reader(read(base + ".uexp")), names)
            cue_waves = sorted({name.split(".")[0] for name in names
                                if name.startswith("/Game/") and "." not in name.split("/")[-1]
                                and not name.endswith("_Cue") and "/Sound/tools/" not in name})
            manifest["cues"][os.path.basename(base)] = {
                "send_level": cue_send_level(props),
                "waves": [os.path.basename(wave) for wave in cue_waves],
            }
            for wave in cue_waves:
                waves["Hk_project/Content/" + wave[len("/Game/"):]] = "speaker"

        for base, forced_group in sorted(waves.items()):
            uasset, uexp, ubulk = read(base + ".uasset"), read(base + ".uexp"), read(base + ".ubulk")
            if uasset is None or uexp is None:
                print(f"skipped {base}: not in the pak")
                continue
            names = name_map(uasset)
            props = read_properties(Reader(uexp), names)
            sound = os.path.basename(base)
            encoded, suffix = ogg_stream(uexp), ".ogg"
            if encoded is None:
                encoded, suffix = riff_stream(uexp, ubulk), ".wav"
            if encoded is None:
                print(f"skipped {sound}: no audio stream found")
                continue
            decode(encoded, suffix, os.path.join(out_dir, sound + ".f32"))
            manifest["sounds"][sound] = {
                "file": sound + ".f32",
                "group": forced_group or sound_group(sound, names),
                "looping": bool(props.get("bLooping", {}).get("value", False)),
                "volume": props.get("Volume", {}).get("value", 1.0),
            }
    with open(os.path.join(out_dir, "manifest.json"), "w") as out:
        json.dump(manifest, out, indent=1, sort_keys=True)
    groups = {}
    for info in manifest["sounds"].values():
        groups[info["group"]] = groups.get(info["group"], 0) + 1
    print(f"{len(manifest['sounds'])} sounds {groups} and {len(manifest['cues'])} speaker cues written to {out_dir}")


if __name__ == "__main__":
    main()

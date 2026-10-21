#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
config_home="${XDG_CONFIG_HOME:-$HOME/.config}"
config_dir="$config_home/stray-ps5-haptics"
wireplumber_dir="$config_home/wireplumber/wireplumber.conf.d"
assets_dir="${XDG_DATA_HOME:-$HOME/.local/share}/stray-ps5-haptics"

install_wireplumber_rules() {
  local rule target changed=0
  mkdir -p "$wireplumber_dir"
  for rule in "$root"/wireplumber/*.conf; do
    target="$wireplumber_dir/$(basename "$rule")"
    if ! cmp -s "$rule" "$target"; then
      cp "$rule" "$target"
      changed=1
    fi
  done
  if [ "$changed" = 1 ]; then
    systemctl --user restart wireplumber
    until pactl info > /dev/null 2>&1; do sleep 1; done
    echo "WirePlumber rules installed in $wireplumber_dir"
  fi
}

select_pro_audio() {
  local card
  card="$(pactl list cards short | awk '/DualSense_Wireless_Controller/ {print $2; exit}')"
  if [ -n "$card" ]; then
    pactl set-card-profile "$card" pro-audio
  else
    echo "No DualSense audio device found. Connect the controller and run this again to switch it to Pro Audio."
  fi
}

find_game_dir() {
  local steam="$HOME/.local/share/Steam"
  local library
  for library in $(grep -oP '"path"\s+"\K[^"]+' "$steam/steamapps/libraryfolders.vdf" 2>/dev/null) "$steam"; do
    if [ -f "$library/steamapps/appmanifest_1332010.acf" ]; then
      echo "$library/steamapps/common/Stray"
      return 0
    fi
  done
  return 1
}

game_dir="${1:-$(find_game_dir)}"
win64="$game_dir/Hk_project/Binaries/Win64"
mods="$win64/ue4ss/Mods"

[ -f "$win64/Stray-Win64-Shipping.exe" ] || { echo "Stray not found in $game_dir" >&2; exit 1; }
[ -f "$win64/dwmapi.dll" ] && [ -d "$mods" ] || { echo "UE4SS is not installed in $win64" >&2; exit 1; }
for tool in cargo ffmpeg pw-cat pactl python3; do
  command -v "$tool" > /dev/null || { echo "missing $tool" >&2; exit 1; }
done
python3 -I -c "import numpy" || { echo "missing python numpy" >&2; exit 1; }

(cd "$root/tools/unoodle" && cargo build --release --quiet)
python3 -I "$root/tools/build_assets.py" "$game_dir" "$assets_dir"

rm -rf "$mods/StrayHaptics"
cp -r "$root/mod/StrayHaptics" "$mods/StrayHaptics"
python3 -I - "$assets_dir/manifest.json" "$mods/StrayHaptics/speaker_cues.txt" <<'EOF'
import json
import sys

manifest, target = sys.argv[1:3]
with open(manifest) as handle:
    cues = json.load(handle)["cues"]
with open(target, "w") as out:
    for name, cue in sorted(cues.items()):
        out.write(f"{name}\t{cue['send_level']}\n")
EOF

python3 -I - "$mods" <<'EOF'
import json
import sys

mods = sys.argv[1]
name = "StrayHaptics"
with open(f"{mods}/mods.txt") as handle:
    lines = [line for line in handle.read().splitlines() if not line.startswith(name + " ")]
lines = [line.split(" : ")[0] + " : 0" if " : " in line and not line.startswith(";") else line for line in lines]
anchor = next((i for i, line in enumerate(lines) if line.startswith("; Built-in keybinds")), len(lines))
lines.insert(anchor, f"{name} : 1")
with open(f"{mods}/mods.txt", "w") as handle:
    handle.write("\n".join(lines) + "\n")
with open(f"{mods}/mods.json") as handle:
    entries = [entry for entry in json.load(handle) if entry["mod_name"] != name]
for entry in entries:
    entry["mod_enabled"] = False
entries.insert(max(0, len(entries) - 1), {"mod_name": name, "mod_enabled": True})
with open(f"{mods}/mods.json", "w") as handle:
    json.dump(entries, handle, indent=4)
EOF

mkdir -p "$config_dir"
echo "$game_dir" > "$config_dir/game_dir"

install_wireplumber_rules
select_pro_audio

echo
echo "Installed. Steam launch options for Stray need these two pieces:"
echo "  WINEDLLOVERRIDES=\"dwmapi=n,b\" at the start"
echo "  $root/bin/stray-haptics-run right before %command%"

# stray-ps5-haptics

PS5 controller haptics, controller speaker sounds and adaptive trigger resistance for the PC version of Stray, on Linux.

The PC version of Stray ships the PS5 vibration and controller speaker sounds, but routes them to an audio output that doesn't exist on PC, so nothing reaches the controller. This mod listens for the game's calls and plays the same sounds through the DualSense. Vibration goes to the haptic actuators, and meows and other effects go to the controller speaker. When the cat reaches a scratching spot, the triggers stiffen.

Windows is not supported yet.

## What you need

- Stray on Steam, running through Proton.
- [UE4SS](https://github.com/UE4SS-RE/RE-UE4SS/releases) 3.0.1 (`UE4SS_v3.0.1.zip`). Extract it into `Stray/Hk_project/Binaries/Win64`, so that `dwmapi.dll` and the `ue4ss` folder sit next to `Stray-Win64-Shipping.exe`.
- A DualSense that the PC sees as a USB device: either plugged in with a cable, or connected over Bluetooth through a Raspberry Pi Pico 2 W running [DS5Dongle](https://github.com/awalol/DS5Dongle). A plain Bluetooth connection won't work, because the haptics and the speaker go through the controller's USB audio device.
- PipeWire with WirePlumber 0.5 or newer.
- `python3` with `numpy`, `cargo` (Rust), `ffmpeg`, `pw-cat` and `pactl`.

## Install

```bash
git clone https://github.com/brunofgmag/stray-ps5-haptics.git
cd stray-ps5-haptics
./install.sh
```

The installer looks for Stray in your Steam libraries. If it can't find it, pass the game folder: `./install.sh /path/to/steamapps/common/Stray`.

What the installer does:

- It extracts the controller sounds from your copy of the game into `~/.local/share/stray-ps5-haptics`. Nothing from the game is stored in this repository.
- It copies the mod to `ue4ss/Mods/StrayHaptics` and enables it. It also **disables every other UE4SS mod** in `mods.txt` and `mods.json`.
- It installs two WirePlumber rules in `~/.config/wireplumber/wireplumber.conf.d` and restarts WirePlumber if either rule changed. One rule names the controller's four output channels, which the haptics need to reach the actuators. The other keeps the controller speaker from crackling when you play through the Pico.
- It switches the DualSense audio device to the Pro Audio profile. If the controller isn't connected at that point, connect it and run `./install.sh` again.

Next, set Stray's launch options in Steam (Properties → General → Launch Options). The installer prints the exact line for your system, and it looks like this:

```
WINEDLLOVERRIDES="dwmapi=n,b" /path/to/stray-ps5-haptics/bin/stray-haptics-run %command%
```

The launch options point into the repository folder, so don't move it after installing.

Leave Steam Input enabled for Stray. If you turn it off, the game talks to the controller directly: the haptics get weaker and the light bar goes dark.

## Check that it works

Start the game and open `~/.local/state/stray-ps5-haptics/daemon.log`. Each session starts with a `following` line. Once the controller is found, a line like this one appears:

```
output open on alsa_output.usb-Sony_Interactive_Entertainment_DualSense_Wireless_Controller-00.pro-output-0
```

## Volume

Put the options in `~/.config/stray-ps5-haptics/daemon_args`, all on one line. For example:

```
--haptic-gain 0.8 --speaker-gain 3.0
```

The defaults are `--haptic-gain 1.0` and `--speaker-gain 4.0`.

## Troubleshooting

### The game doesn't see the controller at all

Steam Input creates a virtual controller for the game, and it needs the kernel's `uinput` module to do that. If your system updated the kernel and you haven't rebooted since, the module can't load. Rebooting fixes it.

### The log has no `output open on` line

Either the controller is disconnected, or its audio device isn't in the Pro Audio profile. Check the profile with:

```bash
pactl list cards | grep -A40 DualSense | grep 'Active Profile'
```

It should say `pro-audio`. Running `./install.sh` again switches it back.

## Uninstall

1. Remove the two pieces from Stray's launch options.
2. Delete `ue4ss/Mods/StrayHaptics` from the game folder.
3. Delete `~/.local/share/stray-ps5-haptics` and `~/.config/stray-ps5-haptics`.
4. Delete `51-dualsense-pro-positions.conf` and `52-dualsense-pro-input-follows.conf` from `~/.config/wireplumber/wireplumber.conf.d`, then run `systemctl --user restart wireplumber`.

This leaves UE4SS installed. To remove it as well, delete `dwmapi.dll` and the `ue4ss` folder.

## Credits

- [UE4SS](https://github.com/UE4SS-RE/RE-UE4SS) runs the mod inside the game.
- [oozextract](https://crates.io/crates/oozextract) reads the game's compressed sound files.
- [DS5Dongle](https://github.com/awalol/DS5Dongle) carries the haptics over Bluetooth.

## License

MIT. See [LICENSE](LICENSE).

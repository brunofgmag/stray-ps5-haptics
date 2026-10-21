# stray-ps5-haptics

PS5 controller haptics, controller speaker sounds and adaptive trigger resistance for the PC version of Stray, on Linux, with experimental Windows support.

The PC version of Stray ships the PS5 vibration and controller speaker sounds, but routes them to an audio output that doesn't exist on PC, so nothing reaches the controller. This mod listens for the game's calls and plays the same sounds through the DualSense. Vibration goes to the haptic actuators, and meows and other effects go to the controller speaker. When the cat reaches a scratching spot, the triggers stiffen.

The mod was built and played on Linux. The Windows port passes its tests on a Windows machine without a controller, but nobody has played Stray with it on Windows yet. Its install steps are in [Windows (experimental)](#windows-experimental), and the sections before it are about Linux.

## What you need

- Stray on Steam, running through Proton.
- [UE4SS](https://github.com/UE4SS-RE/RE-UE4SS/releases) 3.0.1 (`UE4SS_v3.0.1.zip`). Extract it into `Stray/Hk_project/Binaries/Win64`, so that `dwmapi.dll` and the `ue4ss` folder sit next to `Stray-Win64-Shipping.exe`.
- A DualSense that the PC sees as a USB device: either plugged in with a cable, or connected over Bluetooth through a Raspberry Pi Pico 2 W running [DS5Dongle](https://github.com/awalol/DS5Dongle). A plain Bluetooth connection won't work, because the haptics and the speaker go through the controller's USB audio device.
- PipeWire with WirePlumber 0.5 or newer.
- `python3` with `numpy`, `ffmpeg`, `pw-cat`, `pactl` and `cargo` (Rust). You can skip `cargo` if you use the Linux download from the [Releases page](https://github.com/brunofgmag/stray-ps5-haptics/releases), which comes with the Rust part already built.

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

## Windows (experimental)

The Windows version runs the same mod and mixes the sounds the same way as on Linux. Only the route to the controller differs: the sound goes to the DualSense's audio device through WASAPI, and trigger changes go through hidapi. The tests pass on Windows in GitHub Actions, on a machine with no controller attached. Nobody has tried these parts on a real Windows PC yet:

- Steam running the launch line below on Windows.
- Windows showing the controller as a four-channel audio device, with the haptics on the two rear channels as on Linux.
- Trigger changes reaching the controller while Steam Input also has it open.

If you try it, please open an issue and attach your `daemon.log`, whether it works or not.

### What you need on Windows

- Stray on Steam.
- [UE4SS](https://github.com/UE4SS-RE/RE-UE4SS/releases) 3.0.1, extracted into `Stray\Hk_project\Binaries\Win64` the same way as on Linux. Windows loads it without any extra launch option.
- A DualSense connected by USB cable, or through a Pico 2 W running DS5Dongle. Plain Bluetooth won't work here either.
- Python 3.14 and FFmpeg. Both install from a terminal with winget:

  ```
  winget install --id Python.Python.3.14 -e
  winget install --id Gyan.FFmpeg -e
  ```

  Open a new terminal afterwards so both are on the PATH. Stick to Python 3.14: newer versions may not have a ready-made hidapi package yet, and the triggers need it.

### Install on Windows

1. Download `stray-ps5-haptics-<version>-windows.zip` from the [Releases page](https://github.com/brunofgmag/stray-ps5-haptics/releases) and extract it to a folder you'll keep, such as `C:\Games\stray-ps5-haptics`. The launch options point into this folder, so don't move it after installing.
2. Open a terminal in that folder and run:

   ```
   py install.py
   ```

   If the installer can't find Stray, pass the game folder: `py install.py "D:\SteamLibrary\steamapps\common\Stray"`.
3. Copy the line the installer prints into Stray's launch options in Steam. It looks like this:

   ```
   "C:\Users\you\AppData\Local\stray-ps5-haptics\venv\Scripts\pythonw.exe" "C:\Games\stray-ps5-haptics\bin\stray-haptics-run.pyw" %command%
   ```

On Windows the installer writes the sounds to `%LOCALAPPDATA%\stray-ps5-haptics` and creates a Python environment there with `numpy`, `sounddevice` and `hidapi`. It leaves the Windows sound settings alone. Like on Linux, it copies the mod into `ue4ss\Mods\StrayHaptics` and **disables every other UE4SS mod**.

The zip from the Releases page includes a ready-built copy of the tool that reads the game's compressed sound files. If you clone the repository instead, install [Rust](https://rustup.rs) as well, and the installer builds that tool itself.

Leave Steam Input enabled for Stray, as on Linux.

### Check that it works on Windows

Start the game and open `%LOCALAPPDATA%\stray-ps5-haptics\daemon.log`. Each session starts with a `following` line. Once the controller is found, an `output open on` line appears with the name of its audio device.

If that line never shows up, check the controller's name in the Sound settings. The daemon looks for a four-channel audio device with `DualSense Wireless Controller` in its name. If Windows names it differently, add `--sink` and one word from that name to `%APPDATA%\stray-ps5-haptics\daemon_args`, for example `--sink DualSense`. Also check that the controller's speaker setup in the Sound control panel is Quadraphonic. With a stereo setup, Windows would mix the haptics into the speaker.

A line starting with `triggers:` means a trigger change didn't reach the controller, and the rest of the line says why.

The volume options are the same as on Linux. Put them in `%APPDATA%\stray-ps5-haptics\daemon_args`.

### Uninstall on Windows

1. Remove the line from Stray's launch options.
2. Delete `ue4ss\Mods\StrayHaptics` from the game folder.
3. Delete `%LOCALAPPDATA%\stray-ps5-haptics` and `%APPDATA%\stray-ps5-haptics`.

## Credits

- [UE4SS](https://github.com/UE4SS-RE/RE-UE4SS) runs the mod inside the game.
- [oozextract](https://crates.io/crates/oozextract) reads the game's compressed sound files.
- [DS5Dongle](https://github.com/awalol/DS5Dongle) carries the haptics over Bluetooth.
- [python-sounddevice](https://github.com/spatialaudio/python-sounddevice) and [hidapi](https://github.com/trezor/cython-hidapi) reach the controller on Windows.

## License

MIT. See [LICENSE](LICENSE).

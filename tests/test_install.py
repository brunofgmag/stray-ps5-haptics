import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)

import install

SHIPPED_MODS_TXT = ("CheatManagerEnablerMod : 1\r\nConsoleCommandsMod : 1\r\nBPModLoaderMod : 1\r\n"
                    "jsbLuaProfilerMod : 0\r\n\r\n; Built-in keybinds, do not move up!\r\nKeybinds : 1\r\n")
SHIPPED_MODS_JSON = [{"mod_name": "CheatManagerEnablerMod", "mod_enabled": True},
                     {"mod_name": "BPModLoaderMod", "mod_enabled": True},
                     {"mod_name": "Keybinds", "mod_enabled": True}]
WINDOWS_VDF = r'''"libraryfolders"
{
	"0"
	{
		"path"		"C:\\Program Files (x86)\\Steam"
		"label"		""
	}
	"1"
	{
		"path"		"D:\\Games\\Steam \"Fast\" Library"
		"apps"
		{
			"1332010"		"8123456789"
		}
	}
}
'''


def touch(path, content=""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="") as handle:
        handle.write(content)


def fake_game(directory, with_ue4ss=True):
    win64 = os.path.join(directory, "Stray", "Hk_project", "Binaries", "Win64")
    touch(os.path.join(win64, "Stray-Win64-Shipping.exe"))
    if with_ue4ss:
        touch(os.path.join(win64, "dwmapi.dll"))
        touch(os.path.join(win64, "ue4ss", "Mods", "mods.txt"), SHIPPED_MODS_TXT)
        touch(os.path.join(win64, "ue4ss", "Mods", "mods.json"), json.dumps(SHIPPED_MODS_JSON))
    return os.path.join(directory, "Stray")


class FakeKey:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeWinreg:
    HKEY_CURRENT_USER = "HKCU"
    HKEY_LOCAL_MACHINE = "HKLM"

    def __init__(self, values):
        self.values = values

    def OpenKey(self, hive, key):
        if (hive, key) not in self.values:
            raise FileNotFoundError(2, "The system cannot find the file specified")
        self.opened = (hive, key)
        return FakeKey()

    def QueryValueEx(self, handle, value):
        return self.values[self.opened][value], 1


class SteamLibraryTest(unittest.TestCase):
    def test_reads_windows_library_paths_with_their_escapes_undone(self):
        self.assertEqual(install.library_paths(WINDOWS_VDF),
                         ["C:\\Program Files (x86)\\Steam", 'D:\\Games\\Steam "Fast" Library'])

    def test_reads_linux_library_paths_as_they_are(self):
        vdf = '"libraryfolders"\n{\n\t"0"\n\t{\n\t\t"path"\t\t"/home/cat/.local/share/Steam"\n\t}\n}\n'
        self.assertEqual(install.library_paths(vdf), ["/home/cat/.local/share/Steam"])

    def test_steam_roots_come_from_the_registry_before_the_default_folder(self):
        winreg = FakeWinreg({("HKCU", r"Software\Valve\Steam"): {"SteamPath": "c:/program files (x86)/steam"}})
        self.assertEqual(install.windows_steam_roots(winreg),
                         ["c:/program files (x86)/steam", r"C:\Program Files (x86)\Steam"])

    def test_finds_stray_in_a_second_library(self):
        with tempfile.TemporaryDirectory() as directory:
            steam, library = os.path.join(directory, "Steam"), os.path.join(directory, "Library")
            vdf = f'"libraryfolders"\n{{\n\t"1"\n\t{{\n\t\t"path"\t\t"{library}"\n\t}}\n}}\n'.replace("\\", "\\\\")
            touch(os.path.join(steam, "steamapps", "libraryfolders.vdf"), vdf)
            touch(os.path.join(library, "steamapps", "appmanifest_1332010.acf"))
            self.assertEqual(install.find_game_dir([os.path.join(directory, "missing"), steam]),
                             os.path.join(library, "steamapps", "common", "Stray"))

    def test_finds_stray_in_the_steam_folder_itself_or_nowhere(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertIsNone(install.find_game_dir([directory]))
            touch(os.path.join(directory, "steamapps", "appmanifest_1332010.acf"))
            self.assertEqual(install.find_game_dir([directory]), os.path.join(directory, "steamapps", "common", "Stray"))


class GameCheckTest(unittest.TestCase):
    def test_a_folder_without_stray_or_without_ue4ss_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(SystemExit, "Stray not found"):
                install.check_game(directory)
            game = fake_game(directory, with_ue4ss=False)
            with self.assertRaisesRegex(SystemExit, "UE4SS is not installed"):
                install.check_game(game)

    def test_a_game_with_ue4ss_passes(self):
        with tempfile.TemporaryDirectory() as directory:
            install.check_game(fake_game(directory))


class ModInstallTest(unittest.TestCase):
    def test_copies_the_mod_writes_the_cues_and_enables_only_it(self):
        with tempfile.TemporaryDirectory() as directory:
            mods = install.mods_dir(fake_game(directory))
            touch(os.path.join(mods, "StrayHaptics", "stale.lua"))
            manifest = os.path.join(directory, "manifest.json")
            touch(manifest, json.dumps({"cues": {"meow_b_Cue": {"send_level": 0.5}, "meow_a_Cue": {"send_level": 1.0}}}))
            for _ in range(2):
                install.install_mod(mods, manifest)
            installed = os.path.join(mods, "StrayHaptics")
            self.assertFalse(os.path.exists(os.path.join(installed, "stale.lua")))
            with open(os.path.join(installed, "Scripts", "main.lua"), "rb") as copied, \
                    open(os.path.join(ROOT, "mod", "StrayHaptics", "Scripts", "main.lua"), "rb") as source:
                self.assertEqual(copied.read(), source.read())
            with open(os.path.join(installed, "speaker_cues.txt"), "rb") as handle:
                self.assertEqual(handle.read(), b"meow_a_Cue\t1.0\nmeow_b_Cue\t0.5\n")
            with open(os.path.join(mods, "mods.txt")) as handle:
                self.assertEqual(handle.read().splitlines(),
                                 ["CheatManagerEnablerMod : 0", "ConsoleCommandsMod : 0", "BPModLoaderMod : 0",
                                  "jsbLuaProfilerMod : 0", "", "StrayHaptics : 1",
                                  "; Built-in keybinds, do not move up!", "Keybinds : 0"])
            with open(os.path.join(mods, "mods.json")) as handle:
                self.assertEqual(json.load(handle), [{"mod_name": "CheatManagerEnablerMod", "mod_enabled": False},
                                                     {"mod_name": "BPModLoaderMod", "mod_enabled": False},
                                                     {"mod_name": "StrayHaptics", "mod_enabled": True},
                                                     {"mod_name": "Keybinds", "mod_enabled": False}])


class LaunchOptionsTest(unittest.TestCase):
    def test_windows_line_runs_the_wrapper_with_the_daemon_python_before_the_game(self):
        pythonw = r"C:\Users\Cat Owner\AppData\Local\stray-ps5-haptics\venv\Scripts\pythonw.exe"
        line = install.windows_launch_options(pythonw)[1].strip()
        wrapper = os.path.join(install.ROOT, "bin", "stray-haptics-run.pyw")
        self.assertEqual(line, f'"{pythonw}" "{wrapper}" %command%')
        self.assertTrue(os.path.isfile(wrapper))

    def test_linux_lines_keep_the_dll_override_and_the_shell_wrapper(self):
        lines = install.linux_launch_options()
        self.assertIn('WINEDLLOVERRIDES="dwmapi=n,b"', lines[1])
        self.assertTrue(lines[2].strip().startswith(f"{install.ROOT}/bin/stray-haptics-run "))


if __name__ == "__main__":
    unittest.main()

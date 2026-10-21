import os
import sys

NAME = "stray-ps5-haptics"


def _xdg(environ, variable, fallback):
    return os.path.join(environ.get(variable) or os.path.join(os.path.expanduser("~"), fallback), NAME)


def config_dir(environ=os.environ, platform=sys.platform):
    if platform == "win32":
        return os.path.join(environ["APPDATA"], NAME)
    return _xdg(environ, "XDG_CONFIG_HOME", ".config")


def data_dir(environ=os.environ, platform=sys.platform):
    if platform == "win32":
        return os.path.join(environ["LOCALAPPDATA"], NAME)
    return _xdg(environ, "XDG_DATA_HOME", os.path.join(".local", "share"))


def state_dir(environ=os.environ, platform=sys.platform):
    if platform == "win32":
        return os.path.join(environ["LOCALAPPDATA"], NAME)
    return _xdg(environ, "XDG_STATE_HOME", os.path.join(".local", "state"))

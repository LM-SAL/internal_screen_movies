"""
Basic Config items.
"""

import shutil
from pathlib import Path

HINODE_MOVIES_FILENAME = "*mp4"
HINODE_MOVIES_PATH = None
IRIS_MOVIES_FILENAME = "*mp4"
IRIS_MOVIES_PATH = Path("/irisa/mod/podmovie/modvideos/")
SDO_MOVIES_FILENAME = "AIAtriratio*.mp4"
SDO_MOVIES_PATH = Path("/viz2/media/SunInTime/")

# macOS does not put the VLC binary on PATH.
VLC = shutil.which("vlc") or "/Applications/VLC.app/Contents/MacOS/VLC"
# Homebrew on Intel macOS installs here, which launchd jobs do not have on PATH.
FFPROBE = shutil.which("ffprobe") or "/usr/local/bin/ffprobe"

PATHS = (IRIS_MOVIES_PATH, SDO_MOVIES_PATH, HINODE_MOVIES_PATH)
FILENAME_PATTERN = (IRIS_MOVIES_FILENAME, SDO_MOVIES_FILENAME, HINODE_MOVIES_FILENAME)

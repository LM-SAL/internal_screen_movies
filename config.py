"""Movie sources and external programs."""

import shutil
from pathlib import Path

# Each source is (directory, filename pattern, prefer encoded replacements).
# Set a directory to None to disable it.
SOURCES = (
    (Path("/irisa/mod/podmovie/modvideos/"), "*mp4", True),
    (Path("/viz2/media/SunInTime/"), "AIAtriratio*.mp4", False),
)

# macOS does not put the VLC binary on PATH.
VLC = shutil.which("vlc") or "/Applications/VLC.app/Contents/MacOS/VLC"

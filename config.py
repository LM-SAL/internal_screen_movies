"""Movie sources and external programs."""

import shutil
from pathlib import Path

# Each source is (directory, filename pattern); None disables a directory.
SOURCES = (
    (Path("/irisa/mod/podmovie/modvideos/"), "*mp4"),
    (Path("/viz2/media/SunInTime/"), "AIAtriratio*.mp4"),
)

# macOS does not put the VLC binary on PATH.
VLC = shutil.which("vlc") or "/Applications/VLC.app/Contents/MacOS/VLC"
# Homebrew on Intel macOS installs here, which launchd jobs do not have on PATH.
FFPROBE = shutil.which("ffprobe") or "/usr/local/bin/ffprobe"

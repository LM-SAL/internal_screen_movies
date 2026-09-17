# internal_screen_movies

Play IRIS and SDO/AIA movies from mounted network shares. Configure directories and
filename patterns in `config.py` (`SOURCES`); set a directory to `None` to disable it.
Requires Python 3.10+ and VLC for playback. No extra Python packages are needed.

    python display_movies.py

Ignores movies in `orig/`, prefers suffixed encoded IRIS movies over an unsuffixed
movie beside them, and keeps one copy per remaining filename. It balances the sources
by repeating entries, shuffles `playlist.m3u`, and plays it in VLC fullscreen, looping
at half speed. VLC skips files that cannot play.

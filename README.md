# internal_screen_movies

Play IRIS and SDO/AIA movies from mounted network shares. Configure directories and
filename patterns in `config.py` (`SOURCES`); set a directory to `None` to disable it.
Requires Python 3.10+, VLC for playback, and ffprobe for checking (`brew install ffmpeg`).
No extra Python packages are needed.

    python display_movies.py

Keeps one copy per movie filename, balances the sources by repeating entries, shuffles
`playlist.m3u`, and plays it in VLC fullscreen, looping at half speed. VLC skips files
that cannot play.

    python find_bad_movies.py

Checks every copy with eight workers and writes `bad_movies.csv` with source, creator
(from the IRIS pod directory), path and problem. Decodes the first frame and tail,
verifies timestamps reach the final second, and reports decoder errors, unknown
duration and read failures. Middle corruption can be missed; long keyframe gaps require
more reading.

Timestamped progress appears every five seconds, with counts, problems, speed and a
pending file. Problems appear immediately. Each probe times out after five minutes;
directory discovery may still wait on a stalled mount.

    python find_bad_movies.py --verbose --output /tmp/bad_movies.csv
    python find_bad_movies.py 2>&1 | tee movie-check.log

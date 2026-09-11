# internal_screen_movies

Simple script to find and display movies on an internal screen.

It finds IRIS and SDO/AIA movies on the mounted network shares (paths in `config.py`),
writes `playlist.m3u` with each source repeated so both contribute roughly equal
numbers of entries, and plays it in VLC fullscreen, shuffled, looping, at half speed.

Needs Python 3.10+ and VLC (on macOS the app bundle is found automatically).

    python display_movies.py

`KNOWN_BAD_*.txt` list files that do not play and are skipped. To find new ones, set
`CHECK_MOVIES = True` in `display_movies.py` (needs `pip install -r requirements.txt`);
it opens every remaining file with OpenCV and appends the failures to `KNOWN_BAD_*.txt`.

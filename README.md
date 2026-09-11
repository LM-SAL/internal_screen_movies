# internal_screen_movies

Simple script to find and display movies on an internal screen.

It finds IRIS and SDO/AIA movies on the mounted network shares (paths in `config.py`),
keeps one entry per movie name (the IRIS share holds the same movie in several pod
directories and again in the `orig` subdirectory of the pod that uploaded it), writes
`playlist.m3u` with each source repeated so both contribute roughly equal numbers of
entries, shuffles that list, and plays it in VLC fullscreen, looping, at half speed.

Needs Python 3.10+ and VLC (on macOS the app bundle is found automatically).

    python display_movies.py

Files that do not play are left to VLC, which skips to the next entry by itself.

"""Build a balanced movie playlist and play it in VLC."""

import logging
import random
import shutil
import subprocess
import threading
from pathlib import Path

from config import SOURCES, VLC

logger = logging.getLogger(__name__)

HERE = Path(__file__).resolve().parent
PLAYLIST = HERE / "playlist.m3u"
# A stale network mount blocks forever on stat, so the mount check gives up.
MOUNT_CHECK_TIMEOUT = 30.0


def check_everything_is_installed() -> None:
    """Check that VLC is installed."""
    if shutil.which(VLC) is None:
        msg = f"Error: {VLC} is not installed."
        raise FileNotFoundError(msg)


def mount_problem(directory: Path, timeout: float = MOUNT_CHECK_TIMEOUT) -> str | None:
    """Check a directory in a daemon thread so a stalled mount can time out."""
    failures: list[OSError] = []

    def probe() -> None:
        try:
            directory.expanduser().resolve(strict=True)
        except OSError as exc:
            failures.append(exc)

    thread = threading.Thread(target=probe, daemon=True)
    thread.start()
    thread.join(timeout)

    if thread.is_alive():
        return f"did not respond within {timeout:g} seconds (stale mount?)"
    if failures:
        return f"cannot be read: {failures[0].strerror or failures[0]}"
    return None


def check_directories_mounted() -> None:
    """Check that every configured source is accessible."""
    for directory, _ in SOURCES:
        if directory is None:
            continue
        problem = mount_problem(directory)
        if problem is not None:
            msg = f"Error: Directory '{directory}' {problem}"
            raise OSError(msg)


def get_paths_for_movies(base_path: Path, filename: str) -> list[str]:
    """Keep one copy per filename, preferring shallower paths over pod/orig copies."""
    files = set(map(str, base_path.rglob(filename)))
    seen: dict[str, str] = {}
    for path in sorted(files, key=lambda path: (len(Path(path).parts), path)):
        seen.setdefault(Path(path).name, path)
    return list(seen.values())


def balance(sources: list[list[str]]) -> list[str]:
    """Repeat sources to give each roughly equal representation in the playlist."""
    if not sources:
        msg = "No sources to build a playlist from."
        raise ValueError(msg)
    target = max(len(source) for source in sources)
    movies = []
    for source in sources:
        if source:
            movies.extend(source * max(1, round(target / len(source))))
    return movies


def create_playlist(movies: list[str]) -> None:
    """Write the M3U playlist."""
    logger.info("Writing %s", PLAYLIST)
    PLAYLIST.write_text("#EXTM3U\n" + "".join(f"{path}\n" for path in movies), encoding="utf-8")


def play_movies() -> None:
    """Play in VLC; report failures but allow termination by a signal."""
    vlc = subprocess.run(  # NOQA: S603
        [VLC, "--rate", "0.5", "--fullscreen", "--loop", str(PLAYLIST)],
        check=False,
    )
    if vlc.returncode < 0:
        logger.info("VLC was stopped by signal %d", -vlc.returncode)
        return
    if vlc.returncode != 0:
        raise subprocess.CalledProcessError(vlc.returncode, vlc.args)


def run_playlist() -> None:
    """Find movies, write the playlist and start VLC."""
    check_everything_is_installed()
    check_directories_mounted()
    sources = []
    for base_path, filename_pattern in SOURCES:
        if base_path is None:
            continue
        logger.info("Searching for movies in %s", base_path)
        found = get_paths_for_movies(base_path, filename_pattern)
        if not found:
            msg = f"No movies found in {base_path}"
            raise FileNotFoundError(msg)
        logger.info("Found %d movies in %s", len(found), base_path)
        sources.append(found)
    movies = balance(sources)
    random.shuffle(movies)
    create_playlist(movies)
    play_movies()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_playlist()

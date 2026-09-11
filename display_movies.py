"""
Very simple/rudimentary script to play movies in random order.
"""

import functools
import logging
import random
import shutil
import subprocess
import threading
import time
from pathlib import Path

from config import FILENAME_PATTERN, PATHS, VLC

logger = logging.getLogger(__name__)

HERE = Path(__file__).resolve().parent
PLAYLIST = HERE / "playlist.m3u"
# A stale network mount blocks forever on stat, so the mount check gives up.
MOUNT_CHECK_TIMEOUT = 30.0


def timeit(func):
    """
    Decorator to measure the time taken to execute a function.
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        logger.info("Time taken to execute %s: %.4f seconds.", func.__name__, time.perf_counter() - start)
        return result

    return wrapper


@timeit
def check_everything_is_installed() -> None:
    """
    Check that VLC is installed.

    Raises
    ------
    FileNotFoundError
        If VLC cannot be found.
    """
    if shutil.which(VLC) is None:
        msg = f"Error: {VLC} is not installed."
        raise FileNotFoundError(msg)


def mount_problem(directory: Path, timeout: float = MOUNT_CHECK_TIMEOUT) -> str | None:
    """
    Why ``directory`` is unusable, or None when it can be read.

    ``Path.exists`` reports a permission error as a missing directory, and a
    stale network mount blocks the stat forever, so the probe runs in a daemon
    thread that is abandoned when it times out.

    Parameters
    ----------
    directory : Path
        The directory to look at.
    timeout : float
        Seconds to wait for the file system to answer.

    Returns
    -------
    str | None
        A description of the problem, or None if there is none.
    """
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


@timeit
def check_directories_mounted() -> None:
    """
    Check if the net directory are mounted.

    Raises
    ------
    IOError
        If a directory cannot be read.
    """
    for directory in PATHS:
        if directory is None:
            continue
        problem = mount_problem(directory)
        if problem is not None:
            msg = f"Error: Directory '{directory}' {problem}"
            raise OSError(msg)


@timeit
def get_paths_for_movies(base_path: Path, filename: str) -> list[str]:
    """
    Get all the paths for the movies in the given directory, minus repeated
    copies of a movie.

    The IRIS share keeps the same movie in several pod directories, and again in
    the ``orig`` subdirectory of the pod that uploaded it. One entry per movie is
    enough, else every copy gets its own playlist entry and its own repetition,
    so the copies are matched on the file name, which carries the observation
    date, instrument and time. Paths are ordered so the pod directory copy is the
    one kept and not its ``orig`` duplicate.

    Parameters
    ----------
    base_path : Path
        The base path to search for movies.
    filename : str
        The filename pattern to search for.

    Returns
    -------
    list
        A list of paths to the movies.
    """
    files = set(map(str, base_path.rglob(filename)))
    seen: dict[str, str] = {}
    for path in sorted(files, key=lambda path: (len(Path(path).parts), path)):
        seen.setdefault(Path(path).name, path)
    return list(seen.values())


def balance(sources: list[list[str]]) -> list[str]:
    """
    Repeat each source so that every source contributes roughly the same number
    of playlist entries.

    Every playlist entry is played once per cycle, so repetition is the only way
    to weight a source: a source's share of a cycle is its share of entries.

    Parameters
    ----------
    sources : list[list[str]]
        The movie paths per source. Empty sources contribute nothing.

    Returns
    -------
    list[str]
        The combined, weighted list of movie paths.

    Raises
    ------
    ValueError
        If there are no sources to balance.
    """
    if not sources:
        msg = "No sources to build a playlist from."
        raise ValueError(msg)
    target = max((len(source) for source in sources), default=0)
    movies = []
    for source in sources:
        if target and source:
            movies.extend(source * max(1, round(target / len(source))))
    return movies


def shuffled(movies: list[str]) -> list[str]:
    """
    Reorder the playlist entries at random.

    Doing it here instead of with VLC's ``--random`` makes the written file the
    actual playback order, which other players and humans can read, and keeps
    the order testable.

    Parameters
    ----------
    movies : list
        A list of paths to the movies.

    Returns
    -------
    list[str]
        A new list with the same entries in random order.
    """
    order = movies.copy()
    random.shuffle(order)
    return order


@timeit
def create_playlist(movies: list[str]) -> None:
    """
    Create a playlist m3u file.

    Parameters
    ----------
    movies : list
        A list of paths to the movies.
    """
    logger.info("Writing %s", PLAYLIST)
    PLAYLIST.write_text("#EXTM3U\n" + "".join(f"{path}\n" for path in movies), encoding="utf-8")


@timeit
def play_movies() -> None:
    """
    Play the playlist with VLC, looping the whole file over and over.

    Raises
    ------
    subprocess.CalledProcessError
        If VLC itself fails, but not when it is killed by a signal.
    """
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
    """
    Find the movies, write the playlist and hand it to VLC.
    """
    check_everything_is_installed()
    check_directories_mounted()
    sources = []
    for base_path, filename_pattern in zip(PATHS, FILENAME_PATTERN, strict=True):
        if base_path is None:
            continue
        logger.info("Searching for movies in %s", base_path)
        found = get_paths_for_movies(base_path, filename_pattern)
        if not found:
            msg = f"No movies found in {base_path}"
            raise FileNotFoundError(msg)
        logger.info("Found %d movies in %s", len(found), base_path)
        sources.append(found)
    create_playlist(shuffled(balance(sources)))
    play_movies()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_playlist()

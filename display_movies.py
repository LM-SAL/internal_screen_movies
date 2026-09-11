"""
Very simple/rudimentary script to play movies in random order.
"""

import logging
import shutil
import subprocess
import time
from pathlib import Path

from config import FILENAME_PATTERN, PATHS, VLC

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

HERE = Path(__file__).resolve().parent
PLAYLIST = HERE / "playlist.m3u"


def timeit(func):
    """
    Decorator to measure the time taken to execute a function.
    """

    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        logger.info(f"Time taken to execute {func.__name__}: {time.time() - start} seconds.")  # NOQA: G004
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


@timeit
def check_directories_mounted() -> None:
    """
    Check if the net directory are mounted.

    Raises
    ------
    IOError
        If the directory does not exist.
    """
    for directory in PATHS:
        if directory is not None and not directory.expanduser().resolve().exists():
            msg = f"Error: Directory '{directory}' not found."
            raise OSError(msg)


@timeit
def check_videos(file_paths: list[str]) -> list[str]:
    """
    Using CV check if a video is legit.

    Parameters
    ----------
    file_paths : List[Str]
        List of file paths to check.

    Returns
    -------
    List[Str]
        List of strs for legit movies.
    """
    import cv2  # NOQA: PLC0415

    result = []
    bad_movies = []
    for file_path in file_paths:
        video = cv2.VideoCapture(file_path)
        ok = video.isOpened() and video.read()[0]
        video.release()
        (result if ok else bad_movies).append(file_path)
    if file_paths:
        mod = "IRIS" if "iris" in file_paths[0] else "AIA"
        (HERE / f"bad_movies_{mod}.txt").write_text("\n".join(bad_movies))
    return result


@timeit
def get_paths_for_movies(base_path: Path, filename: str) -> list[str]:
    """
    Get all the paths for the movies in the given directory, minus the known bad ones.

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
    mod = "IRIS" if "iris" in str(base_path) else "AIA"
    files = set(map(str, base_path.rglob(filename)))
    bad_files = set((HERE / f"KNOWN_BAD_{mod}.txt").read_text().splitlines())
    return sorted(files - bad_files)


def balance(sources: list[list[str]]) -> list[str]:
    """
    Repeat each source so that every source contributes roughly the same number of playlist entries.

    VLC's --random picks uniformly over playlist entries, so repetition is the only way to weight a source.

    Parameters
    ----------
    sources : list[list[str]]
        One non-empty list of movie paths per source.

    Returns
    -------
    list[str]
        The combined, weighted list of movie paths.
    """
    target = max(len(source) for source in sources)
    movies = []
    for source in sources:
        movies.extend(source * round(target / len(source)))
    return movies


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
    PLAYLIST.write_text("\n".join(movies))


@timeit
def play_movies_in_random_order() -> None:
    """
    Play the playlist in random order using VLC.
    """
    subprocess.run([VLC, "--rate", "0.5", "--fullscreen", "--random", "--loop", str(PLAYLIST)], check=False)  # NOQA: S603


if __name__ == "__main__":
    check_everything_is_installed()
    check_directories_mounted()
    # Uses CV to open the file to verify its a legit movie
    # Slows down the code quite a bit
    CHECK_MOVIES = False
    sources = []
    for base_path, filename_pattern in zip(PATHS, FILENAME_PATTERN, strict=True):
        if base_path is None:
            continue
        logger.info("Searching for movies in %s", base_path)
        found = get_paths_for_movies(base_path, filename_pattern)
        if CHECK_MOVIES:
            found = check_videos(found)
        if not found:
            msg = f"No movies found in {base_path}"
            raise FileNotFoundError(msg)
        logger.info("Found %d movies in %s", len(found), base_path)
        sources.append(found)
    create_playlist(balance(sources))
    play_movies_in_random_order()

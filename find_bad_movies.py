"""
Find movies that cannot be played, so they can be reported to whoever made
them.
"""

import argparse
import csv
import json
import logging
import re
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from config import FFPROBE, FILENAME_PATTERN, PATHS
from display_movies import HERE, check_directories_mounted, timeit

logger = logging.getLogger(__name__)

REPORT = HERE / "bad_movies.csv"
# ffprobe reads from network mounts, which can stall.
PROBE_TIMEOUT = 300.0
# The work is mostly waiting on the network, so run several probes at once.
WORKERS = 8
# The most distinct ffprobe error lines to keep in the report.
ERROR_LINES = 3
# IRIS uploads live in pod_<last>_<first>_<upload time> directories.
POD_DIRECTORY = re.compile(r"^pod_(.+)_\d{4}-\d{2}-\d{2}T")


def check_everything_is_installed() -> None:
    """
    Check that ffprobe is installed.

    Raises
    ------
    FileNotFoundError
        If ffprobe cannot be found.
    """
    if shutil.which(FFPROBE) is None:
        msg = f"Error: {FFPROBE} is not installed (brew install ffmpeg)."
        raise FileNotFoundError(msg)


def ffprobe(*args: str) -> tuple[dict, str]:
    """
    Run ffprobe with JSON output.

    Parameters
    ----------
    *args : str
        Arguments for ffprobe, ending with the file to probe.

    Returns
    -------
    tuple[dict, str]
        The parsed output and the errors ffprobe printed, which are empty if
        it succeeded without complaint.
    """
    try:
        result = subprocess.run(  # NOQA: S603
            [FFPROBE, "-v", "error", "-of", "json", *args],
            capture_output=True,
            text=True,
            timeout=PROBE_TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {}, f"ffprobe did not finish within {PROBE_TIMEOUT:g} seconds"
    # Drop the "[demuxer @ 0x...] " and "<path>: " prefixes, and repeats of the
    # same error, which a damaged stream can print for every frame.
    path = re.escape(args[-1])
    errors = (re.sub(rf"^(\[.*?\] |{path}: )", "", line) for line in result.stderr.strip().splitlines())
    error = "; ".join(list(dict.fromkeys(errors))[:ERROR_LINES])
    if result.returncode != 0:
        return {}, error or f"ffprobe exited with status {result.returncode}"
    return json.loads(result.stdout or "{}"), error


def movie_problem(path: str) -> str | None:
    """
    Why the movie at ``path`` cannot be played, or None when it looks fine.

    The movie must open, have a video stream and decode a frame at the start
    and one second before the end. This catches empty, truncated and
    non-movie files without reading the whole file over the network, but not
    damage in between.

    Parameters
    ----------
    path : str
        The movie to check.

    Returns
    -------
    str | None
        A description of the problem, or None if there is none.
    """
    info, error = ffprobe("-select_streams", "v:0", "-show_entries", "stream=codec_type:format=duration", path)
    if not info:
        return error
    if not info.get("streams"):
        return "no video stream"
    try:
        seek = float(info["format"]["duration"]) - 1
    except (KeyError, ValueError):
        seek = 0
    intervals = f"%+#1,{seek:.3f}%+#1" if seek > 0 else "%+#1"
    info, error = ffprobe(
        "-select_streams",
        "v:0",
        "-count_frames",
        "-read_intervals",
        intervals,
        "-show_entries",
        "stream=nb_read_frames",
        path,
    )
    if not info:
        return error
    expected = intervals.count("#")
    decoded = int(info["streams"][0].get("nb_read_frames", 0))
    if decoded < expected:
        where = "the first frame" if decoded == 0 else "the frame before the end"
        return f"could not decode {where}" + (f": {error}" if error else "")
    return None


def creator(path: str) -> str:
    """
    Who uploaded the movie at ``path``, taken from its pod directory.

    Parameters
    ----------
    path : str
        The movie path.

    Returns
    -------
    str
        The ``last_first`` name from the pod directory, or an empty string for
        movies outside pod directories.
    """
    for part in Path(path).parts:
        match = POD_DIRECTORY.match(part)
        if match:
            return match.group(1)
    return ""


@timeit
def find_bad_movies(base_path: Path, filename: str) -> list[dict[str, str]]:
    """
    Check every movie in ``base_path``, including repeated copies, since each
    copy is a separate upload that may need fixing.

    Parameters
    ----------
    base_path : Path
        The base path to search for movies.
    filename : str
        The filename pattern to search for.

    Returns
    -------
    list[dict[str, str]]
        One report row per bad movie.
    """
    paths = sorted(map(str, base_path.rglob(filename)))
    logger.info("Checking %d movies in %s", len(paths), base_path)
    with ThreadPoolExecutor(WORKERS) as pool:
        problems = pool.map(movie_problem, paths)
        return [
            {"source": str(base_path), "creator": creator(path), "path": path, "problem": problem}
            for path, problem in zip(paths, problems, strict=True)
            if problem is not None
        ]


def write_report(rows: list[dict[str, str]], report: Path) -> None:
    """
    Write the bad movies to a CSV file, grouped by source and creator.

    Parameters
    ----------
    rows : list[dict[str, str]]
        The report rows.
    report : Path
        The CSV file to write.
    """
    rows = sorted(rows, key=lambda row: (row["source"], row["creator"], row["path"]))
    with report.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=["source", "creator", "path", "problem"])
        writer.writeheader()
        writer.writerows(rows)
    logger.info("Wrote %d bad movies to %s", len(rows), report)


def main() -> None:
    """
    Check the movies in every configured directory and write the report.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-o", "--output", type=Path, default=REPORT, help=f"CSV file to write (default: {REPORT})")
    args = parser.parse_args()
    check_everything_is_installed()
    check_directories_mounted()
    rows = []
    for base_path, filename_pattern in zip(PATHS, FILENAME_PATTERN, strict=True):
        if base_path is not None:
            rows.extend(find_bad_movies(base_path, filename_pattern))
    write_report(rows, args.output)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()

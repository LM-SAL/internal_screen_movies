"""Spot-check movies for corruption and write a CSV report."""

import argparse
import csv
import json
import logging
import math
import re
import shutil
import subprocess
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from contextlib import contextmanager
from pathlib import Path

from config import FFPROBE, SOURCES
from display_movies import HERE, check_directories_mounted

logger = logging.getLogger(__name__)

REPORT = HERE / "bad_movies.csv"
# ffprobe reads from network mounts, which can stall.
PROBE_TIMEOUT = 300.0
# The work is mostly waiting on the network, so run several probes at once.
WORKERS = 8
# The most distinct ffprobe error lines to keep in the report.
ERROR_LINES = 3
PROGRESS_INTERVAL = 5.0
# IRIS uploads live in pod_<last>_<first>_<upload time> directories.
POD_DIRECTORY = re.compile(r"^pod_(.+)_\d{4}-\d{2}-\d{2}T")


def check_everything_is_installed() -> None:
    """Check that ffprobe is installed."""
    if shutil.which(FFPROBE) is None:
        msg = f"Error: {FFPROBE} is not installed (brew install ffmpeg)."
        raise FileNotFoundError(msg)


def ffprobe(*args: str) -> tuple[dict, str]:
    """Run ffprobe with JSON output."""
    try:
        result = subprocess.run(  # NOQA: S603
            [FFPROBE, "-v", "error", "-of", "json", *args],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=PROBE_TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {}, f"ffprobe did not finish within {PROBE_TIMEOUT:g} seconds"
    except OSError as exc:
        return {}, f"could not run ffprobe: {exc}"
    # Drop the "[demuxer @ 0x...] " and "<path>: " prefixes, and repeats of the
    # same error, which a damaged stream can print for every frame.
    path = re.escape(args[-1])
    errors = (re.sub(rf"^(\[.*?\] |{path}: )", "", line) for line in result.stderr.strip().splitlines())
    error = "; ".join(list(dict.fromkeys(errors))[:ERROR_LINES])
    if result.returncode != 0:
        return {}, error or f"ffprobe exited with status {result.returncode}"
    try:
        return json.loads(result.stdout or "{}"), error
    except json.JSONDecodeError:
        return {}, error or "ffprobe returned invalid JSON"


def finite_number(value) -> float | None:
    """Parse an optional ffprobe timestamp or duration."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def movie_problem(path: str) -> str | None:
    """Check the first frame and tail for decoding errors and missing video."""
    logger.debug("Checking %s", path)
    info, error = ffprobe(
        "-select_streams",
        "v:0",
        "-read_intervals",
        "%+#1",
        "-show_frames",
        "-show_entries",
        "frame=best_effort_timestamp_time:stream=start_time,duration:format=start_time,duration",
        path,
    )
    if error:
        return error
    if not info.get("streams"):
        return "no video stream"
    if not info.get("frames"):
        return "could not decode the first frame"
    stream = info["streams"][0]
    container = info.get("format", {})
    start = finite_number(stream.get("start_time"))
    if start is None:
        start = finite_number(container.get("start_time")) or 0.0
    duration = finite_number(stream.get("duration"))
    if duration is None:
        duration = finite_number(container.get("duration"))
        # Container duration starts at the container's origin, which can
        # differ from the video start (for example, when audio starts first).
        if duration is not None:
            duration += (finite_number(container.get("start_time")) or 0.0) - start
    if duration is None or duration <= 0:
        return "could not determine video duration to check the end"
    target = start + max(0.0, duration - 1.0)
    return tail_problem(path, target)


def tail_problem(path: str, target: float) -> str | None:
    """Decode from the preceding keyframe through EOF and verify the timestamp."""
    info, error = ffprobe(
        "-select_streams",
        "v:0",
        "-read_intervals",
        f"{target:.6f}%",
        "-show_frames",
        "-show_entries",
        "frame=best_effort_timestamp_time,duration_time",
        path,
    )
    if error:
        return error
    for frame in info.get("frames", []):
        timestamp = finite_number(frame.get("best_effort_timestamp_time"))
        frame_duration = finite_number(frame.get("duration_time")) or 0.0
        # Include frame duration for movies below one frame per second.
        if timestamp is not None and timestamp + frame_duration >= target:
            return None
    return f"could not decode video reaching {target:g} seconds near the end"


def creator(path: str) -> str:
    """Who uploaded the movie at ``path``, taken from its pod directory."""
    for part in Path(path).parts:
        match = POD_DIRECTORY.match(part)
        if match:
            return match.group(1)
    return ""


@contextmanager
def search_progress(base_path: Path, paths: list[str]):
    """Keep reporting discovery progress even while a network directory stalls."""
    stopped = threading.Event()

    def report() -> None:
        while not stopped.wait(PROGRESS_INTERVAL):
            logger.info("Searching %s: %d movies found so far", base_path, len(paths))

    thread = threading.Thread(target=report, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stopped.set()
        thread.join()


def find_bad_movies(base_path: Path, filename: str) -> list[dict[str, str]]:
    """Check every copy of every movie and report progress as files finish."""
    logger.info("Searching %s for %s", base_path, filename)
    paths: list[str] = []
    with search_progress(base_path, paths):
        paths.extend(map(str, base_path.rglob(filename)))
    total = len(paths)
    if not total:
        logger.warning("No movies found in %s matching %s", base_path, filename)
        return []
    logger.info("Checking %d movies in %s with %d workers", total, base_path, WORKERS)
    rows = []
    completed = 0
    started = last_report = time.monotonic()
    remaining = iter(paths)
    with ThreadPoolExecutor(WORKERS) as pool:
        # Keep only WORKERS futures queued and consume them as they finish,
        # so a slow first file cannot hide progress on other files.
        pending = {}
        for path in remaining:
            pending[pool.submit(movie_problem, path)] = path
            if len(pending) == WORKERS:
                break
        while pending:
            until_report = max(0.0, PROGRESS_INTERVAL - (time.monotonic() - last_report))
            done, _ = wait(pending, timeout=until_report, return_when=FIRST_COMPLETED)
            for future in done:
                path = pending.pop(future)
                problem = future.result()
                completed += 1
                if problem is not None:
                    logger.warning("Problem in %s: %s", path, problem)
                    rows.append({"source": str(base_path), "creator": creator(path), "path": path, "problem": problem})
                else:
                    logger.debug("OK: %s", path)
                next_path = next(remaining, None)
                if next_path is not None:
                    pending[pool.submit(movie_problem, next_path)] = next_path
            now = time.monotonic()
            if not pending or now - last_report >= PROGRESS_INTERVAL:
                elapsed = now - started
                logger.info(
                    "%s: %d/%d checked (%.0f%%), %d problems, %.1fs elapsed, %.1f movies/s",
                    base_path,
                    completed,
                    total,
                    100 * completed / total,
                    len(rows),
                    elapsed,
                    completed / max(elapsed, 0.001),
                )
                if pending:
                    logger.info("Still checking: %s", next(iter(pending.values())))
                last_report = now
    return rows


def write_report(rows: list[dict[str, str]], report: Path) -> None:
    """Write the bad movies to a CSV file, grouped by source and creator."""
    rows = sorted(rows, key=lambda row: (row["source"], row["creator"], row["path"]))
    with report.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=["source", "creator", "path", "problem"])
        writer.writeheader()
        writer.writerows(rows)
    logger.info("Wrote %d bad movies to %s", len(rows), report)


def main() -> None:
    """Check the movies in every configured directory and write the report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-o", "--output", type=Path, default=REPORT, help=f"CSV file to write (default: {REPORT})")
    parser.add_argument("-v", "--verbose", action="store_true", help="also log when each movie starts and passes")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    check_everything_is_installed()
    logger.info("Checking configured network directories")
    check_directories_mounted()
    rows = []
    for base_path, filename_pattern in SOURCES:
        if base_path is not None:
            rows.extend(find_bad_movies(base_path, filename_pattern))
    write_report(rows, args.output)


if __name__ == "__main__":
    main()

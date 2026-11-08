"""Word-count -> time mapping (used when the script has no timestamps)."""
from __future__ import annotations
import re
from .models import Line


def count_words(text: str) -> int:
    return len(re.findall(r"\S+", text))


def fmt_ts(seconds: float) -> str:
    """Output in MM:SS.SS format with 2 decimal places."""
    if seconds < 0:
        seconds = 0.0
    total_hundredths = round(seconds * 100)
    minutes = total_hundredths // 6000
    remainder = total_hundredths % 6000
    secs = remainder / 100
    return f"{minutes:02d}:{secs:05.2f}"


def parse_ts(raw: str) -> float:
    """Parse timestamp string into seconds.
    Handles MM:SS.SS, MM:SS, and HH:MM:SS format."""
    s = raw.strip().strip("()[]")
    parts = [float(p) for p in s.split(":")]
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return round(parts[0] * 60 + parts[1], 4)
    return round(parts[0] * 3600 + parts[1] * 60 + parts[2], 4)


def count_pauses(text: str, patterns: list[str]) -> int:
    return sum(len(re.findall(p, text, re.I)) for p in patterns)


def base_duration(words: int, pauses: int, wpm: float, pause_sec: float) -> float:
    return words / wpm * 60 + pauses * pause_sec


def line_duration(line: Line, timing: dict) -> float:
    pauses = count_pauses(line.text, timing["pause_patterns"])
    base = base_duration(line.words, pauses, timing["words_per_minute"], timing["seconds_per_pause"])
    return base * timing.get("calibration_factor", 1.0)


def assign_times(lines: list[Line], timing: dict) -> bool:
    """Fill line.start/line.end per episode.
    If a line already has BOTH ts AND end values set (from the structured parser),
    skip time estimation for that line.
    Only estimate times for lines that don't have explicit timestamps.
    Returns True if any explicit timestamps were found."""
    found = False
    current_ep, t = None, 0.0
    for line in lines:
        if line.episode != current_ep:
            current_ep, t = line.episode, 0.0

        # If both ts and end values are set (from structured parser), skip estimation
        if line.ts is not None and (line.end != 0.0 or line.element_type):
            found = True
            t = line.end
            continue

        if line.ts is not None:
            t, found = line.ts, True
        line.start = t
        t += line_duration(line, timing)
        line.end = t
    return found


def fit_calibration(rows: list[dict], timing: dict) -> float:
    """rows: dicts with words, pauses, actual_seconds. Returns actual/estimated ratio."""
    est = sum(base_duration(float(r["words"]), float(r["pauses"]),
                            timing["words_per_minute"], timing["seconds_per_pause"]) for r in rows)
    act = sum(float(r["actual_seconds"]) for r in rows)
    return act / est if est else 1.0

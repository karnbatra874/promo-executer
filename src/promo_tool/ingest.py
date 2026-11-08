from __future__ import annotations
import re
from pathlib import Path
from typing import Optional
from .models import Line, Chunk
from .timemap import count_words, parse_ts

HEADER_RE = re.compile(r"^\*\*(.+?)\*\*\s*:?$")
TIMESTAMP_RE = re.compile(
    r"^Start:\s*\(?([0-9:.]+)\)?\s*\|\s*End:\s*\(?([0-9:.]+)\)?",
    re.IGNORECASE
)
SCENE_RE = re.compile(r"^SCENE\s+(\d+)\b", re.IGNORECASE)
SCRIPT_START_RE = re.compile(r"---\s*SCRIPT\s+START\s*---", re.IGNORECASE)
SCRIPT_END_RE = re.compile(r"---\s*SCRIPT\s+END\s*---", re.IGNORECASE)
EPISODE_RE = re.compile(r"EPISODE\s+NUMBER:\s*(?:Episode\s*)?(\d+)", re.IGNORECASE)

LEGACY_EPISODE_RE = re.compile(r"^\s*(?:#+\s*)?(?:episode|ep\.?)\s*(\d+)\b.*$", re.IGNORECASE)
LEGACY_TS_RE = re.compile(r"^\s*\[?(\d{1,2}:\d{2}(?::\d{2})?)\]?\s*")


def parse_structured_script(text: str) -> list[Line]:
    """Parse one episode's structured script format into Line objects."""
    ep_m = EPISODE_RE.search(text)
    if not ep_m:
        ep_m = re.search(r"\bEpisode\s*(\d+)", text, re.IGNORECASE)
    episode = int(ep_m.group(1)) if ep_m else 1

    start_m = SCRIPT_START_RE.search(text)
    if not start_m:
        return []
    body = text[start_m.end():]
    end_m = SCRIPT_END_RE.search(body)
    if end_m:
        body = body[:end_m.start()]

    lines: list[Line] = []
    line_number = 0
    current_scene: Optional[int] = None

    current_header: Optional[str] = None
    current_start: Optional[float] = None
    current_end: Optional[float] = None
    current_content: list[str] = []

    def flush() -> None:
        nonlocal line_number, current_header, current_start, current_end, current_content
        if current_header is None:
            return
        raw_content = re.sub(r"\s+", " ", " ".join(current_content)).strip()
        if not raw_content:
            current_header = None
            current_start = None
            current_end = None
            current_content = []
            return

        header_raw = current_header.rstrip(":").strip()
        header_upper = header_raw.upper()

        start_sec = current_start if current_start is not None else 0.0
        end_sec = current_end if current_end is not None else start_sec

        if header_upper == "CAMERA" or header_upper.startswith("CAMERA ") or header_upper.startswith("CAMERA("):
            element_type = "camera"
            speaker = None
            tone = None
            if raw_content.upper().startswith("CAMERA:"):
                raw_content = raw_content[7:].strip()
            formatted_text = f"CAMERA: {raw_content}"
        elif header_upper == "ACTION" or header_upper.startswith("ACTION ") or header_upper.startswith("ACTION("):
            element_type = "action"
            speaker = None
            tone = None
            if raw_content.upper().startswith("ACTION:"):
                raw_content = raw_content[7:].strip()
            formatted_text = f"ACTION: {raw_content}"
        elif (header_upper in ("SOUND FX", "SOUND EFFECT", "SOUND EFFECTS", "SFX") or
              header_upper.startswith("SOUND FX") or header_upper.startswith("SFX")):
            element_type = "sound_fx"
            speaker = None
            tone = None
            if raw_content.upper().startswith("SOUND FX:"):
                raw_content = raw_content[9:].strip()
            elif raw_content.upper().startswith("SFX:"):
                raw_content = raw_content[4:].strip()
            formatted_text = f"SOUND FX: {raw_content}"
        else:
            element_type = "dialogue"
            tones = re.findall(r"\(([^)]+)\)", header_raw)
            speaker_raw = re.sub(r"\([^)]*\)", "", header_raw).rstrip(":").strip()
            speaker = speaker_raw if speaker_raw else "SPEAKER"
            tone = ", ".join(t.strip() for t in tones) if tones else None

            d = raw_content.strip()
            if len(d) >= 2 and d[0] in ('"', '“') and d[-1] in ('"', '”'):
                d = d[1:-1].strip()

            if tone:
                formatted_text = f'{speaker} ({tone}): "{d}"'
            else:
                formatted_text = f'{speaker}: "{d}"'

        line_number += 1
        lines.append(Line(
            episode=episode,
            number=line_number,
            text=formatted_text,
            words=count_words(formatted_text),
            ts=start_sec,
            start=start_sec,
            end=end_sec,
            element_type=element_type,
            speaker=speaker,
            tone=tone,
            scene=current_scene,
        ))

        current_header = None
        current_start = None
        current_end = None
        current_content = []

    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        scene_m = SCENE_RE.match(line)
        if scene_m:
            flush()
            current_scene = int(scene_m.group(1))
            continue

        header_m = HEADER_RE.match(line)
        if header_m:
            flush()
            current_header = header_m.group(1).strip()
            continue

        if current_header is not None and current_start is None:
            ts_m = TIMESTAMP_RE.match(line)
            if ts_m:
                current_start = parse_ts(ts_m.group(1))
                current_end = parse_ts(ts_m.group(2))
                continue

        if current_header is not None:
            current_content.append(line)
            continue

    flush()
    return lines


def _parse_legacy_script(text: str) -> list[Line]:
    """Fallback simple line-by-line parser for legacy unstructured scripts."""
    episode, number, lines = 1, 0, []
    for raw in text.splitlines():
        s = raw.strip()
        if not s:
            continue
        m = LEGACY_EPISODE_RE.match(s)
        if m:
            episode, number = int(m.group(1)), 0
            continue
        ts = None
        t = LEGACY_TS_RE.match(s)
        if t:
            ts = float(parse_ts(t.group(1)))
            s = s[t.end():].strip()
        if not s:
            continue
        number += 1
        lines.append(Line(episode=episode, number=number, text=s, words=count_words(s), ts=ts))
    return lines


def parse_script(text: str) -> list[Line]:
    """Parse a script text into Line objects.
    Uses structured parser if '--- SCRIPT START ---' is found,
    otherwise falls back to legacy parser."""
    if SCRIPT_START_RE.search(text):
        return parse_structured_script(text)
    return _parse_legacy_script(text)


def load_script(path: str | Path) -> list[Line]:
    """Load a script file or directory into Line objects."""
    p = Path(path)
    if p.is_dir():
        return load_script_dir(p)
    return parse_script(p.read_text(encoding="utf-8"))


def load_script_dir(directory: str | Path) -> list[Line]:
    """Load all episode files from a directory, sorted by filename, and concatenate Lines."""
    p = Path(directory)
    txt_files = sorted(
        [f for f in p.iterdir() if f.is_file() and f.suffix.lower() == ".txt"],
        key=lambda f: f.name
    )
    all_lines: list[Line] = []
    for f in txt_files:
        all_lines.extend(load_script(f))
    return all_lines


def chunk_lines(lines: list[Line], max_words: int, overlap_lines: int) -> list[Chunk]:
    chunks: list[Chunk] = []
    i = 0
    while i < len(lines):
        start, words = i, 0
        while i < len(lines) and (words + lines[i].words <= max_words or i == start):
            words += lines[i].words
            i += 1
        chunks.append(Chunk(index=len(chunks), lines=lines[start:i]))
        if i < len(lines):
            i = max(start + 1, i - overlap_lines)
    return chunks

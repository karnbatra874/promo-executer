"""Quality control: the four predictable failure modes of a text-only promo tool."""
from __future__ import annotations
import re
from .models import Line, Promo, QCFlag

SPEAKER_RE = re.compile(r"^[A-Z][A-Za-z0-9 .'\-]{0,30}:\s*")
NEW_SPEAKER_RE = re.compile(r"^[A-Z][A-Za-z0-9 .'\-]*(?:\s*\([^)]*\))?:\s*")
PAREN_RE = re.compile(r"\([^)]*\)")
NON_DIALOGUE_PREFIXES = ("CAMERA:", "ACTION:", "SOUND FX:", "SOUND:")


def is_dialogue(text: str) -> bool:
    if text.startswith(NON_DIALOGUE_PREFIXES):
        return False
    return (
        bool(SPEAKER_RE.match(text))
        or bool(NEW_SPEAKER_RE.match(text))
        or bool(re.search(r'["“].*?["”]', text))
        or text.startswith(('"', "“"))
    )


def dialogue_body(text: str) -> str:
    m = re.search(r'["“](.*)["”]', text)
    if m:
        return m.group(1).strip()
    clean = NEW_SPEAKER_RE.sub("", text)
    clean = SPEAKER_RE.sub("", clean)
    clean = PAREN_RE.sub("", clean)
    return clean.strip().strip('"\'“”')


# 4. Pacing miscalculation -------------------------------------------------
def check_word_budget_and_pacing(promo: Promo, settings: dict) -> list[QCFlag]:
    p, flags = settings["promo"], []
    if promo.word_count > p["max_words"]:
        flags.append(QCFlag(code="word_budget", severity="error",
                            message=f"{promo.word_count} words > {p['max_words']} max.",
                            suggestion="Trim filler lines or drop a stitched segment."))
    elif promo.word_count < p["min_words"]:
        flags.append(QCFlag(code="word_budget", severity="warn",
                            message=f"{promo.word_count} words < {p['min_words']} min.",
                            suggestion="Extend the segment or merge with the payoff scene."))
    d = promo.est_duration_sec
    if d > p["max_seconds"]:
        flags.append(QCFlag(code="pacing_too_long", severity="error",
                            message=f"Estimated {d:.0f}s (pauses/crying included) > {p['max_seconds']}s.",
                            suggestion="Cut lines; verify real runtime on footage."))
    elif d < p["min_seconds"]:
        flags.append(QCFlag(code="pacing_too_short", severity="warn",
                            message=f"Estimated {d:.0f}s < {p['min_seconds']}s."))
    return flags


# 2. Pronoun soup ----------------------------------------------------------
def check_pronoun_soup(promo: Promo, index: dict[tuple[int, int], Line],
                       settings: dict, cast: list[re.Pattern]) -> list[QCFlag]:
    q = settings["qc"]
    seg = promo.segments[0]
    opening = [index[(seg.episode, n)] for n in range(seg.start_line, seg.end_line + 1)
               if (seg.episode, n) in index][: q["pronoun_context_lines"]]
    body = " ".join(dialogue_body(l.text) for l in opening)
    window = re.findall(r"[A-Za-z']+", body.lower())[: q["pronoun_window_words"]]
    has_pronoun = any(w in set(q["pronouns"]) for w in window)
    has_name = any(pat.search(body) for pat in cast)
    if has_pronoun and not has_name:
        return [QCFlag(code="pronoun_soup", severity="warn",
                       message="Opens with pronouns (he/she/you/him) and names nobody; a new viewer won't know who is who.",
                       suggestion="Prepend an establishing line, add an on-screen caption, or start earlier.")]
    return []


# 3. False cliffhangers ----------------------------------------------------
def check_false_cliffhanger(promo: Promo, index: dict[tuple[int, int], Line],
                            settings: dict) -> list[QCFlag]:
    last = promo.segments[-1]
    final = index.get((last.episode, last.end_line))
    if not final:
        return []
    if final.text.startswith("CAMERA:") and re.search(r"cut to black|fade", final.text, re.I):
        return []
    hit = any(re.search(p, final.text, re.I) for p in settings["qc"]["false_cliffhanger_patterns"])
    if hit or not is_dialogue(final.text):
        return [QCFlag(code="verify_cliffhanger_in_footage", severity="warn",
                       message="Cliffhanger rests on an action/cut line. The final edit may defuse the tension.",
                       suggestion="Watch the footage; confirm the beat lands, or adjust the end timestamp.")]
    return []


def check_talking_head(promo: Promo, index, settings) -> list[QCFlag]:
    """Flag promos that are almost entirely dialogue with no physical action."""
    all_lines = []
    for seg in promo.segments:
        for n in range(seg.start_line, seg.end_line + 1):
            line = index.get((seg.episode, n))
            if line:
                all_lines.append(line)
    if not all_lines:
        return []
    action_count = sum(1 for l in all_lines if getattr(l, 'element_type', '') in ('action', 'camera'))
    dialogue_count = sum(1 for l in all_lines if getattr(l, 'element_type', '') == 'dialogue')
    if dialogue_count > 0 and action_count / max(len(all_lines), 1) < 0.15:
        return [QCFlag(code='talking_head', severity='warn',
                       message='Promo is almost entirely dialogue with minimal visual action.',
                       suggestion='Look for a version with more physical blocking or dramatic camera work.')]
    return []


def run_rule_qc(promo: Promo, index, settings, cast) -> list[QCFlag]:
    return (check_word_budget_and_pacing(promo, settings)
            + check_pronoun_soup(promo, index, settings, cast)
            + check_false_cliffhanger(promo, index, settings)
            + check_talking_head(promo, index, settings))


# 1. Silent visual hooks ---------------------------------------------------
def scan_visual_hooks(lines: list[Line], promos: list[Promo], settings: dict) -> list[dict]:
    """Short action lines with visual-drama keywords that no promo covers.
    These need a HUMAN to watch the footage: the text carries no 'punch'."""
    q = settings["qc"]
    covered = {k for p in promos for k in map(tuple, p.covered_lines)}
    out = []
    for l in lines:
        elem = getattr(l, "element_type", "")
        if elem in ("camera", "sound_fx"):
            continue
        if l.key in covered or is_dialogue(l.text) or l.words > q["visual_hook_max_words"]:
            continue
        for pat in q["visual_hook_keywords"]:
            if re.search(r"\b" + pat, l.text, re.I):
                out.append({"episode": l.episode, "line": l.number, "text": l.text,
                            "approx_start": round(l.start, 1), "matched": pat,
                            "action": "Watch footage at this point; may be a strong silent hook."})
                break
    return out

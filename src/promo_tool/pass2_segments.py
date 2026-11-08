"""Pass 2: expand anchors into 20-60s promos, map line ranges to timestamps."""
from __future__ import annotations
from .config import load_prompt, render
from .models import Anchor, Chunk, Line, Promo, Segment
from .timemap import fmt_ts


def build_promo(raw: dict, index: dict[tuple[int, int], Line], settings: dict) -> Promo | None:
    segments, texts, covered, eps = [], [], [], []
    words, duration = 0, 0.0
    for s in raw.get("segments", []):
        try:
            ep, a, b = int(s["episode"]), int(s["start_line"]), int(s["end_line"])
        except (KeyError, TypeError, ValueError):
            continue
        if a > b:
            a, b = b, a
        b = min(b, a + 200)  # guard against hallucinated huge ranges
        seg_lines = [index[(ep, n)] for n in range(a, b + 1) if (ep, n) in index]
        if not seg_lines:
            continue
        w = sum(l.words for l in seg_lines)
        segments.append(Segment(
            episode=ep, start_line=a, end_line=b,
            start_timestamp=fmt_ts(seg_lines[0].start),
            end_timestamp=fmt_ts(seg_lines[-1].end),
            word_count=w,
        ))
        texts.append("\n".join(l.text for l in seg_lines))
        covered.extend(l.key for l in seg_lines)
        words += w
        duration += seg_lines[-1].end - seg_lines[0].start
        if ep not in eps:
            eps.append(ep)
    if not segments:
        return None
    return Promo(
        episodes_spanned=eps, segments=segments,
        hook=raw.get("hook", ""), cliffhanger=raw.get("cliffhanger", ""),
        rationale=raw.get("rationale", ""), word_count=words,
        est_duration_sec=round(duration, 1), covered_lines=covered,
        text="\n[CUT]\n".join(texts),
    )


def build_promos(llm, chunk: Chunk, anchors: list[Anchor],
                 index: dict[tuple[int, int], Line], settings: dict) -> list[Promo]:
    p = settings["promo"]
    system = load_prompt("system_promo_producer.txt")
    user = render(
        load_prompt("pass2_segments.txt"),
        MIN_WORDS=p["min_words"], MAX_WORDS=p["max_words"], HOOK_WORDS=p["hook_window_words"],
        ANCHORS="\n".join(f"{a.anchor_id} [{a.type}] E{a.episode}:L{a.line} - {a.description}" for a in anchors),
        CHUNK=chunk.render(),
    )
    data = llm.complete_json(system, user, task="segments")
    promos = [build_promo(r, index, settings) for r in data.get("promos", [])]
    return [p for p in promos if p]

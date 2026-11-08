from __future__ import annotations
import csv
import json
from pathlib import Path
from .config import cast_patterns, load_characters
from .ingest import chunk_lines, load_script, load_script_dir
from .pass1_anchors import find_anchors
from .pass2_segments import build_promos
from .qc import run_rule_qc, scan_visual_hooks
from .ranking import assign_tier, judge_promo
from .timemap import assign_times


def dedupe(promos, threshold=0.5):
    kept = []
    for p in promos:
        a = set(map(tuple, p.covered_lines))
        dup = False
        for k in kept:
            b = set(map(tuple, k.covered_lines))
            if a and b and len(a & b) / min(len(a), len(b)) > threshold:
                dup = True
                break
        if not dup:
            kept.append(p)
    return kept


def run(script_path, out_dir, settings, llm=None, max_chunks=None, log=print):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    script = Path(script_path)
    if script.is_dir():
        lines = load_script_dir(script)
    else:
        lines = load_script(script)
    has_ts = assign_times(lines, settings["timing"])
    index = {l.key: l for l in lines}
    chunks = chunk_lines(lines, settings["chunk"]["max_words"], settings["chunk"]["overlap_lines"])
    if max_chunks:
        chunks = chunks[:max_chunks]
    log(f"{len(lines)} lines, {len({l.episode for l in lines})} episodes, {len(chunks)} chunks "
        f"(script timestamps: {'yes' if has_ts else 'no - using word-count estimate'})")

    promos = []
    if llm is not None:
        total = len(chunks)
        for chunk in chunks:
            try:
                log(f"Processing chunk {chunk.index + 1}/{total}: extracting anchors (rate-limited to stay under 15 RPM)...")
                anchors = find_anchors(llm, chunk)
                log(f"   chunk {chunk.index + 1}/{total}: {len(anchors)} anchors found")
                if anchors:
                    promos += build_promos(llm, chunk, anchors, index, settings)
            except RuntimeError as e:
                log(f"   chunk {chunk.index + 1}/{total} skipped: {e}")

    promos = dedupe(promos)
    for n, p in enumerate(promos, 1):
        p.promo_id = f"P{n}"

    cast = cast_patterns(load_characters())
    for p in promos:
        p.qc_flags = run_rule_qc(p, index, settings, cast)
        try:
            judge_promo(llm, p, settings)
        except RuntimeError as e:
            log(f"{p.promo_id} not scored: {e}")
        p.tier = assign_tier(p, settings)
        p.needs_human_review = bool(p.qc_flags)

    ranked = sorted(promos, key=lambda p: p.total_score or 0, reverse=True)
    visual = scan_visual_hooks(lines, promos, settings)

    (out / "promos_all.json").write_text(
        json.dumps({"promos": [p.model_dump() for p in promos]}, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "promos_ranked.json").write_text(
        json.dumps({"promos": [p.model_dump() for p in ranked]}, indent=2, ensure_ascii=False), encoding="utf-8")

    with open(out / "review_queue.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["promo_id", "tier", "total_score", "est_duration_sec", "word_count", "segments",
                    "qc_flags", "hook", "cliffhanger",
                    "HUMAN_decision (approve/reject/fix)", "HUMAN_verified_start", "HUMAN_verified_end",
                    "HUMAN_actual_seconds", "HUMAN_notes"])
        for p in ranked:
            segs = " | ".join(f"E{s.episode} {s.start_timestamp}-{s.end_timestamp}" for s in p.segments)
            w.writerow([p.promo_id, p.tier, p.total_score, p.est_duration_sec, p.word_count, segs,
                        "; ".join(f.code for f in p.qc_flags), p.hook, p.cliffhanger, "", "", "", "", ""])

    with open(out / "visual_hook_candidates.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["episode", "line", "text", "approx_start", "matched", "action"])
        w.writeheader()
        w.writerows(visual)

    log(f"{len(promos)} promos, {len(visual)} silent-visual-hook candidates -> {out}")
    return ranked, visual

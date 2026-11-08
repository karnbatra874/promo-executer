"""Pass 1: find high-tension anchors (hooks and cliffhangers)."""
from __future__ import annotations
from .config import load_prompt, render
from .models import Anchor, Chunk


def find_anchors(llm, chunk: Chunk) -> list[Anchor]:
    system = load_prompt("system_promo_producer.txt")
    user = render(load_prompt("pass1_anchors.txt"), CHUNK=chunk.render())
    data = llm.complete_json(system, user, task="anchors")
    anchors: list[Anchor] = []
    for i, raw in enumerate(data.get("anchors", []), 1):
        try:
            raw.setdefault("anchor_id", f"A{i}")
            anchors.append(Anchor(**raw))
        except Exception:
            continue
    return anchors

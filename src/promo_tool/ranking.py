"""LLM-as-judge scoring + weighted ranking + tiers."""
from __future__ import annotations
from .config import load_prompt, render
from .models import Promo, QCFlag, Scores


def clamp(x: float) -> float:
    return max(1.0, min(10.0, float(x)))


def weighted_total(s: Scores, weights: dict) -> float:
    return round(s.hook_velocity * weights["hook_velocity"]
                 + s.context_independence * weights["context_independence"]
                 + s.cliffhanger_friction * weights["cliffhanger_friction"], 2)


def assign_tier(promo: Promo, settings: dict) -> str:
    if any(f.severity == "error" for f in promo.qc_flags):
        return "Hold: fix QC errors"
    t = settings["ranking"]["tiers"]
    score = promo.total_score or 0
    if score >= t["tier1"]:
        return "Tier 1: Post Immediately"
    if "tier2" in t and score >= t["tier2"]:
        return "Tier 2: Post After Review"
    return "Tier 3: Low Priority"


def judge_promo(llm, promo: Promo, settings: dict) -> None:
    system = "You are a strict judge of short-form microdrama promos. Output JSON only."
    user = render(load_prompt("judge.txt"), HOOK=promo.hook, CLIFFHANGER=promo.cliffhanger, TEXT=promo.text)
    data = llm.complete_json(system, user, task="judge")
    promo.scores = Scores(
        hook_velocity=clamp(data["hook_velocity"]),
        context_independence=clamp(data["context_independence"]),
        cliffhanger_friction=clamp(data["cliffhanger_friction"]),
    )
    promo.total_score = weighted_total(promo.scores, settings["ranking"]["weights"])
    gaps = data.get("context_gaps") or []
    if gaps:
        promo.qc_flags.append(QCFlag(code="context_gap", severity="warn",
                                     message="Judge says a new viewer would miss: " + "; ".join(map(str, gaps)),
                                     suggestion="Add context line/caption or pick a different start point."))

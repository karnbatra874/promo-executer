from promo_tool.models import Promo, Scores, QCFlag
from promo_tool.ranking import weighted_total, assign_tier


def test_weights_sum(settings):
    w = settings["ranking"]["weights"]
    assert abs(sum(w.values()) - 1.0) < 1e-9
    assert weighted_total(Scores(hook_velocity=10, context_independence=10, cliffhanger_friction=10), w) == 10


def test_formula(settings):
    s = Scores(hook_velocity=10, context_independence=5, cliffhanger_friction=5)
    assert weighted_total(s, settings["ranking"]["weights"]) == 7.0


def test_tier1_and_hold(settings):
    p = Promo(total_score=8.5)
    assert assign_tier(p, settings) == "Tier 1: Post Immediately"
    p.qc_flags = [QCFlag(code="word_budget", severity="error", message="x")]
    assert assign_tier(p, settings).startswith("Hold")

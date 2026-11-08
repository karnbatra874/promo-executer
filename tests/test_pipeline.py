import json
from promo_tool.pipeline import run
from promo_tool.config import ROOT
from conftest import FakeLLM


def test_end_to_end_with_fake_llm(tmp_path, settings):
    ranked, visual = run(ROOT / "data" / "input" / "sample_script.txt", tmp_path, settings,
                         llm=FakeLLM(), log=lambda *_: None)
    assert len(ranked) == 1
    data = json.loads((tmp_path / "promos_ranked.json").read_text())
    p = data["promos"][0]
    assert p["promo_id"] == "P1" and p["total_score"] == 8.8  # 10*.4 + 8*.3 + 8*.3
    assert {"start_timestamp", "end_timestamp"} <= set(p["segments"][0])
    assert (tmp_path / "review_queue.csv").exists()
    assert (tmp_path / "visual_hook_candidates.csv").exists()

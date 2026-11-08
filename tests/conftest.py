import re
import pytest
from promo_tool.config import load_settings, load_characters, cast_patterns, ROOT
from promo_tool.ingest import load_script
from promo_tool.timemap import assign_times


@pytest.fixture(scope="session")
def settings():
    return load_settings()


@pytest.fixture()
def lines(settings):
    ls = load_script(ROOT / "data" / "input" / "sample_script.txt")
    assign_times(ls, settings["timing"])
    return ls


@pytest.fixture()
def index(lines):
    return {l.key: l for l in lines}


@pytest.fixture(scope="session")
def cast():
    return cast_patterns(load_characters())


class FakeLLM:
    """Canned responses so the whole pipeline is testable with no API key."""
    def complete_json(self, system, user, task=""):
        if task == "anchors":
            # Line 7 is VICTORIA's gloating line - a strong hook
            return {"anchors": [{"anchor_id": "A1", "type": "hook", "episode": 1, "line": 7,
                                 "description": "sister reveals she is marrying the groom"}]}
        if task == "segments":
            # Lines 5-14: from altar reveal through cut to black
            return {"promos": [{"segments": [{"episode": 1, "start_line": 5, "end_line": 14}],
                                "hook": "Sister reveals she is marrying the groom",
                                "cliffhanger": "Elena's face hardens into defiance before cut to black",
                                "rationale": "betrayal at the altar"}]}
        # Judge response
        return {"hook_velocity": 9, "context_independence": 9, "cliffhanger_friction": 8,
                "context_gaps": [], "notes": "strong wedding betrayal hook"}

from promo_tool.models import Line
from promo_tool.timemap import count_words, fmt_ts, assign_times, fit_calibration


def test_words_and_format():
    assert count_words("a b  c") == 3
    assert fmt_ts(75) == "01:15"


def test_150_words_is_one_minute(settings):
    timing = {**settings["timing"], "pause_patterns": []}
    l = Line(episode=1, number=1, text=" ".join(["w"] * 150), words=150)
    assign_times([l], timing)
    assert round(l.end - l.start) == 60


def test_explicit_timestamp_resets_clock(settings):
    a = Line(episode=1, number=1, text="x", words=1)
    b = Line(episode=1, number=2, text="y", words=1, ts=100.0)
    assert assign_times([a, b], settings["timing"]) is True
    assert b.start == 100.0


def test_calibration_ratio(settings):
    t = {**settings["timing"]}
    rows = [{"words": 150, "pauses": 0, "actual_seconds": 120}]
    assert abs(fit_calibration(rows, t) - 2.0) < 1e-6

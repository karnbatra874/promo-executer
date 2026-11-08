from promo_tool.models import Promo, Segment
from promo_tool.qc import (check_pronoun_soup, check_false_cliffhanger,
                           check_word_budget_and_pacing, scan_visual_hooks)


def promo(ep, a, b, words=80, dur=30):
    return Promo(segments=[Segment(episode=ep, start_line=a, end_line=b, start_timestamp="00:00",
                                   end_timestamp="00:10", word_count=words)],
                 word_count=words, est_duration_sec=dur)


def test_pronoun_soup_flagged(index, settings, cast):
    flags = check_pronoun_soup(promo(2, 1, 3), index, settings, cast)
    assert flags and flags[0].code == "pronoun_soup"


def test_named_opening_not_flagged(index, settings, cast):
    assert check_pronoun_soup(promo(1, 4, 8), index, settings, cast) == []


def test_false_cliffhanger_on_cut_line(index, settings):
    last = max(n for (e, n) in index if e == 2)
    flags = check_false_cliffhanger(promo(2, 1, last), index, settings)
    assert flags and flags[0].code == "verify_cliffhanger_in_footage"


def test_pacing_and_budget(settings):
    codes = {f.code for f in check_word_budget_and_pacing(promo(1, 1, 2, words=200, dur=90), settings)}
    assert {"word_budget", "pacing_too_long"} <= codes


def test_silent_visual_hook_found(lines, settings):
    hits = scan_visual_hooks(lines, [], settings)
    assert any("looks at the document" in h["text"].lower() for h in hits)

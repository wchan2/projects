import numpy as np
import pytest

from episodes import detect_crash_episodes, label_episodes
from tests.conftest import piecewise


def test_detects_known_drawdowns(known_crashes):
    ep = detect_crash_episodes(known_crashes, crash_threshold=0.25, merge_gap_days=60)
    assert len(ep) == 2                                   # the -19% dip is ignored
    a, b = ep.iloc[0], ep.iloc[1]
    assert a.trough_depth == pytest.approx(-0.40, abs=1e-6)
    assert b.trough_depth == pytest.approx(-0.30, abs=1e-6)
    assert a.peak_date == known_crashes.index[250] and a.trough_date == known_crashes.index[350]
    assert a.days_to_trough == 100
    assert a.recovery_date is not None and not a.open and not b.open
    assert b.peak_date == known_crashes.index[800] and b.trough_date == known_crashes.index[880]


def test_threshold_controls_selection(known_crashes):
    assert len(detect_crash_episodes(known_crashes, crash_threshold=0.15)) == 3
    assert len(detect_crash_episodes(known_crashes, crash_threshold=0.45)) == 0


def test_open_episode_closed_at_end_date():
    s = piecewise([(0, 100), (100, 50), (200, 60)])
    ep = detect_crash_episodes(s, crash_threshold=0.25)
    assert len(ep) == 1 and ep.iloc[0].open and np.isnan(ep.iloc[0].days_to_recovery)
    cut = detect_crash_episodes(s, crash_threshold=0.25, end_date=s.index[60])
    assert len(cut) == 1 and cut.iloc[0].trough_depth > -0.5


def test_merge_gap():
    # two -40% crashes; recovery to a new high between them lasts ~10 days
    s = piecewise([(0, 100), (50, 60), (100, 101), (110, 101), (130, 60), (250, 105)])
    assert len(detect_crash_episodes(s, merge_gap_days=60)) == 1     # < 60 days apart: merged
    assert len(detect_crash_episodes(s, merge_gap_days=5)) == 2


def test_override_windows(known_crashes):
    ov = [{"start": known_crashes.index[250], "end": known_crashes.index[500]}]
    ep = detect_crash_episodes(known_crashes, override=ov)
    assert len(ep) == 1 and ep.iloc[0].trough_date == known_crashes.index[350]


def test_vix_peak_recorded(noisy_market):
    ep = detect_crash_episodes(noisy_market.signal, noisy_market.vix, 0.25)
    assert (ep.vix_peak > 30).all()


def test_labels_are_causal(noisy_market):
    s = noisy_market.signal
    full = label_episodes(s, 0.25, 60)
    for cut in (300, 500, 700, 900, 1100):
        part = label_episodes(s.iloc[:cut], 0.25, 60)
        assert part.equals(full.iloc[:cut])

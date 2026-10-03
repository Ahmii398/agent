"""Prefix-consistency tests: a leak of future bars makes these fail."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from trade_agent.features.pipeline import compute_features
from trade_agent.features.swings import swing_points


def _synth(n: int = 240, start: datetime | None = None) -> pd.DataFrame:
    start = start or datetime(2024, 1, 1, tzinfo=UTC)
    rng = np.random.default_rng(42)
    walk = np.cumsum(rng.normal(0, 1, size=n)) + 100
    ts = [start + timedelta(hours=i) for i in range(n)]
    high = walk + rng.uniform(0.2, 1.5, size=n)
    low = walk - rng.uniform(0.2, 1.5, size=n)
    return pd.DataFrame(
        {
            "ts": ts,
            "open": walk,
            "high": np.maximum(high, walk),
            "low": np.minimum(low, walk),
            "close": walk + rng.normal(0, 0.2, size=n),
            "volume": rng.uniform(10, 100, size=n),
        }
    )


COMPARE_COLS = [
    "close",
    "atr",
    "swing_high",
    "swing_low",
    "hh",
    "ll",
    "bos_up",
    "choch_down",
    "bull_engulf",
    "hammer",
    "fvg_bull",
    "sweep_high",
    "efficiency_ratio",
    "session",
    "structure_bias",
]


def test_prefix_matches_full_series() -> None:
    """Features on df[:k] must equal the first k rows of features(df)."""
    df = _synth(300)
    full = compute_features(df)
    for k in (80, 150, 240):
        part = compute_features(df.iloc[:k].reset_index(drop=True))
        cols = [c for c in COMPARE_COLS if c in full.columns]
        left = full.iloc[:k][cols].reset_index(drop=True)
        right = part[cols].reset_index(drop=True)
        pd.testing.assert_frame_equal(left, right, check_dtype=False)


def test_injected_future_shift_is_detected() -> None:
    """A deliberately leaky feature (shift -1) must fail the prefix test."""
    df = _synth(120)
    leaked = df.copy()
    leaked["future_close"] = leaked["close"].shift(-1)

    def _leaky(frame: pd.DataFrame) -> pd.DataFrame:
        out = frame.copy()
        out["future_close"] = out["close"].shift(-1)
        return out

    full = _leaky(df)
    part = _leaky(df.iloc[:80].reset_index(drop=True))
    # Last usable leaked value differs: full[:80] has close[80] in row 79;
    # truncated series has NaN in row 79.
    with pytest.raises(AssertionError):
        pd.testing.assert_series_equal(
            full.iloc[:80]["future_close"].reset_index(drop=True),
            part["future_close"].reset_index(drop=True),
        )


def test_swing_not_marked_until_confirmation() -> None:
    """A lone spike is not a swing high on its own bar."""
    ts0 = datetime(2024, 1, 1, tzinfo=UTC)
    prices = [10, 11, 12, 20, 12, 11, 10]  # spike at index 3
    df = pd.DataFrame(
        {
            "ts": [ts0 + timedelta(hours=i) for i in range(7)],
            "open": prices,
            "high": [p + 0.1 for p in prices],
            "low": [p - 0.1 for p in prices],
            "close": prices,
            "volume": [1] * 7,
        }
    )
    sw = swing_points(df, left=2)
    # Pivot at index 3 confirms at index 5.
    assert not bool(sw.loc[3, "swing_high"])
    assert bool(sw.loc[5, "swing_high"])
    assert sw.loc[5, "swing_high_price"] == pytest.approx(20.1)


def test_htf_4h_not_visible_until_it_closes() -> None:
    from trade_agent.features.mtf import closed_htf_as_of

    start = datetime(2024, 1, 1, 8, 0, tzinfo=UTC)
    htf = pd.DataFrame(
        {
            "ts": [start],
            "open": [100.0],
            "high": [110.0],
            "low": [90.0],
            "close": [105.0],
            "volume": [1.0],
        }
    )
    visible_early = closed_htf_as_of(htf, "4h", start + timedelta(hours=1))
    visible_late = closed_htf_as_of(htf, "4h", start + timedelta(hours=4))
    assert visible_early.empty
    assert len(visible_late) == 1

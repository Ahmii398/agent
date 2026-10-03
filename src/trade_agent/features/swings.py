"""Confirmed swing highs/lows. A swing is emitted only after ``left`` bars close."""

from __future__ import annotations

import pandas as pd


def swing_points(df: pd.DataFrame, left: int = 2) -> pd.DataFrame:
    """Mark Williams-style fractals at the *confirmation* bar.

    At bar ``t`` the candidate pivot is ``t - left``. It is a swing high iff
    its high is strictly greater than every other high in ``[t - 2*left, t]``.
    That window never looks past ``t``.
    """
    if left < 1:
        raise ValueError("left must be >= 1")
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    pivot_h = high.shift(left)
    pivot_l = low.shift(left)
    is_sh = pivot_h.notna()
    is_sl = pivot_l.notna()
    for offset in range(0, 2 * left + 1):
        if offset == left:
            continue
        other_h = high.shift(2 * left - offset)
        other_l = low.shift(2 * left - offset)
        is_sh &= pivot_h > other_h
        is_sl &= pivot_l < other_l

    sh_price = pivot_h.where(is_sh)
    sl_price = pivot_l.where(is_sl)
    sh_pivot = df["ts"].shift(left).where(is_sh)
    sl_pivot = df["ts"].shift(left).where(is_sl)
    return pd.DataFrame(
        {
            "swing_high": is_sh.fillna(False).astype(bool),
            "swing_low": is_sl.fillna(False).astype(bool),
            "swing_high_price": sh_price,
            "swing_low_price": sl_price,
            "swing_high_pivot_ts": sh_pivot,
            "swing_low_pivot_ts": sl_pivot,
        },
        index=df.index,
    )


def last_confirmed_swings(swings: pd.DataFrame) -> pd.DataFrame:
    """Forward-fill the latest confirmed swing prices (no future values)."""
    return pd.DataFrame(
        {
            "last_swing_high": swings["swing_high_price"].ffill(),
            "last_swing_low": swings["swing_low_price"].ffill(),
        },
        index=swings.index,
    )

"""Single- and two-bar candle patterns. Only ``t`` and ``t-1`` are used."""

from __future__ import annotations

import pandas as pd


def candle_patterns(df: pd.DataFrame) -> pd.DataFrame:
    """Engulfing, pin bar (hammer/shooting), inside bar, doji."""
    o = df["open"].astype(float)
    h = df["high"].astype(float)
    low = df["low"].astype(float)
    c = df["close"].astype(float)
    body = (c - o).abs()
    rng = (h - low).replace(0, pd.NA)
    upper = h - pd.concat([o, c], axis=1).max(axis=1)
    lower = pd.concat([o, c], axis=1).min(axis=1) - low
    bull = c > o
    bear = c < o
    prev_o, prev_c = o.shift(1), c.shift(1)
    prev_h, prev_l = h.shift(1), low.shift(1)
    prev_bull = prev_c > prev_o
    prev_bear = prev_c < prev_o

    bull_engulf = bull & prev_bear & (c >= prev_o) & (o <= prev_c)
    bear_engulf = bear & prev_bull & (c <= prev_o) & (o >= prev_c)
    hammer = (lower >= 2 * body) & (upper <= body) & (body / rng <= 0.4)
    shoot = (upper >= 2 * body) & (lower <= body) & (body / rng <= 0.4)
    inside = (h <= prev_h) & (low >= prev_l)
    doji = body / rng <= 0.1

    return pd.DataFrame(
        {
            "bull_engulf": bull_engulf.fillna(False),
            "bear_engulf": bear_engulf.fillna(False),
            "hammer": hammer.fillna(False),
            "shooting_star": shoot.fillna(False),
            "inside_bar": inside.fillna(False),
            "doji": doji.fillna(False),
        },
        index=df.index,
    )

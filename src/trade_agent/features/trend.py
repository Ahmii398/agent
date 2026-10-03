"""Causal trend strength: efficiency ratio and a short/long EMA gap."""

from __future__ import annotations

import pandas as pd


def trend_strength(
    df: pd.DataFrame, er_period: int = 20, fast: int = 20, slow: int = 50
) -> pd.DataFrame:
    """Kaufman efficiency ratio plus normalized EMA spread.

    Both use only closes at or before the current bar.
    """
    close = df["close"].astype(float)
    change = (close - close.shift(er_period)).abs()
    path = close.diff().abs().rolling(er_period, min_periods=er_period).sum()
    efficiency = change / path.replace(0, pd.NA)
    ema_fast = close.ewm(span=fast, adjust=False, min_periods=fast).mean()
    ema_slow = close.ewm(span=slow, adjust=False, min_periods=slow).mean()
    spread = (ema_fast - ema_slow) / close.replace(0, pd.NA)
    direction = (spread > 0).astype(int) - (spread < 0).astype(int)
    return pd.DataFrame(
        {
            "efficiency_ratio": efficiency.astype(float),
            "ema_fast": ema_fast,
            "ema_slow": ema_slow,
            "ema_spread": spread.astype(float),
            "trend_dir": direction,
        },
        index=df.index,
    )

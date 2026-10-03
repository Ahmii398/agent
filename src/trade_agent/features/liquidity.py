"""Liquidity sweeps: wick through a confirmed swing, close back inside."""

from __future__ import annotations

import pandas as pd


def liquidity_sweeps(df: pd.DataFrame, swings: pd.DataFrame) -> pd.DataFrame:
    """Sweep high: high > last swing high and close < last swing high.

    Last swing prices are forward-filled from *already confirmed* swings,
    so a sweep cannot use a swing that has not printed yet.
    """
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)
    last_sh = swings["last_swing_high"]
    last_sl = swings["last_swing_low"]
    sweep_high = (high > last_sh) & (close < last_sh)
    sweep_low = (low < last_sl) & (close > last_sl)
    return pd.DataFrame(
        {
            "sweep_high": sweep_high.fillna(False),
            "sweep_low": sweep_low.fillna(False),
        },
        index=df.index,
    )

"""Support / resistance zones from confirmed swing prices (causal)."""

from __future__ import annotations

import numpy as np
import pandas as pd


def sr_zones(
    df: pd.DataFrame, swings: pd.DataFrame, atr: pd.Series, width_atr: float = 0.25
) -> pd.DataFrame:
    """Nearest resistance (above) and support (below) from swings known at ``t``.

    Zone half-width is ``width_atr * ATR[t]``. Distance is in price, not future.
    """
    close = df["close"].astype(float)
    res = np.full(len(df), np.nan)
    sup = np.full(len(df), np.nan)
    highs: list[float] = []
    lows: list[float] = []
    high_vals = swings["swing_high_price"].to_numpy()
    low_vals = swings["swing_low_price"].to_numpy()
    close_vals = close.to_numpy()
    for i in range(len(df)):
        if swings["swing_high"].iloc[i]:
            highs.append(float(high_vals[i]))
        if swings["swing_low"].iloc[i]:
            lows.append(float(low_vals[i]))
        px = close_vals[i]
        above = [h for h in highs if h > px]
        below = [lo for lo in lows if lo < px]
        if above:
            res[i] = min(above)
        if below:
            sup[i] = max(below)
    half = atr.astype(float) * width_atr
    return pd.DataFrame(
        {
            "resistance": res,
            "support": sup,
            "dist_to_res_atr": (res - close) / atr.replace(0, np.nan),
            "dist_to_sup_atr": (close - sup) / atr.replace(0, np.nan),
            "at_resistance": (close - res).abs() <= half,
            "at_support": (close - sup).abs() <= half,
        },
        index=df.index,
    )

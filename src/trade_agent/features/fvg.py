"""Fair value gaps from a 3-candle pattern ending at the current bar."""

from __future__ import annotations

import pandas as pd


def fair_value_gaps(df: pd.DataFrame) -> pd.DataFrame:
    """Bullish FVG: ``low[t] > high[t-2]``. Bearish FVG: ``high[t] < low[t-2]``.

    Candle ``t-1`` is the displacement bar. All three prints are known at ``t``.
    """
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    high_2 = high.shift(2)
    low_2 = low.shift(2)
    bull = low > high_2
    bear = high < low_2
    gap_low = high_2.where(bull)
    gap_high = low.where(bull)
    bear_gap_low = high.where(bear)
    bear_gap_high = low_2.where(bear)
    return pd.DataFrame(
        {
            "fvg_bull": bull.fillna(False),
            "fvg_bear": bear.fillna(False),
            "fvg_bull_low": gap_low,
            "fvg_bull_high": gap_high,
            "fvg_bear_low": bear_gap_low,
            "fvg_bear_high": bear_gap_high,
        },
        index=df.index,
    )

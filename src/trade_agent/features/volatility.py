"""ATR and a three-state volatility regime. Rolling windows use only past+now."""

from __future__ import annotations

import pandas as pd


def true_range(df: pd.DataFrame) -> pd.Series:
    """Wilder true range. Previous close is ``shift(1)`` — no look-ahead."""
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    prev_close = df["close"].astype(float).shift(1)
    a = high - low
    b = (high - prev_close).abs()
    c = (low - prev_close).abs()
    return pd.concat([a, b, c], axis=1).max(axis=1)


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Wilder ATR via EWM with ``adjust=False`` (recursive, causal)."""
    if period < 1:
        raise ValueError("period must be >= 1")
    tr = true_range(df)
    return tr.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


def volatility_regime(df: pd.DataFrame, atr_period: int = 14, lookback: int = 100) -> pd.DataFrame:
    """Classify ATR vs its own causal median: low / mid / high.

    Thresholds: below 0.75× median → low, above 1.5× → high.
    """
    series = atr(df, period=atr_period)
    # Rolling median includes the current bar (known at close).
    med = series.rolling(lookback, min_periods=max(20, lookback // 5)).median()
    ratio = series / med
    regime = pd.Series("unknown", index=df.index)
    regime = regime.mask(ratio < 0.75, "low").mask(ratio > 1.5, "high")
    regime = regime.mask(ratio.between(0.75, 1.5, inclusive="both"), "mid")
    regime = regime.where(ratio.notna(), "unknown")
    return pd.DataFrame({"atr": series, "atr_ratio": ratio, "vol_regime": regime}, index=df.index)

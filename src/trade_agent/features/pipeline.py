"""Build the full causal feature frame for one symbol/timeframe."""

from __future__ import annotations

import pandas as pd

from trade_agent.features.fvg import fair_value_gaps
from trade_agent.features.liquidity import liquidity_sweeps
from trade_agent.features.mtf import htf_alignment
from trade_agent.features.patterns import candle_patterns
from trade_agent.features.sessions import session_flags
from trade_agent.features.structure import market_structure
from trade_agent.features.trend import trend_strength
from trade_agent.features.volatility import atr, volatility_regime
from trade_agent.features.zones import sr_zones


def compute_features(
    df: pd.DataFrame,
    *,
    swing_left: int = 2,
    atr_period: int = 14,
    htf: pd.DataFrame | None = None,
    htf_timeframe: str | None = None,
) -> pd.DataFrame:
    """Return ``df`` plus numeric/boolean features. No column uses future bars.

    Args:
        df: Canonical OHLCV (``ts, open, high, low, close, volume``).
        swing_left: Fractal radius. Confirmation lag is ``left`` bars.
        atr_period: Wilder ATR length.
        htf: Optional higher-timeframe OHLCV for alignment.
        htf_timeframe: Required when ``htf`` is provided (e.g. ``4h``).
    """
    if df.empty:
        return df.copy()
    base = df.reset_index(drop=True).copy()
    vol = volatility_regime(base, atr_period=atr_period)
    atr_s = atr(base, period=atr_period)
    struct = market_structure(base, left=swing_left)
    zones = sr_zones(base, struct, atr_s)
    pats = candle_patterns(base)
    liq = liquidity_sweeps(base, struct)
    gaps = fair_value_gaps(base)
    trend = trend_strength(base)
    sess = session_flags(base)
    parts = [base, struct, vol, zones, pats, liq, gaps, trend, sess]
    if htf is not None and htf_timeframe:
        parts.append(htf_alignment(base, htf, htf_timeframe))
    out = pd.concat(parts, axis=1)
    # Concat can duplicate ``ts`` if a part already has it; keep first.
    return out.loc[:, ~out.columns.duplicated()]

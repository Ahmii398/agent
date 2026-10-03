"""Higher-timeframe bias using only HTF bars that have *closed* at ``as_of``."""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from trade_agent.data.candles import drop_unclosed
from trade_agent.data.timeframes import timeframe_delta
from trade_agent.features.trend import trend_strength


def htf_alignment(
    ltf: pd.DataFrame,
    htf: pd.DataFrame,
    htf_timeframe: str,
) -> pd.DataFrame:
    """Map each LTF bar to the last *closed* HTF trend direction.

    A 4h bar opened at 08:00 is invisible to a 1h bar at 09:00 (it closes at
    12:00). ``merge_asof`` backward on HTF close-time enforces that.
    """
    empty = pd.DataFrame(
        {"htf_trend_dir": pd.Series(0, index=ltf.index, dtype=int), "htf_aligned": False},
        index=ltf.index,
    )
    if htf.empty or ltf.empty:
        return empty
    htf_feat = trend_strength(htf)
    right = pd.DataFrame(
        {
            "htf_close_at": pd.to_datetime(htf["ts"], utc=True)
            + pd.Timedelta(timeframe_delta(htf_timeframe)),
            "htf_trend_dir": htf_feat["trend_dir"].astype(int),
        }
    ).sort_values("htf_close_at")
    left = pd.DataFrame(
        {"ts": pd.to_datetime(ltf["ts"], utc=True), "idx": ltf.index}
    ).sort_values("ts")
    merged = pd.merge_asof(
        left,
        right,
        left_on="ts",
        right_on="htf_close_at",
        direction="backward",
    )
    merged = merged.set_index("idx").reindex(ltf.index)
    htf_dir = merged["htf_trend_dir"].fillna(0).astype(int)
    ltf_dir = trend_strength(ltf)["trend_dir"].astype(int)
    aligned = (htf_dir != 0) & (htf_dir == ltf_dir)
    return pd.DataFrame({"htf_trend_dir": htf_dir, "htf_aligned": aligned}, index=ltf.index)


def closed_htf_as_of(htf: pd.DataFrame, timeframe: str, as_of: datetime) -> pd.DataFrame:
    """Public helper: HTF rows whose close is ``<= as_of``."""
    return drop_unclosed(htf, timeframe, as_of=as_of)

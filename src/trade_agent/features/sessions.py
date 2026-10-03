"""Session flags from the candle *open* time in UTC.

Default windows (FX/crypto convention, UTC):
Asia 00:00–08:00, London 07:00–16:00, New York 12:00–21:00.
Overlaps are allowed; each flag is independent.
"""

from __future__ import annotations

import pandas as pd

ASIA = (0, 8)
LONDON = (7, 16)
NEW_YORK = (12, 21)


def _in_window(hours: pd.Series, start: int, end: int) -> pd.Series:
    if start <= end:
        return (hours >= start) & (hours < end)
    return (hours >= start) | (hours < end)


def session_flags(df: pd.DataFrame) -> pd.DataFrame:
    """Boolean Asia / London / NY plus a primary session label."""
    hours = pd.to_datetime(df["ts"], utc=True).dt.hour
    asia = _in_window(hours, *ASIA)
    london = _in_window(hours, *LONDON)
    ny = _in_window(hours, *NEW_YORK)
    primary = pd.Series("off", index=df.index)
    # Priority NY > London > Asia when overlapping (later session dominates).
    primary = primary.mask(asia, "asia").mask(london, "london").mask(ny, "ny")
    return pd.DataFrame(
        {
            "session_asia": asia.to_numpy(),
            "session_london": london.to_numpy(),
            "session_ny": ny.to_numpy(),
            "session": primary,
        },
        index=df.index,
    )

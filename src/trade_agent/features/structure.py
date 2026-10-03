"""Market structure: HH/HL/LH/LL plus BOS / CHoCH from confirmed swings."""

from __future__ import annotations

import numpy as np
import pandas as pd

from trade_agent.features.swings import last_confirmed_swings, swing_points


def market_structure(df: pd.DataFrame, left: int = 2) -> pd.DataFrame:
    """Label structure events at the bar they become knowable.

    A new confirmed swing high is HH if it is above the previous confirmed
    swing high, LH otherwise. BOS up: close crosses the last swing high after
    a sequence of HH/HL (bullish). CHoCH: close crosses against the prevailing
    swing structure.
    """
    swings = swing_points(df, left=left)
    last = last_confirmed_swings(swings)
    close = df["close"].astype(float)

    # Previous confirmed swing of the same type (shifted so we don't compare to self).
    prev_sh = swings["swing_high_price"].replace({np.nan: np.nan}).ffill().shift(1)
    prev_sl = swings["swing_low_price"].replace({np.nan: np.nan}).ffill().shift(1)

    hh = swings["swing_high"] & (swings["swing_high_price"] > prev_sh)
    lh = swings["swing_high"] & (swings["swing_high_price"] < prev_sh)
    hl = swings["swing_low"] & (swings["swing_low_price"] > prev_sl)
    ll = swings["swing_low"] & (swings["swing_low_price"] < prev_sl)

    # Structure bias: last *event* that printed. 1 bull, -1 bear, 0 unknown.
    event = pd.Series(0, index=df.index, dtype=int)
    event = event.mask(hh | hl, 1).mask(lh | ll, -1)
    bias = event.replace(0, np.nan).ffill().fillna(0).astype(int)

    bos_up = (close > last["last_swing_high"]) & (bias.shift(1) == 1)
    bos_down = (close < last["last_swing_low"]) & (bias.shift(1) == -1)
    choch_up = (close > last["last_swing_high"]) & (bias.shift(1) == -1)
    choch_down = (close < last["last_swing_low"]) & (bias.shift(1) == 1)

    # Fire only on the first bar of a cross (edge), not every bar above.
    bos_up = bos_up & bos_up.shift(1).ne(True)
    bos_down = bos_down & bos_down.shift(1).ne(True)
    choch_up = choch_up & choch_up.shift(1).ne(True)
    choch_down = choch_down & choch_down.shift(1).ne(True)

    out = swings.copy()
    out["last_swing_high"] = last["last_swing_high"]
    out["last_swing_low"] = last["last_swing_low"]
    out["hh"] = hh.fillna(False)
    out["hl"] = hl.fillna(False)
    out["lh"] = lh.fillna(False)
    out["ll"] = ll.fillna(False)
    out["structure_bias"] = bias
    out["bos_up"] = bos_up.fillna(False)
    out["bos_down"] = bos_down.fillna(False)
    out["choch_up"] = choch_up.fillna(False)
    out["choch_down"] = choch_down.fillna(False)
    return out

"""Print a feature summary for stored candles."""

from __future__ import annotations

from trade_agent.core.config import Settings
from trade_agent.data.candles import CandleStore
from trade_agent.features.pipeline import compute_features


def cmd_features(settings: Settings, args) -> int:
    candles = CandleStore(settings.data_dir)
    df = candles.load("binance", args.symbol, args.timeframe)
    if df.empty:
        print(f"no candles for {args.symbol} {args.timeframe}")
        return 2
    htf = candles.load("binance", args.symbol, args.htf)
    feat = compute_features(df, htf=htf if not htf.empty else None, htf_timeframe=args.htf)
    print(
        f"symbol={args.symbol} tf={args.timeframe} rows={len(feat)} cols={len(feat.columns)}"
    )
    bool_cols = [
        c
        for c in feat.columns
        if feat[c].dtype == bool
        or str(feat[c].dtype) == "boolean"
    ]
    for col in bool_cols:
        print(f"  count {col}={int(feat[col].sum())}")
    if "vol_regime" in feat.columns:
        print("  vol_regime", feat["vol_regime"].value_counts().to_dict())
    if "session" in feat.columns:
        print("  session", feat["session"].value_counts().to_dict())
    if "structure_bias" in feat.columns:
        print("  structure_bias", feat["structure_bias"].value_counts().to_dict())
    tail = feat.tail(args.sample)
    show = [
        "ts",
        "close",
        "atr",
        "vol_regime",
        "session",
        "structure_bias",
        "htf_trend_dir",
        "htf_aligned",
        "sweep_high",
        "fvg_bull",
        "bull_engulf",
    ]
    show = [c for c in show if c in tail.columns]
    print(tail[show].to_string(index=False))
    return 0

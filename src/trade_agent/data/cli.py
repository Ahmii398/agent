"""CLI helpers for download / inspect / one-shot stream."""

from __future__ import annotations

from datetime import timedelta

from trade_agent.core.config import Settings
from trade_agent.core.timeutil import from_iso, utcnow
from trade_agent.data.candles import CandleStore
from trade_agent.data.ccxt_provider import CcxtOHLCVProvider
from trade_agent.data.downloader import HistoricalDownloader
from trade_agent.data.gaps import quality_report
from trade_agent.data.streamer import poll_closed_candles
from trade_agent.db.store import Store


def cmd_download(settings: Settings, args) -> int:
    start, end = _window(args)
    provider = CcxtOHLCVProvider("binance")
    candles = CandleStore(settings.data_dir)
    with Store(settings.db_path) as store:
        store.migrate()
        downloader = HistoricalDownloader(provider, candles, store)
        for symbol in args.symbol or ["BTC/USDT", "ETH/USDT"]:
            df = downloader.download(symbol, args.timeframe, start, end)
            _print_report(provider.name, symbol, args.timeframe, df)
    return 0


def cmd_inspect(settings: Settings, args) -> int:
    candles = CandleStore(settings.data_dir)
    df = candles.load("binance", args.symbol, args.timeframe)
    _print_report("binance", args.symbol, args.timeframe, df, sample=min(args.sample, 10))
    return 0


def cmd_stream(settings: Settings, args) -> int:
    provider = CcxtOHLCVProvider("binance")
    print(
        f"streaming exchange={provider.name} symbol={args.symbol} "
        f"tf={args.timeframe} max={args.max}"
    )
    for bar in poll_closed_candles(
        provider,
        args.symbol,
        args.timeframe,
        poll_seconds=args.poll,
        max_yields=args.max,
    ):
        print(
            f"closed ts={bar.ts.isoformat()} o={bar.open} h={bar.high} "
            f"l={bar.low} c={bar.close} v={bar.volume}"
        )
    return 0


def cmd_verify_data(settings: Settings, args) -> int:
    """Download real Binance history and print quality evidence."""
    end = utcnow()
    start = end - timedelta(days=args.days)
    provider = CcxtOHLCVProvider("binance")
    candles = CandleStore(settings.data_dir)
    with Store(settings.db_path) as store:
        store.migrate()
        downloader = HistoricalDownloader(provider, candles, store)
        ok = True
        symbols = args.symbol or ["BTC/USDT", "ETH/USDT"]
        for symbol in symbols:
            df = downloader.download(symbol, args.timeframe, start, end)
            report = quality_report(df, args.timeframe)
            _print_report(provider.name, symbol, args.timeframe, df)
            if not report.ok:
                print(f"QUALITY_ISSUE symbol={symbol} {report}")
                ok = False
            if report.gaps:
                print(f"GAPS symbol={symbol} count={len(report.gaps)}")
                for g in report.gaps[:10]:
                    print(f"  gap start={g.start.isoformat()} missing={g.missing_bars}")
                repaired = downloader.repair_gaps(symbol, args.timeframe)
                after = quality_report(repaired, args.timeframe)
                print(f"after_repair gaps={len(after.gaps)} rows={after.rows}")
        # Second download of the same window must not need new REST pages.
        print("re-download (must be cache-only)...")
        df2 = downloader.download(symbols[0], args.timeframe, start, end)
        print(f"cache_replay_rows={len(df2)}")
    return 0 if ok else 2


def _window(args) -> tuple:
    if args.start and args.end:
        return from_iso(args.start), from_iso(args.end)
    end = utcnow()
    start = end - timedelta(days=args.days)
    return start, end


def _print_report(exchange: str, symbol: str, timeframe: str, df, sample: int = 3) -> None:
    report = quality_report(df, timeframe)
    print(
        f"exchange={exchange} symbol={symbol} tf={timeframe} rows={report.rows} "
        f"first={report.first_ts} last={report.last_ts} gaps={len(report.gaps)} "
        f"ohlc_violations={report.ohlc_violations} future_bars={report.future_bars} "
        f"ok={report.ok}"
    )
    if df.empty:
        return
    show = df.head(sample)
    for row in show.itertuples(index=False):
        print(
            f"  sample ts={row.ts} o={row.open} h={row.high} "
            f"l={row.low} c={row.close} v={row.volume}"
        )
    if len(df) > sample:
        last = df.iloc[-1]
        print(
            f"  last    ts={last.ts} o={last.open} h={last.high} "
            f"l={last.low} c={last.close} v={last.volume}"
        )

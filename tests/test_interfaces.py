from __future__ import annotations

from datetime import UTC, datetime

import pytest

from trade_agent.interfaces.data_provider import DataProvider, OHLCVBar
from trade_agent.interfaces.llm_client import LLMTask


class _StubProvider(DataProvider):
    name = "stub"

    def fetch_ohlcv(self, symbol, timeframe, start, end):
        return [
            OHLCVBar(
                ts=datetime(2024, 1, 1, tzinfo=UTC),
                open=1,
                high=2,
                low=0.5,
                close=1.5,
                volume=10,
            )
        ]

    def detect_gaps(self, bars, timeframe):
        return []


def test_data_provider_contract() -> None:
    p = _StubProvider()
    bars = p.fetch_ohlcv("BTC/USDT", "1h", datetime(2024, 1, 1, tzinfo=UTC), datetime(2024, 1, 2, tzinfo=UTC))
    assert bars[0].ts.tzinfo is not None
    with pytest.raises(NotImplementedError):
        next(p.stream_ohlcv("BTC/USDT", "1h"))


def test_llm_task_values() -> None:
    assert LLMTask.WEB_EXTRACT.value == "web_extract"
    assert LLMTask.REASONING.value == "reasoning"

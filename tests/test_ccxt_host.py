from trade_agent.data.ccxt_provider import BINANCE_PUBLIC_REST, CcxtOHLCVProvider


def test_binance_uses_vision_host_not_geo_blocked_api() -> None:
    provider = CcxtOHLCVProvider("binance")
    assert provider._exchange.urls["api"]["public"] == BINANCE_PUBLIC_REST
    assert "binance.vision" in BINANCE_PUBLIC_REST
    assert "api.binance.com" not in BINANCE_PUBLIC_REST

from __future__ import annotations

from pathlib import Path

from trade_agent.approval.flags import LIVE_TRADING_ENABLED
from trade_agent.core.config import load_settings


def test_default_config_loads(tmp_path: Path) -> None:
    settings = load_settings(data_dir=tmp_path, load_env=False)
    assert settings.app.timezone == "UTC"
    assert settings.app.random_seed == 42
    assert "BTC/USDT" in settings.universe.crypto
    assert settings.llm.monthly_budget_usd > 0
    assert settings.llm.tasks["web_extract"].allow_tools is False
    assert settings.llm.tasks["web_extract"].json_only is True
    assert (tmp_path / "candles").is_dir()
    assert (tmp_path / "cache").is_dir()


def test_yaml_cannot_enable_live_trading(tmp_path: Path) -> None:
    cfg = tmp_path / "evil.yaml"
    cfg.write_text("live_trading:\n  enabled: true\n", encoding="utf-8")
    settings = load_settings(cfg, data_dir=tmp_path / "var", load_env=False)
    # YAML may claim live is on; the compile-time flag that brokers consult stays off.
    assert settings.live_trading.enabled is True
    assert LIVE_TRADING_ENABLED is False
    # The live path consults the source constant, not YAML:
    from trade_agent.interfaces.broker import Broker, Order, Side
    from trade_agent.core.errors import LiveTradingDisabled

    class FakeLive(Broker):
        name = "fake-live"
        is_paper = False

        def submit(self, order: Order):
            self.assert_live_allowed()
            raise AssertionError("must not reach")

        def cancel(self, order_id: str) -> None:
            return None

        def positions(self):
            return []

        def equity(self) -> float:
            return 0.0

    broker = FakeLive()
    try:
        broker.submit(Order(symbol="BTC/USDT", side=Side.BUY, qty=1))
        raise AssertionError("live submit must be disabled")
    except LiveTradingDisabled:
        pass

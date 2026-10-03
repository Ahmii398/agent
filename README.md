# trade-agent

Autonomous research-and-trading agent for crypto and forex. Paper first. Live
trading is compiled off and cannot be enabled from YAML.

## Phase 1 (this commit)

Scaffold only: config, logging, SQLite schema, KeyPool, LLM monthly budget,
abstract `DataProvider` / `Broker` / `LLMClient`, hardcoded risk limits.

Later phases fill `data/`, `features/`, `research/`, the trader brain, validation,
paper trading, and the dashboard.

## Setup

```bash
cp .env.example .env   # keys stay here; never commit .env
uv sync --extra dev
uv run python -m trade_agent init-db
uv run python -m trade_agent status
uv run python -m trade_agent verify
uv run python -m trade_agent verify-data --days 60 --timeframe 1h
uv run python -m trade_agent inspect --symbol BTC/USDT --timeframe 1h
uv run python -m trade_agent research --asset BTC --asset ETH
uv run python -m trade_agent research-inspect
uv run pytest
uv run ruff check src tests
```

Phase 1 and Phase 2 use **no API keys**. Phase 2 pulls Binance public spot
candles via ccxt. **Real-data note:** `api.binance.com` returns HTTP 451
(geo-restricted) from some hosts; the provider uses
`https://data-api.binance.vision/api/v3` (same Binance klines) and logs that
choice.

Phase 6 collects structured research (FRED, Finnhub, NewsAPI, Twelve Data,
GoldAPI, Fear & Greed, CoinGecko, CFTC, Bitget public, RSS) plus a tiny
robots-respecting Wikipedia allowlist. Keys live in `.env` only; logs use
`key_index`. Point-in-time queries require `published_at < as_of` and drop
unknown publish times. Fetched text cannot change risk limits or place orders.
Bitget public market data does not send the API key; authenticated Bitget
trading needs `BITGET_API_SECRET` and `BITGET_PASSPHRASE` (not configured).

If a later phase needs a key the agent stops and names the exact `.env`
variable.

## Layout

```
config/default.yaml          # non-secret settings; risk numbers are display-only
src/trade_agent/
  core/                      # config, logging, KeyPool, UTC time, untrusted-text wrap
  db/                        # SQLite schema + Store
  interfaces/                # DataProvider, Broker, LLMClient
  llm/                       # budget + Ollama / Anthropic / dummy
  risk/                      # HARD-CODED limits; YAML cannot weaken them
  approval/                  # LIVE_TRADING_ENABLED = False
  data/ features/ research/ reasoning/ memory/
  strategies/ backtest/ validation/ agent/ paper/ dashboard/ vision/
var/                         # local DB, Parquet candles, HTTP cache (gitignored)
```

## Storage

- **Candles:** Parquet at `var/candles/{exchange}/{SYMBOL}/{timeframe}.parquet`
- **Everything else:** SQLite at `var/trade_agent.db`
- All timestamps are UTC. Naive datetimes are rejected.

## Safety

- Fetched web text is wrapped in `UNTRUSTED_EXTERNAL_DATA` blocks before any LLM.
- Web-extract LLM calls have no tools and must return schema-valid JSON.
- RiskGuard binds limits at import. There is no setter.
- Live broker `submit()` raises `LiveTradingDisabled` while the flag is False.

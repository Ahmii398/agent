"""Local extract for untrusted web text. No tools, no config/order side effects."""

from __future__ import annotations

import re
from typing import Any

from trade_agent.core.security import (
    WEB_EXTRACT_REQUIRED_KEYS,
    assert_json_schema,
    wrap_untrusted,
)

_POS = {
    "surge",
    "rally",
    "bull",
    "gain",
    "beat",
    "strong",
    "record",
    "optimistic",
    "hawkish",
}
_NEG = {
    "crash",
    "plunge",
    "bear",
    "loss",
    "miss",
    "weak",
    "fear",
    "dovish",
    "collapse",
    "hack",
}
_ASSET_ALIASES = {
    "btc": "BTC",
    "bitcoin": "BTC",
    "eth": "ETH",
    "ethereum": "ETH",
    "xau": "XAU",
    "gold": "XAU",
    "dxy": "DXY",
    "dollar": "DXY",
    "spy": "SPX",
    "s&p": "SPX",
}


def extract_untrusted(text: str, *, source: str, url: str | None = None) -> dict[str, Any]:
    """Return schema-valid {summary, sentiment, tags} from untrusted text.

    The payload is wrapped in UNTRUSTED markers first. Instruction-like lines
    are dropped from the summary. This function has no access to config, risk
    limits, or order placement.
    """
    wrapped = wrap_untrusted(text, source=source, url=url)
    cleaned = _strip_instructions(_visible_payload(wrapped))
    words = re.findall(r"[a-z0-9&]+", cleaned.lower())
    pos = sum(1 for w in words if w in _POS)
    neg = sum(1 for w in words if w in _NEG)
    denom = pos + neg
    sentiment = 0.0 if denom == 0 else (pos - neg) / denom
    tags = sorted({_ASSET_ALIASES[w] for w in words if w in _ASSET_ALIASES})
    summary = " ".join(cleaned.split())[:400]
    parsed = {"summary": summary or "(empty)", "sentiment": float(sentiment), "tags": tags}
    return assert_json_schema(parsed, WEB_EXTRACT_REQUIRED_KEYS)


def _visible_payload(wrapped: str) -> str:
    start = wrapped.find(">>>")
    end = wrapped.rfind("<<<END_UNTRUSTED_EXTERNAL_DATA>>>")
    if start == -1 or end == -1:
        return wrapped
    return wrapped[start + 3 : end]


_INSTRUCTION_RE = re.compile(
    r"(ignore previous|you are now|set live_trading|buy now|place the order|"
    r"override risk|api_key\s*=)",
    re.I,
)


def _strip_instructions(text: str) -> str:
    keep = [line for line in text.splitlines() if not _INSTRUCTION_RE.search(line)]
    return "\n".join(keep)

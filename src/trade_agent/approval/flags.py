"""Feature flags that YAML / the agent loop are not allowed to flip.

``LIVE_TRADING_ENABLED`` stays False through Phase 8. Enabling it requires a
source change *and* a row in ``live_approvals``. There is no setter.
"""

LIVE_TRADING_ENABLED = False

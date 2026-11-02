import pytest

import main


@pytest.fixture(autouse=True)
def _no_rate_limit(monkeypatch):
    """Tests run many requests from one client, so the limiter is off unless a test turns it on."""
    monkeypatch.setattr(main.rate_limit, "per_minute", 0)
    main.rate_limit._hits.clear()

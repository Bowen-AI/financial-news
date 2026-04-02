"""
Integration tests for the FastAPI application.

Requires: DATABASE_URL, REDIS_URL, API_KEY env vars (set in CI via GitHub Actions services).
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

# Skip entire module if integration env is not set
pytestmark = pytest.mark.skipif(
    "postgresql" not in os.environ.get("DATABASE_URL", ""),
    reason="Requires Postgres DATABASE_URL for integration tests",
)

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
async def api_client():
    """Return an async test client for the FastAPI app (function-scoped to avoid loop issues)."""
    from apps.api.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client


@pytest.fixture
def api_key():
    return os.environ.get("API_KEY", "test-api-key")


# ── Health ────────────────────────────────────────────────────────────────────


class TestHealthEndpoint:
    async def test_health_returns_ok(self, api_client: AsyncClient):
        resp = await api_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "timestamp" in data

    async def test_health_no_auth_required(self, api_client: AsyncClient):
        """Health check must not require authentication."""
        resp = await api_client.get("/health")
        assert resp.status_code == 200


# ── Auth ──────────────────────────────────────────────────────────────────────


class TestAuthProtection:
    async def test_status_requires_auth(self, api_client: AsyncClient):
        resp = await api_client.get("/status")
        # 401 or 403 both indicate the request was correctly rejected
        assert resp.status_code in (401, 403)

    async def test_status_with_valid_key(self, api_client: AsyncClient, api_key: str):
        resp = await api_client.get("/status", headers={"X-API-Key": api_key})
        assert resp.status_code == 200

    async def test_invalid_key_rejected(self, api_client: AsyncClient):
        resp = await api_client.get(
            "/status", headers={"X-API-Key": "invalid-key-xyz"}
        )
        assert resp.status_code in (401, 403)

    async def test_portfolio_requires_auth(self, api_client: AsyncClient):
        resp = await api_client.get("/portfolio")
        assert resp.status_code in (401, 403)


# ── Status ────────────────────────────────────────────────────────────────────


class TestStatusEndpoint:
    async def test_status_shape(self, api_client: AsyncClient, api_key: str):
        resp = await api_client.get("/status", headers={"X-API-Key": api_key})
        assert resp.status_code == 200
        data = resp.json()
        assert "llm_backend" in data
        assert "alert_threshold" in data
        assert "status" in data

    async def test_status_has_model_info(self, api_client: AsyncClient, api_key: str):
        resp = await api_client.get("/status", headers={"X-API-Key": api_key})
        data = resp.json()
        assert data["llm_backend"] in ("ollama", "vllm", "llamacpp")


# ── Portfolio ─────────────────────────────────────────────────────────────────


class TestPortfolioEndpoints:
    async def test_portfolio_has_positions_and_ledger(self, api_client: AsyncClient, api_key: str):
        resp = await api_client.get(
            "/portfolio", headers={"X-API-Key": api_key}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "positions" in data
        assert "ledger" in data

    async def test_portfolio_action_buy(self, api_client: AsyncClient, api_key: str):
        resp = await api_client.post(
            "/portfolio/action",
            headers={"X-API-Key": api_key},
            json={"raw_text": "BUY 10 AAPL @ 180.00"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "recorded"
        assert data["parsed"]["action"] == "BUY"
        assert data["parsed"]["instrument"] == "AAPL"
        assert data["parsed"]["quantity"] == 10.0
        assert data["parsed"]["price"] == 180.0

    async def test_portfolio_action_sell(self, api_client: AsyncClient, api_key: str):
        resp = await api_client.post(
            "/portfolio/action",
            headers={"X-API-Key": api_key},
            json={"raw_text": "SELL 5 AAPL @ 200.00"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "recorded"
        assert data["parsed"]["action"] == "SELL"

    async def test_portfolio_action_note(self, api_client: AsyncClient, api_key: str):
        resp = await api_client.post(
            "/portfolio/action",
            headers={"X-API-Key": api_key},
            json={"raw_text": "NOTE: watching NVDA earnings"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "recorded"

    async def test_portfolio_shows_buy_after_recording(
        self, api_client: AsyncClient, api_key: str
    ):
        # Record a trade first
        await api_client.post(
            "/portfolio/action",
            headers={"X-API-Key": api_key},
            json={"raw_text": "BUY 100 MSFT @ 400.00"},
        )
        # Check it appears in ledger
        resp = await api_client.get(
            "/portfolio", headers={"X-API-Key": api_key}
        )
        data = resp.json()
        instruments = [t["instrument"] for t in data["ledger"]]
        assert "MSFT" in instruments

    async def test_unrecognized_action_returns_unrecognized_status(
        self, api_client: AsyncClient, api_key: str
    ):
        resp = await api_client.post(
            "/portfolio/action",
            headers={"X-API-Key": api_key},
            json={"raw_text": "What is the market outlook?"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "unrecognized"


# ── Ingest ────────────────────────────────────────────────────────────────────


class TestIngestEndpoint:
    async def test_ingest_run_queues_task(self, api_client: AsyncClient, api_key: str):
        """Verify the endpoint queues a Celery task without requiring a running worker."""
        # Tasks are imported inside the route handler, so patch at the source module
        with patch("apps.worker.tasks.ingest_task") as mock_task:
            mock_result = MagicMock()
            mock_result.id = "mock-task-id-123"
            mock_task.delay.return_value = mock_result

            resp = await api_client.post(
                "/ingest/run", headers={"X-API-Key": api_key}
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "queued"
        assert "task_id" in data


# ── Briefing ──────────────────────────────────────────────────────────────────


class TestBriefingEndpoint:
    async def test_briefing_send_queues_task(self, api_client: AsyncClient, api_key: str):
        with patch("apps.worker.tasks.briefing_task") as mock_task:
            mock_result = MagicMock()
            mock_result.id = "mock-briefing-task"
            mock_task.delay.return_value = mock_result

            resp = await api_client.post(
                "/briefing/send", headers={"X-API-Key": api_key}
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "queued"


# ── Alerts ────────────────────────────────────────────────────────────────────


class TestAlertEndpoint:
    async def test_alerts_run_queues_task(self, api_client: AsyncClient, api_key: str):
        with patch("apps.worker.tasks.alert_task") as mock_task:
            mock_result = MagicMock()
            mock_result.id = "mock-alert-task"
            mock_task.delay.return_value = mock_result

            resp = await api_client.post(
                "/alerts/run", headers={"X-API-Key": api_key}
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "queued"


# ── Backtest ──────────────────────────────────────────────────────────────────


class TestBacktestEndpoint:
    async def test_backtest_unknown_alert_404(
        self, api_client: AsyncClient, api_key: str
    ):
        resp = await api_client.post(
            "/backtest/run",
            headers={"X-API-Key": api_key},
            json={
                "alert_id": "00000000-0000-0000-0000-000000000000",
                "action": "BUY",
                "holding_days": 5,
            },
        )
        assert resp.status_code == 404

    async def test_backtest_rejects_invalid_alert_id_format(
        self, api_client: AsyncClient, api_key: str
    ):
        resp = await api_client.post(
            "/backtest/run",
            headers={"X-API-Key": api_key},
            json={"alert_id": "not-a-uuid"},
        )
        assert resp.status_code in (404, 422)


# ── Dashboard ─────────────────────────────────────────────────────────────────


class TestDashboard:
    async def test_dashboard_requires_auth(self, api_client: AsyncClient):
        resp = await api_client.get("/dashboard")
        assert resp.status_code in (401, 403)

    async def test_dashboard_returns_html(self, api_client: AsyncClient, api_key: str):
        resp = await api_client.get(
            "/dashboard", headers={"X-API-Key": api_key}
        )
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "Financial News" in resp.text

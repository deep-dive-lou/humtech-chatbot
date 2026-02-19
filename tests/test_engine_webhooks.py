from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.engine.webhooks import router


class _AcquireCtx:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakePool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        return _AcquireCtx(self._conn)


class FakeConn:
    def __init__(self, tenant_id: str = "11111111-1111-1111-1111-111111111111"):
        self.tenant_id = tenant_id
        self.settings = {
            "engine": {
                "webhooks": {
                    "ghl": {
                        "secret": "good-secret",
                        "location_id": "loc-123",
                    }
                }
            }
        }

    async def fetchrow(self, sql, *args):
        if "FROM core.tenants" in sql:
            tenant_hint = args[0]
            if tenant_hint == self.tenant_id:
                return {"tenant_id": self.tenant_id, "settings": self.settings}
            return None
        return None

    async def fetch(self, sql, *args):
        if "FROM core.tenants" in sql:
            return [{"tenant_id": self.tenant_id, "settings": self.settings}]
        return []


class EngineWebhookEndpointTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(router)
        self.client = TestClient(app)
        self.conn = FakeConn()
        self.base_payload = {
            "tenant_id": self.conn.tenant_id,
            "locationId": "loc-123",
            "opportunityId": "opp-1",
            "contactId": "contact-1",
            "stage": "Proposal Sent",
            "type": "OpportunityStageUpdate",
            "eventId": "evt-source-1",
            "occurredAt": "2026-02-15T10:00:00Z",
            "monetaryValue": 1500,
        }

    def test_happy_path_creates_or_updates_lead_and_inserts_event(self):
        with (
            patch("app.engine.webhooks.get_pool", new=AsyncMock(return_value=FakePool(self.conn))),
            patch("app.engine.webhooks.resolve_stage_mapping", new=AsyncMock(return_value="proposal_sent")),
            patch("app.engine.webhooks.upsert_lead", new=AsyncMock(return_value="lead-1")) as upsert_lead,
            patch("app.engine.webhooks.write_lead_event", new=AsyncMock(return_value="event-1")) as write_event,
        ):
            resp = self.client.post("/engine/webhooks/ghl/good-secret", json=self.base_payload)

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["lead_id"], "lead-1")
        self.assertEqual(body["event_id"], "event-1")
        self.assertFalse(body["duplicate"])
        upsert_lead.assert_awaited_once()
        write_event.assert_awaited_once()

    def test_duplicate_webhook_does_not_create_duplicate_event(self):
        with (
            patch("app.engine.webhooks.get_pool", new=AsyncMock(return_value=FakePool(self.conn))),
            patch("app.engine.webhooks.resolve_stage_mapping", new=AsyncMock(return_value="proposal_sent")),
            patch("app.engine.webhooks.upsert_lead", new=AsyncMock(return_value="lead-1")),
            patch("app.engine.webhooks.write_lead_event", new=AsyncMock(return_value=None)),
        ):
            resp = self.client.post("/engine/webhooks/ghl/good-secret", json=self.base_payload)

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["ok"])
        self.assertTrue(body["duplicate"])
        self.assertIsNone(body["event_id"])

    def test_unknown_mapping_persists_with_null_canonical_stage_and_logs_warning(self):
        with (
            patch("app.engine.webhooks.get_pool", new=AsyncMock(return_value=FakePool(self.conn))),
            patch("app.engine.webhooks.resolve_stage_mapping", new=AsyncMock(return_value=None)),
            patch("app.engine.webhooks.upsert_lead", new=AsyncMock(return_value="lead-1")),
            patch("app.engine.webhooks.write_lead_event", new=AsyncMock(return_value="event-1")),
            self.assertLogs("app.engine.webhooks", level="WARNING") as logs,
        ):
            resp = self.client.post("/engine/webhooks/ghl/good-secret", json=self.base_payload)

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIsNone(body["canonical_stage"])
        self.assertTrue(any("Missing stage mapping" in line for line in logs.output))

    def test_invalid_secret_is_rejected(self):
        with (
            patch("app.engine.webhooks.get_pool", new=AsyncMock(return_value=FakePool(self.conn))),
            patch("app.engine.webhooks.resolve_stage_mapping", new=AsyncMock(return_value="proposal_sent")),
            patch("app.engine.webhooks.upsert_lead", new=AsyncMock(return_value="lead-1")),
            patch("app.engine.webhooks.write_lead_event", new=AsyncMock(return_value="event-1")),
        ):
            resp = self.client.post("/engine/webhooks/ghl/bad-secret", json=self.base_payload)

        self.assertEqual(resp.status_code, 401)

    def test_location_mismatch_is_rejected(self):
        payload = dict(self.base_payload)
        payload["locationId"] = "different-location"
        with (
            patch("app.engine.webhooks.get_pool", new=AsyncMock(return_value=FakePool(self.conn))),
            patch("app.engine.webhooks.resolve_stage_mapping", new=AsyncMock(return_value="proposal_sent")),
            patch("app.engine.webhooks.upsert_lead", new=AsyncMock(return_value="lead-1")),
            patch("app.engine.webhooks.write_lead_event", new=AsyncMock(return_value="event-1")),
        ):
            resp = self.client.post("/engine/webhooks/ghl/good-secret", json=payload)

        self.assertEqual(resp.status_code, 401)

    def test_endpoint_reachable_under_provider_path(self):
        resp = self.client.post("/engine/webhooks/ghl", json=self.base_payload)
        self.assertNotEqual(resp.status_code, 404)


if __name__ == "__main__":
    unittest.main()


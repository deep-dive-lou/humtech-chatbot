from __future__ import annotations

import unittest

from app.engine.providers.ghl_webhook_parser import parse_ghl_webhook


class GHLWebhookParserTests(unittest.TestCase):
    def test_parser_extracts_normalized_contract_fields(self):
        payload = {
            "tenant_id": "11111111-1111-1111-1111-111111111111",
            "locationId": "loc-123",
            "opportunityId": "opp-1",
            "contactId": "contact-1",
            "stage": "Proposal Sent",
            "type": "OpportunityStageUpdate",
            "eventId": "evt-123",
            "occurredAt": "2026-02-15T10:00:00Z",
            "monetaryValue": "2500.50",
        }
        result = parse_ghl_webhook(payload)

        self.assertEqual(result.provider, "ghl")
        self.assertEqual(result.tenant_id, payload["tenant_id"])
        self.assertEqual(result.lead_external_id, "opp-1")
        self.assertEqual(result.contact_external_id, "contact-1")
        self.assertEqual(result.raw_stage, "Proposal Sent")
        self.assertEqual(result.event_type, "stage_changed")
        self.assertEqual(result.source_event_id, "evt-123")
        self.assertEqual(result.lead_value, 2500.5)
        self.assertEqual(result.location_id, "loc-123")


if __name__ == "__main__":
    unittest.main()


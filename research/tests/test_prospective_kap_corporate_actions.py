from pathlib import Path
import sys
import unittest

RESEARCH = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RESEARCH))
import prospective_kap_corporate_actions as kap
import phase_b_corporate_action_readiness as readiness


class ProspectiveKapCorporateActionTests(unittest.TestCase):
    def test_bimas_bist_cash_dividend_detail(self):
        detail = (RESEARCH / "cache" / "kap_corporate_action_probe" / "1663015.html").read_bytes()
        event = kap.parse_cash_dividend(detail, "BIMAS.IS")
        self.assertEqual(event["event_type"], "CASH_DIVIDEND")
        self.assertEqual(event["ex_date"], "2026-09-16")
        self.assertEqual(event["gross_amount"], 2.5)
        self.assertEqual(event["net_amount"], 2.125)
        self.assertEqual(event["currency"], "TRY")

    def test_non_cash_detail_is_rejected(self):
        detail = (RESEARCH / "cache" / "kap_corporate_action_probe" / "1663262.html").read_bytes()
        self.assertIsNone(kap.parse_cash_dividend(detail, "BIMAS.IS"))

    def test_pit_status_rule_is_fail_closed_after_ex_date(self):
        self.assertEqual(kap.pit_status("2026-09-19T10:38:29+00:00", "2026-09-16"), "RETROSPECTIVE_ONLY")
        self.assertEqual(kap.pit_status("2026-09-15T15:00:00+00:00", "2026-09-16"), "PROSPECTIVE_CAPTURED")

    def test_missing_official_event_fails_closed(self):
        result = readiness.evaluate(
            [{"ticker": "BIMAS.IS", "date": "2026-09-16", "dividends": 2.5}],
            {"schema": kap.SCHEMA, "events": []},
        )
        self.assertFalse(result["authoritative_reconciliation"])
        self.assertFalse(result["phase_b_source_readiness"])
        self.assertEqual(result["rows"][0]["status"], "MISSING_OFFICIAL_EVENT")


if __name__ == "__main__":
    unittest.main()

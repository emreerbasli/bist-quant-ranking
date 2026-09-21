import json
import unittest

import pandas as pd

from research import exp_data_005 as d5


class TestExpData005(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        d5.build_overlay()

    def test_candidate_detector_sanity(self):
        events, counts = d5.candidate_scan()
        self.assertEqual(counts["ratio_jump_without_event"], 0)
        self.assertIn(("KONTR.IS", "2025-12-01"), set(zip(events.symbol, events.date)))

    def test_known_five_still_detected_and_controlled(self):
        events, _ = d5.candidate_scan()
        old = json.loads(d5.CONTRACT_004.read_text(encoding="utf-8"))["events"]
        keys = set(zip(events.symbol, events.date))
        for event in old:
            self.assertIn((event["symbol"], event["provider_adjusted_date"]), keys)
            view = d5.load_view(event["symbol"])
            date = pd.Timestamp(event["provider_adjusted_date"])
            self.assertEqual(view.loc[date, "price_quality"], "UNRESOLVED")

    def test_new_event_quarantine_and_no_future_rewrite(self):
        base = pd.read_parquet(d5.BASE_VIEW / d5.file_name("KONTR.IS"))
        view = d5.load_view("KONTR.IS")
        early = view.loc["2025-12-01":"2025-12-08"]
        self.assertTrue(early["price_quality"].eq("UNRESOLVED").all())
        self.assertTrue(early["trading_eligible"].eq(False).all())
        self.assertEqual(view.loc[pd.Timestamp("2025-12-09"), "price_quality"], "RECONSTRUCTED")
        pd.testing.assert_series_equal(base.loc[:"2025-11-28", "research_close"], view.loc[:"2025-11-28", "research_close"])

    def test_unresolved_never_silently_verified(self):
        for path in d5.BASE_VIEW.glob("*.parquet"):
            symbol = d5.symbol_from_path(path)
            view = d5.load_view(symbol)
            unresolved = view["price_quality"].eq("UNRESOLVED")
            self.assertFalse(view.loc[unresolved, "trading_eligible"].any())

    def test_horizon_count_consistency(self):
        symbols = [d5.symbol_from_path(p) for p in d5.BASE_VIEW.glob("*.parquet") if "IDX_" not in p.stem]
        out = d5.horizon_coverage(symbols)
        self.assertTrue((out.candidate_observations == out.usable_observations + out.excluded_observations).all())
        self.assertEqual(set(out.horizon_sessions), set(d5.HORIZONS))

    def test_eligibility_policy_consistency(self):
        view = d5.load_view("SASA.IS")
        bad = view["trading_status"].str.startswith("UNRESOLVED")
        self.assertFalse(view.loc[bad, "trading_eligible"].any())


if __name__ == "__main__":
    unittest.main()

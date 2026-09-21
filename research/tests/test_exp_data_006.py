import unittest

import pandas as pd

from research import exp_data_006 as d6


class FundamentalIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.df = d6.load_fundamentals()
        cls.prov = d6.provenance(cls.df)
        cls.capital, cls.signal = d6.capital_audit(cls.df)

    def test_pit_classification_consistency(self):
        self.assertEqual(len(self.df), 2646)
        self.assertTrue(self.prov.pit_quality.eq("APPROXIMATE_FIXED_LAG").all())
        self.assertTrue(self.prov.announcement_timestamp.isna().all())

    def test_future_and_restatement_leakage_sanity(self):
        vintage = d6.vintage_audit(self.df)
        self.assertTrue(vintage.latest_overwrite_risk.all())
        self.assertTrue(vintage.retained_vintage.eq("UNKNOWN_CURRENT_SNAPSHOT").all())
        poc = d6.poc_results(self.df)
        exact = poc[poc.accepted_exact_recovery].iloc[0]
        self.assertNotEqual(exact.local_net_profit_try, exact.official_net_profit_ytd_thousand_try * 1000)

    def test_period_semantics_sanity(self):
        sem = d6.period_semantics(self.df).set_index("field")
        self.assertEqual(sem.loc["net_kar", "stored_semantics"], "YTD_CUMULATIVE_3_6_9_12_MONTH")
        self.assertFalse(bool(sem.loc["net_kar", "single_quarter_available"]))
        self.assertEqual(sem.loc["ozkaynaklar", "stored_semantics"], "POINT_IN_TIME_PERIOD_END")

    def test_historical_capital_fallback_detection(self):
        self.assertEqual(len(self.capital), 190)
        self.assertFalse(self.capital.future_last_capital_fallback.any())
        self.assertTrue(self.capital.market_cap_source.eq("MISSING").all())
        self.assertTrue((pd.to_datetime(self.capital.fallback_capital_source_date) > pd.to_datetime(self.capital.availability_proxy_date)).all())

    def test_signal_date_valuation_consistency(self):
        self.assertFalse(self.signal.valuation_recomputed_on_each_signal_date.any())
        self.assertFalse(self.signal.signal_date_valuation_consistent.any())

    def test_missing_is_not_verified_or_zero(self):
        status = d6.field_status(self.df, self.capital)
        self.assertFalse(status[status.status == "MISSING"].status.eq("VERIFIED").any())
        self.assertGreater(len(d6.missing_zero_scan()), 0)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

RESEARCH = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RESEARCH))

import exp_tgt_001 as tgt
from temporal_validation import build_label_interval, purged_training_mask


class TargetHorizonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads(tgt.CONTRACT_PATH.read_text(encoding="utf-8"))
        cls.calendar, cls.symbols, cls.views, _ = tgt.load_inputs(cls.contract)
        cls.features, cls.data, cls.coverage = tgt.build_dataset(cls.calendar, cls.symbols, cls.views)

    def test_dynamic_20_40_60_labels(self):
        signal = self.calendar[300]
        for h in (20, 40, 60):
            interval = build_label_interval(self.calendar, signal, h)
            self.assertEqual(self.calendar.get_loc(interval.label_end) - self.calendar.get_loc(interval.label_start), h)

    def test_no_label_leakage_and_purge_consistency(self):
        boundary = pd.Timestamp("2023-01-01")
        for h in (20, 40, 60):
            rows = tgt.train_rows(self.data, h, boundary)
            self.assertTrue((rows.label_end < boundary).all())
        short = build_label_interval(self.calendar, self.calendar[300], 20)
        long = build_label_interval(self.calendar, self.calendar[300], 60)
        boundary = self.calendar[342]
        self.assertEqual(purged_training_mask([short, long], boundary), [True, False])

    def test_inner_outer_separation(self):
        for fold in self.contract["outer_folds"]:
            outer_year = pd.Timestamp(fold["test_start"]).year
            self.assertTrue(all(y < outer_year for y in fold["inner_validation_years"]))
            self.assertEqual(len(fold["inner_validation_years"]), 2)

    def test_same_feature_and_model_across_horizons(self):
        self.assertEqual(self.contract["features"], [
            {"name": "mom_12_1", "formula": "last_valid_close[-21] / last_valid_close[-252] - 1"},
            {"name": "mom_63", "formula": "last_valid_close / last_valid_close[-64] - 1"},
            {"name": "vol_63", "formula": "std of the last 63 valid close-to-close returns"},
        ])
        self.assertTrue(self.contract["model"]["same_configuration_across_horizons"])

    def test_no_macro_or_unsafe_fundamental_fields(self):
        names = {x["name"] for x in self.contract["features"]}
        forbidden = set(self.contract["forbidden_fields"])
        self.assertTrue(names.isdisjoint(forbidden))
        self.assertEqual(self.contract["data_scope"]["fundamental"], "EXCLUDED_FROM_THIS_EXPERIMENT")
        self.assertEqual(self.contract["data_scope"]["macro_including_usdtry"], "EXCLUDED")

    def test_no_future_eligibility_or_feature_change(self):
        view = self.views[self.symbols[0]].copy(deep=True)
        pos = 500
        before = tgt.feature_row(view, pos)
        view.iloc[pos + 1:, view.columns.get_loc("research_close")] = 10**9
        view.iloc[pos + 1:, view.columns.get_loc("trading_eligible")] = False
        after = tgt.feature_row(view, pos)
        self.assertEqual(before, after)
        self.assertTrue(self.contract["eligibility"]["future_label_availability_not_used_to_form_universe"])

    def test_reproducible_ridge_control(self):
        rows = tgt.train_rows(self.data, 20, "2023-01-01")
        m1, m2 = tgt.fit_ridge(rows), tgt.fit_ridge(rows)
        np.testing.assert_allclose(tgt.predict(m1, rows.head(50)), tgt.predict(m2, rows.head(50)), rtol=0, atol=0)

    def test_outputs_are_nested_and_daily(self):
        selection = pd.read_csv(tgt.RESULTS / "EXP-TGT-001_inner_selections.csv")
        outer = pd.read_csv(tgt.RESULTS / "EXP-TGT-001_outer_metrics.csv")
        nav = pd.read_csv(tgt.RESULTS / "EXP-TGT-001_selected_outer_daily_nav.csv")
        self.assertEqual(len(selection), 4)
        self.assertEqual(set(selection.selected_horizon), {20, 40, 60})
        self.assertEqual(len(outer), 4 * 3 * 4)
        self.assertGreater(len(nav), 0)
        self.assertIn("nav", nav.columns)

    def test_benchmark_not_in_investable_universe(self):
        self.assertEqual(len(self.symbols), 88)
        self.assertNotIn("XU100.IS", self.symbols)


if __name__ == "__main__":
    unittest.main()

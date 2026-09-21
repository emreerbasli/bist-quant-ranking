from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

import pandas as pd

RESEARCH = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RESEARCH))

from temporal_validation import build_label_interval, purged_training_mask


class TemporalValidationTests(unittest.TestCase):
    def test_dynamic_horizons_count_exact_sessions(self):
        cal = pd.bdate_range("2020-01-01", periods=100)
        for horizon in (20, 40, 60):
            obs = build_label_interval(cal, cal[5], horizon)
            self.assertEqual(obs.entry_date, cal[6])
            self.assertEqual(obs.label_start, cal[6])
            self.assertEqual(obs.label_end, cal[6 + horizon])
            self.assertEqual(cal.get_loc(obs.label_end) - cal.get_loc(obs.label_start), horizon)

    def test_purge_uses_each_observations_actual_label_end(self):
        cal = pd.bdate_range("2020-01-01", periods=150)
        short = build_label_interval(cal, cal[5], 20)
        long = build_label_interval(cal, cal[5], 60)
        self.assertEqual(purged_training_mask([short, long], cal[40]), [True, False])

    def test_contract_separates_horizon_holding_and_rebalance(self):
        contract = json.loads((RESEARCH / "contracts" / "research_contract.json").read_text(encoding="utf-8"))
        self.assertEqual(contract["prediction_horizons_sessions"], [20, 40, 60])
        self.assertEqual(contract["holding_period"]["minimum_sessions"], 60)
        self.assertEqual(contract["rebalance_frequency"]["research_control_sessions"], 60)
        self.assertTrue(contract["holding_period"]["is_separate_from_prediction_horizon"])
        self.assertFalse(contract["prediction_horizon_20_is_rotation"])
        self.assertFalse(contract["outer_feedback_for_selection"])


if __name__ == "__main__":
    unittest.main()

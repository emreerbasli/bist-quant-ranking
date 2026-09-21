import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from research.exp_data_003 import (
    CONTRACT,
    entitlement_factor,
    event_inventory,
    ohlc_inventory,
    zero_volume_inventory,
)


class EventReconciliationTests(unittest.TestCase):
    def test_bonus_issue_factor(self):
        self.assertAlmostEqual(entitlement_factor(846.0, "BONUS_ISSUE", 10.0, 0.0), 1.0 / 11.0)

    def test_rights_issue_factor(self):
        expected = (60.0 + 3.0) / (60.0 * 4.0)
        self.assertAlmostEqual(entitlement_factor(60.0, "RIGHTS_ISSUE", 3.0, 1.0), expected)

    def test_unsupported_action_rejected(self):
        with self.assertRaises(ValueError):
            entitlement_factor(10.0, "UNKNOWN", 1.0, 0.0)

    def test_all_five_extremes_are_reconciled_data_errors(self):
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        events = event_inventory(contract)
        self.assertEqual(len(events), 5)
        self.assertEqual(set(events["classification"]), {"CONFIRMED_DATA_ERROR"})
        self.assertTrue(events["reconciled_economic_return"].abs().lt(0.05).all())
        self.assertTrue(events["local_split_field"].eq(0).all())

    def test_ohlc_classifications_are_stable(self):
        found = ohlc_inventory().set_index("symbol")["classification"].to_dict()
        self.assertEqual(found, {"MTRKS.IS": "DATA_ERROR", "MIATK.IS": "ROUNDING_ONLY"})

    def test_zero_volume_population_is_fully_accounted(self):
        detail, _ = zero_volume_inventory()
        self.assertEqual(len(detail), 1728)
        self.assertTrue(detail["ohlc_present"].all())
        self.assertEqual(detail["category"].isna().sum(), 0)


if __name__ == "__main__":
    unittest.main()

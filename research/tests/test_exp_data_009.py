import json
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT / "research"))
import exp_data_009

class MacroAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.s = exp_data_009.run()
    def test_no_future_publication_is_accepted(self):
        self.assertEqual(self.s["future_dated_cpi_months"], [])
        self.assertEqual(self.s["macro_gate"], "EXCLUDE")
    def test_fabricated_fallback_is_excluded(self): self.assertGreater(self.s["fallback_expression_occurrences"], 0)
    def test_static_rate_is_not_current(self): self.assertEqual(self.s["series_readiness"]["policy_rate"], "NO")
    def test_fx_alignment_measured(self): self.assertEqual(len(self.s["fx"]["bist_missing_fx_dates"]), 3)
    def test_real_rate_timing_is_not_safe(self): self.assertEqual(self.s["series_readiness"]["real_rate"], "NO")
    def test_no_production_mutation_claimed(self): self.assertEqual(self.s["production_changes"], 0)

if __name__ == "__main__": unittest.main()

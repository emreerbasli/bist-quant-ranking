from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from research.exp_data_008 import (
    BatchStop,
    available_from,
    batch_plan,
    cache_read,
    cache_write,
    canonical_universe,
    derive_single_quarters,
    local_comparison,
    parse_member_inventory,
)

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = json.loads((ROOT / "research" / "contracts" / "exp_data_008_bulk.json").read_text(encoding="utf-8"))


class BulkRecoveryTests(unittest.TestCase):
    def test_locked_universe(self) -> None:
        frame, digest = canonical_universe()
        self.assertEqual(len(frame), 2646)
        self.assertEqual(frame.legacy_observation_id.nunique(), 2646)
        self.assertEqual(digest, CONTRACT["input_universe"]["canonical_jsonl_sha256"])

    def test_member_inventory_parser(self) -> None:
        content = b'mkkMemberOid\\":\\"4028e4a140f2ed710140f2f4d6c70039\\",\\"kapMemberTitle\\":\\"X\\",\\"stockCode\\":\\"KCHOL\\"'
        self.assertEqual(parse_member_inventory(content)["KCHOL"], "4028e4a140f2ed710140f2f4d6c70039")

    def test_timestamp_availability_is_next_session(self) -> None:
        sessions = pd.DatetimeIndex(["2024-11-04", "2024-11-05", "2024-11-06"])
        self.assertEqual(available_from("04.11.2024 18:22:35", sessions), "2024-11-05T18:10:00")
        self.assertEqual(available_from("04.11.2024", sessions), "2024-11-05T18:10:00")

    def test_cache_hash_integrity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "item.bin"
            cache_write(path, b"official")
            self.assertEqual(cache_read(path), b"official")
            path.write_bytes(b"corrupt")
            with self.assertRaises(BatchStop):
                cache_read(path)

    def test_batch_plan_is_deterministic_and_complete(self) -> None:
        tickers = [f"T{i:02d}" for i in range(88)]
        plan = batch_plan(tickers)
        self.assertEqual([len(batch) for batch in plan], [3, 10, 15, 15, 15, 15, 15])
        self.assertEqual([ticker for batch in plan for ticker in batch], tickers)

    def test_local_comparison_and_missing_not_zero(self) -> None:
        missing = local_comparison("revenue", None, 100.0, CONTRACT)
        self.assertEqual(missing["audit_class"], "MISSING_LOCAL")
        exact = local_comparison("revenue", 100.0, 100.0, CONTRACT)
        self.assertEqual(exact["audit_class"], "EXACT_MATCH")
        semantic = local_comparison("cfo", 100.0, 90.0, CONTRACT)
        self.assertEqual(semantic["audit_class"], "SEMANTIC_MISMATCH")

    def test_safe_ytd_derivation(self) -> None:
        observations = pd.DataFrame([
            {"legacy_observation_id": "X:2022Q1", "ticker": "X", "financial_period": "2022Q1", "recovery_status": "RECOVERED_EXACT", "consolidation_basis": "CONSOLIDATED", "tfrs29_status": "PRE_TFRS29", "first_notification_id": 1},
            {"legacy_observation_id": "X:2022Q2", "ticker": "X", "financial_period": "2022Q2", "recovery_status": "RECOVERED_EXACT", "consolidation_basis": "CONSOLIDATED", "tfrs29_status": "PRE_TFRS29", "first_notification_id": 2},
        ])
        fields = pd.DataFrame([
            {"legacy_observation_id": "X:2022Q1", "ticker": "X", "financial_period": "2022Q1", "field": "revenue", "normalized_value": 100.0},
            {"legacy_observation_id": "X:2022Q2", "ticker": "X", "financial_period": "2022Q2", "field": "revenue", "normalized_value": 250.0},
        ])
        derived = derive_single_quarters(fields, observations, CONTRACT)
        self.assertEqual(float(derived.iloc[0].normalized_value), 150.0)
        self.assertEqual(derived.iloc[0].semantic_class, "FLOW_SINGLE_QUARTER_DERIVED")

    def test_no_latest_to_first_substitution_regressions(self) -> None:
        pilot = pd.read_csv(ROOT / "research" / "results" / "EXP-DATA-007_pilot_observations.csv")
        aefes = pilot[pilot.observation_id == "AEFES.IS:2022Q3"].iloc[0]
        self.assertEqual(int(aefes.kap_notification_id), 1076388)
        self.assertTrue(bool(aefes.restatement_revision_flag))

    def test_exp007_regression_suite(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "unittest", "research.tests.test_exp_data_007", "-q"],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)

    def test_production_hash_integrity(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(ROOT / "research" / "verify_production_hashes.py")],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)


if __name__ == "__main__":
    unittest.main()

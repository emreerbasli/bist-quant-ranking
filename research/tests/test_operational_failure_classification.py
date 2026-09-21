from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

RESEARCH = Path(__file__).resolve().parents[1]
ROOT = RESEARCH.parent
sys.path.insert(0, str(RESEARCH))

import forward_infrastructure_001r3 as fw
import run_frozen_shadow as runner


CID = "RC-LGBMR-001"
EXPECTED_CANDIDATES = {
    "RC-LGBMR-001": "350fb049f7f2e392a62fc89516acbb00676e1b1ef922559fc2f1dc3bfe9e81f6",
    "RC-LAMBDAMART-001": "4744a5109bc3f97b11f2ef6f890cdded5672fd5a25a9a8252f9e1ad7fb31d849",
}


class FakeCanonicalData:
    provider_id = "FAULT_CLASSIFICATION_FIXTURE"

    def __init__(self):
        self.calendar = pd.bdate_range(end="2026-09-18", periods=260)
        self.data = {}
        for i in range(12):
            x = pd.DataFrame(index=self.calendar)
            x["research_open"] = 100.0 + i + np.arange(len(x)) * 0.01
            x["research_close"] = x.research_open + 0.5
            x["raw_close"] = x.research_close
            x["volume"] = 100_000.0
            x["trading_eligible"] = True
            x["price_quality"] = "RESOLVED"
            self.data[f"S{i}"] = x
        self.index = self.data["S0"].copy()

    def benchmark(self):
        return self.index

    def symbols(self):
        return sorted(self.data)

    def view(self, symbol):
        return self.data[symbol]

    def input_paths(self, symbols):
        return [fw.CONTRACT]


class MissingData(FakeCanonicalData):
    def benchmark(self):
        return self.index.iloc[:0]


class OperationalFailureClassificationTests(unittest.TestCase):
    def injected(self, fault_stage: str):
        fake = FakeCanonicalData()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(runner.fw, "validate_activation", return_value=({"activation_baseline_source_max": "2026-09-17"}, {})), patch.object(runner, "CanonicalRunnerDataSources", return_value=fake), patch.object(runner.fw, "classify", return_value="CLEAN_FORWARD"):
                with self.assertRaises(RuntimeError):
                    runner.run(CID, "2026-09-18", forward_root=root, test_fault_stage=fault_stage)
            return fw.read_rows(root / "operational" / f"{CID}.jsonl")

    def test_a_snapshot_integrity_failure_is_classified(self):
        rows = self.injected("SNAPSHOT")
        self.assertEqual(rows[0]["failure_type"], "SNAPSHOT_HASH_FAILURE")
        self.assertEqual(rows[0]["failure_stage"], "SNAPSHOT")

    def test_b_snapshot_failure_is_not_data_not_ready(self):
        self.assertNotEqual(self.injected("SNAPSHOT")[0]["failure_type"], "DATA_NOT_READY")

    def test_c_order_generation_failure_is_classified(self):
        rows = self.injected("ORDER")
        self.assertEqual(rows[0]["failure_type"], "ORDER_FAILURE")
        self.assertEqual(rows[0]["failure_stage"], "ORDER")

    def test_d_order_failure_is_not_signal_failure(self):
        self.assertNotEqual(self.injected("ORDER")[0]["failure_type"], "SIGNAL_FAILURE")

    def test_e_genuine_data_readiness_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(runner.fw, "validate_activation", return_value=({"activation_baseline_source_max": "2026-09-17"}, {})), patch.object(runner, "CanonicalRunnerDataSources", return_value=MissingData()):
                with self.assertRaises(fw.ForwardIntegrityError):
                    runner.run(CID, "2026-09-18", forward_root=root)
            row = fw.read_rows(root / "operational" / f"{CID}.jsonl")[0]
            self.assertEqual((row["failure_type"], row["failure_stage"]), ("DATA_NOT_READY", "DATA"))

    def test_f_genuine_signal_failure(self):
        row = self.injected("SIGNAL")[0]
        self.assertEqual((row["failure_type"], row["failure_stage"]), ("SIGNAL_FAILURE", "SIGNAL"))

    def test_g_execution_failure_mapping(self):
        self.assertEqual(runner.failure_kind("EXECUTION", RuntimeError("x")), ("EXECUTION_FAILURE", "EXECUTION"))

    def test_h_nav_failure_mapping(self):
        self.assertEqual(runner.failure_kind("NAV", RuntimeError("x")), ("NAV_FAILURE", "NAV"))

    def test_i_cohort_failure_mapping(self):
        self.assertEqual(runner.failure_kind("COHORT", RuntimeError("x")), ("COHORT_EVAL_FAILURE", "COHORT"))

    def test_j_failure_event_is_durable_and_schema_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runner.operational(root, CID, "1.0.0", "run-1", "2026-09-18", "ORDER_FAILURE", "ORDER", RuntimeError("x"))
            runner.operational(root, CID, "1.0.0", "run-2", "2026-09-18", "ORDER_FAILURE", "ORDER", RuntimeError("x"))
            rows = fw.read_rows(root / "operational" / f"{CID}.jsonl")
            self.assertEqual(len(rows), 1)
            self.assertTrue({"failure_type", "failure_stage", "error_type", "event_id", "run_id", "candidate_id", "session", "timestamp", "message"}.issubset(rows[0]))

    def test_k_candidate_hashes_unchanged(self):
        for candidate, digest in EXPECTED_CANDIDATES.items():
            self.assertEqual(fw.sha(fw.FROZEN / candidate / "model.joblib"), digest)

    def test_l_production_protected_hash_diff_zero(self):
        baseline = json.loads((RESEARCH / "manifests" / "production_hash_manifest_before.json").read_text(encoding="utf-8"))
        changed = []
        for item in baseline["files"]:
            path = ROOT / item["path"]
            if bool(item.get("exists")) != path.exists() or (path.exists() and fw.sha(path) != item["sha256"]):
                changed.append(item["path"])
        self.assertEqual(changed, [])

    def test_m_official_logs_unchanged_and_empty(self):
        for candidate in EXPECTED_CANDIDATES:
            for name in ("shadow_signals.jsonl", "shadow_portfolio.jsonl", "shadow_operational_events.jsonl"):
                self.assertEqual((fw.FROZEN / candidate / name).stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()

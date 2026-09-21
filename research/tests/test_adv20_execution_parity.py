from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

RESEARCH = Path(__file__).resolve().parents[1]
ROOT = RESEARCH.parent
sys.path.insert(0, str(RESEARCH))

import forward_infrastructure_001r3 as fw
from exp_port_001 import adv20, good
from forward_lifecycle_001r3 import Lifecycle


CID = "RC-LGBMR-001"
EXPECTED_CANDIDATES = {
    "RC-LGBMR-001": "350fb049f7f2e392a62fc89516acbb00676e1b1ef922559fc2f1dc3bfe9e81f6",
    "RC-LAMBDAMART-001": "4744a5109bc3f97b11f2ef6f890cdded5672fd5a25a9a8252f9e1ad7fb31d849",
}


def view(rows: int = 21) -> pd.DataFrame:
    index = pd.bdate_range("2026-01-02", periods=rows)
    x = pd.DataFrame(index=index)
    x["research_open"] = 100.0
    x["research_close"] = 101.0
    x["raw_close"] = np.arange(100.0, 100.0 + rows)
    x["volume"] = np.arange(1.0, 1.0 + rows) * 1000.0
    x["trading_eligible"] = True
    x["price_quality"] = "RESOLVED"
    return x


class Adv20ExecutionParityTests(unittest.TestCase):
    def expected(self, x: pd.DataFrame) -> float:
        eligible = x.iloc[:20]
        eligible = eligible[
            eligible.trading_eligible.fillna(False)
            & eligible.price_quality.astype(str).ne("UNRESOLVED")
            & pd.to_numeric(eligible.raw_close, errors="coerce").gt(0)
            & pd.to_numeric(eligible.volume, errors="coerce").gt(0)
        ]
        return float((eligible.raw_close * eligible.volume).median()) if len(eligible) >= 15 else np.nan

    def test_a_twenty_valid_rows_match_exact_adv(self):
        x = view()
        self.assertEqual(adv20(x, 20), self.expected(x))

    def test_b_ineligible_rows_are_excluded(self):
        x = view(); x.loc[x.index[:5], "trading_eligible"] = False; x.loc[x.index[:5], "raw_close"] = 1_000_000.0
        self.assertEqual(adv20(x, 20), self.expected(x))

    def test_c_unresolved_quality_rows_are_excluded(self):
        x = view(); x.loc[x.index[:5], "price_quality"] = "UNRESOLVED"; x.loc[x.index[:5], "raw_close"] = 1_000_000.0
        self.assertEqual(adv20(x, 20), self.expected(x))

    def test_d_nonpositive_volume_rows_are_excluded(self):
        x = view(); x.loc[x.index[:3], "volume"] = [0.0, -1.0, np.nan]
        self.assertEqual(adv20(x, 20), self.expected(x))

    def test_e_nonpositive_or_invalid_price_rows_are_excluded(self):
        x = view(); x.loc[x.index[:3], "raw_close"] = [0.0, -1.0, np.nan]
        self.assertEqual(adv20(x, 20), self.expected(x))

    def test_f_exactly_fifteen_valid_rows_are_accepted(self):
        x = view(); x.loc[x.index[:5], "trading_eligible"] = False
        self.assertEqual(adv20(x, 20), self.expected(x))
        self.assertTrue(np.isfinite(adv20(x, 20)))

    def test_g_fourteen_valid_rows_fail_closed(self):
        x = view(); x.loc[x.index[:6], "trading_eligible"] = False
        self.assertTrue(np.isnan(adv20(x, 20)))

    def test_h_lifecycle_event_adv_equals_frozen_helper(self):
        calendar = pd.bdate_range("2026-01-02", periods=21)
        views = {f"S{i}": view() for i in range(12)}
        benchmark = view()
        contract = json.loads(fw.CONTRACT.read_text(encoding="utf-8"))
        manifest, _ = fw.frozen_candidate(CID)
        scores = [{"ticker": symbol, "raw_score": float(i), "cross_section_rank": i + 1, "selected_top10": i < 10, "signal_date_eligible": True} for i, symbol in enumerate(views)]
        with tempfile.TemporaryDirectory() as tmp:
            lifecycle = Lifecycle(Path(tmp), CID, manifest["candidate_version"], manifest, contract)
            lifecycle.create_signal("signal", calendar[19], calendar, scores, {"input_snapshot_hash": "x", "source_max_session": str(calendar[-1].date())})
            lifecycle.process_session("execution", calendar[20], calendar, views, benchmark)
            executions = [row for row in fw.read_rows(lifecycle.events) if row["event_type"] == "ORDER_EXECUTION"]
            self.assertEqual(len(executions), 10)
            self.assertTrue(all(row["adv_value"] == adv20(views[row["ticker"]], 20) for row in executions))

    def test_i_fill_decision_matches_frozen_contract(self):
        calendar = pd.bdate_range("2026-01-02", periods=21)
        views = {f"S{i}": view() for i in range(12)}
        benchmark = view()
        contract = json.loads(fw.CONTRACT.read_text(encoding="utf-8"))
        manifest, _ = fw.frozen_candidate(CID)
        scores = [{"ticker": symbol, "raw_score": float(i), "cross_section_rank": i + 1, "selected_top10": i < 10, "signal_date_eligible": True} for i, symbol in enumerate(views)]
        with tempfile.TemporaryDirectory() as tmp:
            lifecycle = Lifecycle(Path(tmp), CID, manifest["candidate_version"], manifest, contract)
            lifecycle.create_signal("signal", calendar[19], calendar, scores, {"input_snapshot_hash": "x", "source_max_session": str(calendar[-1].date())})
            lifecycle.process_session("execution", calendar[20], calendar, views, benchmark)
            executions = [row for row in fw.read_rows(lifecycle.events) if row["event_type"] == "ORDER_EXECUTION"]
            for row in executions:
                source = views[row["ticker"]]
                executable = good(source.iloc[20]) and np.isfinite(adv20(source, 20)) and row["order_notional"] <= adv20(source, 20) * contract["portfolio"]["max_order_adv_pct"]
                self.assertEqual(row["fill_status"], "FILLED" if executable else "BLOCKED")

    def test_j_candidate_hashes_unchanged(self):
        for candidate, digest in EXPECTED_CANDIDATES.items():
            self.assertEqual(fw.sha(fw.FROZEN / candidate / "model.joblib"), digest)

    def test_k_official_logs_unchanged_and_empty(self):
        for candidate in EXPECTED_CANDIDATES:
            for name in ("shadow_signals.jsonl", "shadow_portfolio.jsonl", "shadow_operational_events.jsonl"):
                self.assertEqual((fw.FROZEN / candidate / name).stat().st_size, 0)

    def test_l_production_protected_hash_diff_zero(self):
        baseline = json.loads((RESEARCH / "manifests" / "production_hash_manifest_before.json").read_text(encoding="utf-8"))
        changed = []
        for item in baseline["files"]:
            path = ROOT / item["path"]
            if bool(item.get("exists")) != path.exists() or (path.exists() and fw.sha(path) != item["sha256"]):
                changed.append(item["path"])
        self.assertEqual(changed, [])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

RESEARCH = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RESEARCH))
import prospective_dry_run_phase_f as dry
import forward_infrastructure_001r3 as fw


ARTIFACT = RESEARCH / "data" / "prospective_dry_runs" / "dry_20260919T130000Z.json"


class ProspectiveDryRunTests(unittest.TestCase):
    def test_end_to_end_artifact_contract(self):
        result = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        for key in ("dry_run_id", "created_at", "source", "canonical", "activation", "session", "provenance", "candidates", "excluded_fail_closed"):
            self.assertIn(key, result)
        self.assertTrue(result["DRY_RUN_ONLY"])
        self.assertFalse(result["official_commit"])
        self.assertEqual(result["session"]["session_date"], "2026-09-16")
        self.assertEqual(result["eligible_universe_count"], 86)

    def test_pit_exclusion_and_provenance(self):
        result = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        excluded = {row["ticker"]: row["reason"] for row in result["excluded_fail_closed"]}
        self.assertEqual(excluded["BIMAS.IS"], "RETROSPECTIVE_ACTION_EXCLUDED")
        self.assertEqual(excluded["SASA.IS"], "UNRESOLVED_MISSING_VOLUME")
        self.assertEqual(result["source"]["source_max"], "2026-09-18")
        self.assertEqual(result["activation"]["baseline_source_max"], "2026-09-15")
        self.assertTrue(all(len(value) == 64 for value in result["provenance"].values()))

    def test_both_candidates_rank_and_top10(self):
        result = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        for candidate, role in (("RC-LGBMR-001", "PRIMARY_SHADOW_MODEL"), ("RC-LAMBDAMART-001", "SECONDARY_SHADOW_MODEL")):
            payload = result["candidates"][candidate]
            self.assertEqual(payload["role"], role)
            rows = payload["scores"]
            self.assertEqual(len(rows), 86)
            self.assertEqual([row["rank"] for row in rows], list(range(1, 87)))
            self.assertEqual(sum(row["selected_top10"] for row in rows), 10)
            self.assertEqual(len({row["ticker"] for row in rows[:10]}), 10)

    def test_deterministic_substantive_rerun_and_write_once(self):
        first = dry.run_dry_run("2026-09-16")
        second = dry.run_dry_run("2026-09-16")
        self.assertEqual(first["substantive_sha256"], second["substantive_sha256"])
        self.assertEqual(dry.write_once(ARTIFACT, second), "READ_ONLY_REUSE")

    def test_candidate_and_official_log_integrity(self):
        result = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        for candidate in ("RC-LGBMR-001", "RC-LAMBDAMART-001"):
            manifest = fw.candidate_manifest(candidate)
            self.assertEqual(result["candidates"][candidate]["model_sha256"], manifest["model_sha256"])
        for path in (RESEARCH / "frozen_candidates").glob("*/shadow_*.jsonl"):
            self.assertEqual(path.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()

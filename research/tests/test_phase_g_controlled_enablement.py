from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

RESEARCH = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RESEARCH))
import phase_g_controlled_enablement as phase_g


ARTIFACT = RESEARCH / "data" / "phase_g_readiness" / "EXP-DEPLOY-001-PHASE-G.json"


class PhaseGTests(unittest.TestCase):
    def test_temporal_gate_is_fail_closed(self):
        result = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        self.assertEqual(result["gate"], "PASS")
        self.assertFalse(result["genuinely_post_activation_eligible"])
        self.assertEqual(result["latest_prospective_session"], "2026-09-18")
        self.assertEqual(result["official_evidence_count_before"], 0)
        self.assertEqual(result["official_evidence_count_after"], 0)
        self.assertTrue(result["backfill_prevented"])

    def test_no_official_write_and_expected_exclusions(self):
        result = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        self.assertFalse(result["official_write_performed"])
        reasons = {row["ticker"]: row["reason"] for row in result["fail_closed_exclusions"]}
        self.assertEqual(reasons["BIMAS.IS"], "RETROSPECTIVE_ACTION_EXCLUDED")
        self.assertEqual(reasons["SASA.IS"], "UNRESOLVED_MISSING_VOLUME")

    def test_write_once_reuse(self):
        self.assertEqual(phase_g.write_once(ARTIFACT, phase_g.evaluate()), "READ_ONLY_REUSE")


if __name__ == "__main__":
    unittest.main()

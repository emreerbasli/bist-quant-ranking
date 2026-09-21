from pathlib import Path
import json
import sys
import tempfile
import unittest

import pandas as pd

RESEARCH = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RESEARCH))
import prospective_canonical_extension as ext


PRICE = RESEARCH / "data" / "prospective_raw" / "acq_20260919T102219Z"
ACTIONS = RESEARCH / "data" / "prospective_corporate_actions" / "kap_ca_20260919T104003Z"


class ProspectiveCanonicalExtensionTests(unittest.TestCase):
    def test_bimas_retrospective_action_is_excluded(self):
        parent, _ = ext.load_view("BIMAS.IS")
        events = {(e["ticker"], e["ex_date"]): e for e in json.loads((ACTIONS / "normalized_events.json").read_text())["events"]}
        frame, state = ext.build_symbol("BIMAS.IS", PRICE / "BIMAS_IS.parquet", parent, events)
        self.assertEqual(state["chain_state_status"], "RETROSPECTIVE_OR_UNKNOWN_ACTION")
        self.assertFalse(bool(frame.iloc[0]["trading_eligible"]))
        self.assertEqual(frame.iloc[0]["corporate_action_flag"], "RETROSPECTIVE_ACTION_EXCLUDED")

    def test_non_action_chain_continues_from_frozen_state(self):
        parent, _ = ext.load_view("AEFES.IS")
        frame, state = ext.build_symbol("AEFES.IS", PRICE / "AEFES_IS.parquet", parent, {})
        self.assertEqual(state["chain_state_status"], "CONTINUED")
        self.assertEqual(len(frame), 2)
        self.assertTrue(frame.iloc[0]["trading_eligible"])
        self.assertTrue(pd.notna(frame.iloc[0]["research_close"]))

    def test_canonical_output_is_deterministic(self):
        parent, _ = ext.load_view("AEFES.IS")
        first, _ = ext.build_symbol("AEFES.IS", PRICE / "AEFES_IS.parquet", parent, {})
        second, _ = ext.build_symbol("AEFES.IS", PRICE / "AEFES_IS.parquet", parent, {})
        self.assertEqual(ext.canonical_hash(first), ext.canonical_hash(second))

    def test_historical_backfill_rejected(self):
        parent, _ = ext.load_view("AEFES.IS")
        raw = pd.read_parquet(PRICE / "AEFES_IS.parquet").copy()
        raw.index = pd.to_datetime(raw.index)
        raw.index = raw.index.where(raw.index != raw.index[0], pd.Timestamp("2026-09-15"))
        with tempfile.TemporaryDirectory() as directory:
            raw_path = Path(directory) / "historical.parquet"
            raw.to_parquet(raw_path)
            with self.assertRaisesRegex(ValueError, "HISTORICAL_BACKFILL_FORBIDDEN"):
                ext.build_symbol("AEFES.IS", raw_path, parent, {})


if __name__ == "__main__":
    unittest.main()

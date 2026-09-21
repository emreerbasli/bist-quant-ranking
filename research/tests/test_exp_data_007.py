from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

from research.exp_data_007 import (
    classify_consolidation,
    flow_semantics,
    parse_number,
    presentation_unit_multiplier,
    presentation_unit_info,
    select_lineage,
    tfrs29_status,
    timing_quality,
)


ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "research" / "results"


def csv(name: str) -> pd.DataFrame:
    return pd.read_csv(RESULTS / name)


class KapVintagePilotTests(unittest.TestCase):
    def test_known_isctr_2024q3_regression(self) -> None:
        obs = csv("EXP-DATA-007_pilot_observations.csv")
        row = obs[(obs.ticker == "ISCTR.IS") & (obs.financial_period == "2024Q3")].iloc[0]
        self.assertEqual(int(row.kap_notification_id), 1353364)
        self.assertEqual(row.announcement_timestamp, "04.11.2024 18:22:35")
        self.assertEqual(row.consolidated_flag, "NON_CONSOLIDATED")
        values = csv("EXP-DATA-007_field_values.csv")
        net = values[(values.observation_id == "ISCTR.IS:2024Q3") & (values.field == "net_income")].iloc[0]
        self.assertEqual(float(net.first_published_value_try), 34_684_797_000)

    def test_original_vs_restated_mapping_sanity(self) -> None:
        candidates = csv("EXP-DATA-007_notification_candidates.csv")
        rows = candidates[candidates.observation_id == "AEFES.IS:2022Q3"].copy()
        rows["parsed_time"] = pd.to_datetime(rows.announcement_timestamp, dayfirst=True)
        rows = rows.sort_values("parsed_time")
        self.assertEqual(rows.notification_id.astype(int).tolist(), [1076388, 1076969])
        self.assertEqual(rows.modify_status.tolist(), ["DUZELTILEN", "DUZENLENEN"])
        obs = csv("EXP-DATA-007_pilot_observations.csv")
        row = obs[obs.observation_id == "AEFES.IS:2022Q3"].iloc[0]
        self.assertTrue(bool(row.restatement_revision_flag))
        self.assertEqual(row.vintage_class, "RESTATED")

    def test_timestamp_date_classification(self) -> None:
        self.assertEqual(timing_quality("04.11.2024 18:22:35"), "EXACT_TIMESTAMP")
        self.assertEqual(timing_quality("04.11.2024"), "EXACT_DATE")
        self.assertEqual(timing_quality("2024-Q3"), "APPROXIMATE")
        self.assertEqual(timing_quality(None), "UNKNOWN")

    def test_duplicate_notification_handling(self) -> None:
        rows = [
            {"consolidated_flag": "CONSOLIDATED", "id": 1},
            {"consolidated_flag": "NON_CONSOLIDATED", "id": 2},
            {"consolidated_flag": "CONSOLIDATED", "id": 3},
        ]
        selected, failure = select_lineage(rows, "CONSOLIDATED")
        self.assertIsNone(failure)
        self.assertEqual([row["id"] for row in selected], [1, 3])

    def test_consolidated_solo_discrimination(self) -> None:
        self.assertEqual(
            classify_consolidation("Finansal Tablo Niteliği Konsolide Olmayan"), "NON_CONSOLIDATED"
        )
        self.assertEqual(classify_consolidation("Finansal Tablo Niteliği Konsolide"), "CONSOLIDATED")
        self.assertEqual(classify_consolidation("basis unavailable"), "UNKNOWN")

    def test_ytd_semantics_sanity(self) -> None:
        self.assertEqual(flow_semantics(1), "SINGLE_QUARTER")
        self.assertEqual(flow_semantics(2), "YTD_6M")
        self.assertEqual(flow_semantics(3), "YTD_9M")
        self.assertEqual(flow_semantics(4), "ANNUAL")
        semantics = csv("EXP-DATA-007_accounting_semantics.csv")
        unsafe = semantics[semantics.financial_period.str[-1].isin(["2", "3", "4"])]
        self.assertFalse(unsafe.single_quarter_decomposition_safe.any())

    def test_tfrs29_comparison_sanity(self) -> None:
        self.assertEqual(tfrs29_status("2022Q3", "NON_FINANCIAL", False), "PRE_TFRS29")
        self.assertEqual(
            tfrs29_status("2024Q2", "BANK", False), "BANK_BDDK_NOT_APPLIED_IN_LOCAL_CONTRACT"
        )
        self.assertEqual(
            tfrs29_status("2024Q2", "NON_FINANCIAL", True), "POST_TFRS29_MENTION_CONFIRMED"
        )
        tfrs = csv("EXP-DATA-007_tfrs29_comparison.csv")
        confirmed = tfrs[tfrs.tfrs29_status == "POST_TFRS29_MENTION_CONFIRMED"]
        self.assertGreater(len(confirmed), 0)
        self.assertTrue(
            (confirmed.double_adjustment_risk == "DOUBLE-ADJUSTMENT RISK").all()
        )
        self.assertTrue(confirmed.restated_comparative_net_income_try.isna().all())
        self.assertTrue(
            confirmed.restated_comparative_status.str.contains("NOT_SEPARATELY_PROVEN").all()
        )

    def test_missing_is_not_zero(self) -> None:
        self.assertIsNone(parse_number(""))
        self.assertIsNone(parse_number("-"))
        self.assertEqual(parse_number("0"), 0)
        values = csv("EXP-DATA-007_field_values.csv")
        missing = values[values.missing_official]
        self.assertTrue(missing.first_published_value_try.isna().all())

    def test_presentation_currency_scale(self) -> None:
        self.assertEqual(presentation_unit_multiplier("Sunum Para Birimi 1.000 TL"), 1_000)
        self.assertEqual(presentation_unit_multiplier("Sunum Para Birimi 1.000.000 TL"), 1_000_000)
        self.assertEqual(presentation_unit_multiplier("Sunum Para Birimi TL"), 1)
        self.assertEqual(parse_number("162.998", 1_000_000), parse_number("162.998.000.000", 1))

    def test_statement_unit_metadata_and_mixed_unit_rejection(self) -> None:
        one_million = BeautifulSoup("<table><tr><td>Sunum Para Birimi</td><td>1.000.000 TL</td></tr></table>", "html.parser")
        one_thousand = BeautifulSoup("<table><tr><td>Sunum Para Birimi</td><td>1.000 TL</td></tr></table>", "html.parser")
        insurer_tl = BeautifulSoup("<table><tr><td>Sunum Para Birimi</td><td>TL</td></tr></table>", "html.parser")
        mixed = BeautifulSoup("<table><tr><td>Sunum Para Birimi</td><td>TL</td></tr><tr><td>Sunum Para Birimi</td><td>1.000 TL</td></tr></table>", "html.parser")
        self.assertEqual(presentation_unit_info(one_million)["multiplier"], 1_000_000)
        self.assertEqual(presentation_unit_info(one_thousand)["multiplier"], 1_000)
        self.assertEqual(presentation_unit_info(insurer_tl)["multiplier"], 1)
        self.assertEqual(presentation_unit_info(mixed)["status"], "INVALID_MIXED_OR_UNKNOWN")

    def test_pilot_scope_and_production_hash_integrity(self) -> None:
        summary = json.loads((RESULTS / "EXP-DATA-007_recovery_summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["total_pilot_observations"], 30)
        self.assertLess(summary["request_count"], 200)
        completed = subprocess.run(
            [sys.executable, str(ROOT / "research" / "verify_production_hashes.py")],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)


if __name__ == "__main__":
    unittest.main()

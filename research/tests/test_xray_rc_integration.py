"""Focused, read-only checks for the RC model binding in the X-Ray view."""

import json
import re
import unittest
from pathlib import Path

import shadow_reader


ROOT = Path(__file__).resolve().parents[2]
DRY_RUN = ROOT / "research" / "data" / "prospective_dry_runs" / "dry_20260919T130000Z.json"


class XRayRcIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.artifact = json.loads(DRY_RUN.read_text(encoding="utf-8"))
        cls.state = shadow_reader.get_shadow_system_state(ROOT)
        cls.source = (ROOT / "app.py").read_text(encoding="utf-8")
        cls.xray = cls.source.split('elif sayfa == "🔍 Hisse Röntgeni (X-Ray)":', 1)[1]

    def test_reader_exposes_full_cross_section_and_top10(self):
        self.assertEqual(self.state["status"], "VALIDATED_DRY_RUN")
        self.assertEqual(self.state["session_date"], "2026-09-16")
        self.assertEqual(self.state["eligible_universe_count"], 86)
        for candidate in ("RC-LGBMR-001", "RC-LAMBDAMART-001"):
            rows = self.state["primary" if candidate == "RC-LGBMR-001" else "secondary"]["cross_section"]
            self.assertEqual(len(rows), 86)
            self.assertEqual([r["rank"] for r in rows], list(range(1, 87)))
            self.assertEqual(sum(r["selected_top10"] for r in rows), 10)

    def test_reader_matches_frozen_dry_run_scores_exactly(self):
        for candidate, key in (("RC-LGBMR-001", "primary"), ("RC-LAMBDAMART-001", "secondary")):
            expected = self.artifact["candidates"][candidate]["scores"]
            actual = self.state[key]["cross_section"]
            self.assertEqual(actual, expected)
            self.assertEqual(self.state[key]["ordered_top10"], expected[:10])

    def test_exclusions_are_preserved(self):
        self.assertEqual(self.state["excluded_symbols"], self.artifact["excluded_fail_closed"])

    def test_app_consumes_cross_section_and_declares_frozen_features(self):
        self.assertIn('.get("cross_section")', self.source)
        for feature in ("mom_12_1", "mom_63", "vol_63"):
            self.assertIn(feature, self.source)
        self.assertNotIn("z_reel_eps\": 0.0", self.source)

    def test_xray_has_no_stale_v4_rc_labels(self):
        self.assertNotIn("V4 LambdaMART 7 faktör", self.xray)
        self.assertNotIn("V4 LambdaMART Skoru", self.xray)
        self.assertIn("Frozen model girdileri", self.xray)
        self.assertIn("PRIMARY/SECONDARY SHADOW", self.xray)

    def test_rc_composite_card_is_rank_based_not_zero_fallback(self):
        self.assertIn("_xr_karne_skor = 100 if _xr_n <= 1", self.source)
        self.assertIn("_xr_rank_for_card", self.source)
        ranks = [row["rank"] for row in self.state["primary"]["cross_section"]]
        cards = [round(100 * (len(ranks) - rank) / (len(ranks) - 1)) for rank in ranks]
        self.assertEqual(cards[0], 100)
        self.assertEqual(cards[-1], 0)
        self.assertGreater(len(set(cards)), 10)

    def test_primary_homepage_renders_both_independent_portfolios(self):
        portfolio_page = self.source.split('if sayfa == "💼 Portföyüm & Pozisyon Yönetimi":', 1)[1].split(
            'elif sayfa == "🏆 BIST 88 Model Sıralaması":', 1
        )[0]
        self.assertIn('shadow_state[_home_key]', portfolio_page)
        self.assertIn('"primary"', portfolio_page)
        self.assertIn('"secondary"', portfolio_page)
        self.assertIn("RC-LGBMR-001", portfolio_page)
        self.assertIn("RC-LAMBDAMART-001", portfolio_page)
        self.assertIn("birleşik portföy değildir", portfolio_page)

    def test_homepage_drops_duplicate_active_table_and_keeps_detailed_chart(self):
        portfolio_page = self.source.split('if sayfa == "💼 Portföyüm & Pozisyon Yönetimi":', 1)[1].split(
            'elif sayfa == "🏆 BIST 88 Model Sıralaması":', 1
        )[0]
        self.assertNotIn('st.markdown(f"#### Aktif görünüm:', portfolio_page)
        self.assertNotIn('st.dataframe(df_selection', portfolio_page)
        self.assertIn('Bollinger Üst', self.source)
        self.assertIn('MACD (12,26,9)', self.source)
        self.assertIn('rows=4', self.source)

    def test_chart_has_explicit_period_selection(self):
        for period in ("1 Ay", "3 Ay", "6 Ay", "1 Yıl", "Tüm Veri"):
            self.assertIn(period, self.source)
        self.assertIn("_xr_period_rows", self.source)
        self.assertIn("xray_period_", self.source)

    def test_app_compiles(self):
        compile(self.source, str(ROOT / "app.py"), "exec")


if __name__ == "__main__":
    unittest.main()

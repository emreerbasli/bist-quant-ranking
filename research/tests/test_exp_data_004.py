import json
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from research.exp_data_004 import (
    CONTRACT, OHLC, RESULTS, SNAPSHOT, VIEW_DIR, _status, build_symbol_view,
    events_by_symbol, share_factor, theoretical_ex_price, view_path,
)


class AuthoritativeTimelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        cls.by_symbol = events_by_symbol(cls.contract)

    def test_five_known_anomalies_are_quarantined_until_official_ex_date(self):
        self.assertEqual(len(self.contract["events"]), 5)
        for event in self.contract["events"]:
            view = pd.read_parquet(view_path(event["symbol"]))
            provider_date = pd.Timestamp(event["provider_adjusted_date"])
            ex_date = pd.Timestamp(event["ex_date"])
            unsafe = view.loc[(view.index >= provider_date) & (view.index < ex_date)]
            self.assertGreater(len(unsafe), 0)
            self.assertTrue(unsafe["research_close"].isna().all())
            self.assertTrue(unsafe["price_quality"].eq("UNRESOLVED").all())
            self.assertEqual(view.loc[ex_date, "price_quality"], "RECONSTRUCTED")

    def test_effective_date_not_announcement_or_provider_date_drives_reconstruction(self):
        for event in self.contract["events"]:
            view = pd.read_parquet(view_path(event["symbol"]))
            ex_date = pd.Timestamp(event["ex_date"])
            self.assertEqual(view.loc[ex_date, "corporate_action_flag"], event["action_type"])
            self.assertTrue(np.isfinite(view.loc[ex_date, "research_close"]))

    def test_future_action_does_not_rewrite_pre_anomaly_research_prices(self):
        for event in self.contract["events"]:
            with_event = pd.read_parquet(view_path(event["symbol"]))
            without_event = build_symbol_view(event["symbol"], [])
            before = with_event.index < pd.Timestamp(event["provider_adjusted_date"])
            pd.testing.assert_series_equal(
                with_event.loc[before, "research_close"], without_event.loc[before, "research_close"],
                check_names=False, check_exact=False, rtol=1e-12, atol=1e-12,
            )

    def test_no_duplicate_or_date_order_corruption(self):
        paths = list(VIEW_DIR.glob("*.parquet"))
        self.assertEqual(len(paths), 89)
        for path in paths:
            frame = pd.read_parquet(path)
            self.assertFalse(frame.index.has_duplicates, path.name)
            self.assertTrue(frame.index.is_monotonic_increasing, path.name)

    def test_daily_nav_compatibility(self):
        for name in ("universe_equal_weight", "momentum_12_1_top10"):
            frame = pd.read_csv(RESULTS / f"EXP-DATA-004_{name}_authoritative_daily.csv")
            equity = pd.to_numeric(frame["equity"], errors="coerce")
            self.assertTrue(np.isfinite(equity).all())
            self.assertTrue(equity.gt(0).all())
            dates = pd.to_datetime(frame["date"])
            self.assertTrue(dates.is_monotonic_increasing)

    def test_vectorized_refactor_matches_rowwise_reference_on_event_windows(self):
        for event in self.contract["events"]:
            symbol = event["symbol"]
            vector = pd.read_parquet(view_path(symbol))
            provider = pd.read_parquet(SNAPSHOT / f"{symbol.replace('.', '_')}.parquet").sort_index()
            provider.index = pd.DatetimeIndex(provider.index).normalize()
            corrected = provider[OHLC].apply(pd.to_numeric, errors="coerce").copy()
            pdate, exdate = pd.Timestamp(event["provider_adjusted_date"]), pd.Timestamp(event["ex_date"])
            unsafe = (corrected.index >= pdate) & (corrected.index < exdate)
            corrected.loc[unsafe, OHLC] *= share_factor(event)
            reference = pd.DataFrame(np.nan, index=corrected.index, columns=OHLC)
            first = corrected["close"].first_valid_index()
            reference.loc[first, OHLC] = corrected.loc[first, OHLC]
            prev_research_close = float(reference.loc[first, "close"])
            prev_nominal_close = float(corrected.loc[first, "close"])
            for date in corrected.index[corrected.index.get_loc(first) + 1:]:
                current_close = corrected.loc[date, "close"]
                if pd.isna(current_close):
                    continue
                if date == exdate:
                    denominator = theoretical_ex_price(prev_nominal_close, event)
                    numerator = float(current_close)
                else:
                    denominator = prev_nominal_close
                    numerator = float(current_close + provider.loc[date, "dividends"])
                growth = numerator / denominator
                current_research_close = prev_research_close * growth
                reference.loc[date, OHLC] = corrected.loc[date, OHLC] * (current_research_close / float(current_close))
                prev_research_close = current_research_close
                prev_nominal_close = float(current_close)
            reference.loc[unsafe, OHLC] = np.nan

            left = vector.index.get_loc(pdate)
            right = vector.index.get_loc(exdate)
            window = vector.index[max(0, left - 2): min(len(vector), right + 3)]
            for column in OHLC:
                np.testing.assert_allclose(
                    vector.loc[window, f"research_{column}"].to_numpy(dtype=float),
                    reference.loc[window, column].to_numpy(dtype=float),
                    rtol=1e-12, atol=1e-12, equal_nan=True,
                )
            expected_quality = pd.Series("PROVIDER_ONLY", index=window)
            expected_quality.loc[(window >= pdate) & (window < exdate)] = "UNRESOLVED"
            if exdate in window:
                expected_quality.loc[exdate] = "RECONSTRUCTED"
            pd.testing.assert_series_equal(vector.loc[window, "price_quality"], expected_quality, check_names=False)
            self.assertTrue(vector.loc[(vector.index >= pdate) & (vector.index < exdate), "trading_eligible"].eq(False).all())

            rowwise_status = []
            previous = None
            for _, row in vector.loc[window].iterrows():
                rowwise_status.append(_status(row, previous))
                if pd.notna(row["raw_close"]):
                    previous = float(row["raw_close"])
            # Seed the first window row with its true preceding close for exact status.
            first_date = window[0]
            prior_dates = vector.index[vector.index < first_date]
            if len(prior_dates):
                previous = float(vector.loc[prior_dates[-1], "raw_close"])
                rowwise_status = []
                for _, row in vector.loc[window].iterrows():
                    rowwise_status.append(_status(row, previous))
                    if pd.notna(row["raw_close"]):
                        previous = float(row["raw_close"])
            self.assertEqual(vector.loc[window, "trading_status"].tolist(), rowwise_status)

    def test_quality_counts_and_eligibility_consistent(self):
        manifest = pd.read_csv(RESULTS / "EXP-DATA-004_price_view_manifest.csv")
        total = int(manifest["rows"].sum())
        quality_total = int(manifest[["quality_verified", "quality_reconstructed", "quality_provider_only", "quality_unresolved"]].sum().sum())
        self.assertEqual(total, 159229)
        self.assertEqual(quality_total, total)
        for path in VIEW_DIR.glob("*.parquet"):
            frame = pd.read_parquet(path)
            expected = (
                frame["price_quality"].isin(["VERIFIED", "RECONSTRUCTED", "PROVIDER_ONLY"])
                & frame["trading_status"].eq("TRADED_PROVIDER")
                & frame[[f"research_{x}" for x in OHLC]].notna().all(axis=1)
            )
            self.assertTrue(frame["trading_eligible"].eq(expected).all(), path.name)

    def test_sasa_zero_volume_is_generically_ineligible_with_marks_retained(self):
        sasa = pd.read_parquet(view_path("SASA.IS")).loc["2025":"2026"]
        affected = sasa[sasa["volume"].le(0)]
        self.assertEqual(len(affected), 140)
        self.assertTrue(affected["price_quality"].eq("UNRESOLVED").all())
        self.assertTrue(affected["trading_eligible"].eq(False).all())
        # Research prices remain as observable marks; simulator eligibility masks them
        # and therefore forward-fills only the last valid mark for held-position NAV.
        self.assertTrue(affected["research_close"].notna().all())


if __name__ == "__main__":
    unittest.main()

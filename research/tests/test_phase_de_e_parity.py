from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

RESEARCH = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RESEARCH))

import exp_data_004 as frozen
import exp_tgt_001 as target
import forward_infrastructure_001r3 as fw
import prospective_canonical_extension as ext


PRICE = RESEARCH / "data" / "provider_snapshot"
EVENTS = json.loads(frozen.CONTRACT.read_text(encoding="utf-8"))["events"]
EVENT_MAP = {
    (event["symbol"], event["ex_date"]): {
        "ticker": event["symbol"],
        "ex_date": event["ex_date"],
        "event_type": event["action_type"],
        "action_type": event["action_type"],
        "ratio": event["ratio"],
        "subscription_price": event.get("subscription_price", 0.0),
        "pit_status": "PROSPECTIVE_CAPTURED",
        "provider_adjusted_date": event.get("provider_adjusted_date"),
    }
    for event in EVENTS
}


def raw_path(symbol: str) -> Path:
    return PRICE / ext.file_name(symbol)


class PhaseDEParityTests(unittest.TestCase):
    def compare_window(self, symbol: str, start: str, end: str, event_symbols: set[str] | None = None):
        provider = pd.read_parquet(raw_path(symbol)).sort_index()
        provider.index = pd.to_datetime(provider.index).normalize()
        start_ts, end_ts = pd.Timestamp(start), pd.Timestamp(end)
        raw = provider.loc[(provider.index >= start_ts) & (provider.index <= end_ts)].copy()
        parent, _ = ext.load_view(symbol)
        parent = parent.loc[parent.index < start_ts]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "window.parquet"
            raw.to_parquet(path)
            selected = {k: v for k, v in EVENT_MAP.items() if k[0] == symbol}
            actual, _ = ext.build_symbol(symbol, path, parent, selected)
        reference = frozen.build_symbol_view(symbol, [e for e in EVENTS if e["symbol"] == symbol]).loc[raw.index]
        columns = [
            "ticker", "raw_open", "raw_high", "raw_low", "raw_close",
            "provider_adjusted_open", "provider_adjusted_high", "provider_adjusted_low",
            "provider_adjusted_close", "volume", "dividends", "provider_stock_splits",
            "research_open", "research_high", "research_low", "research_close",
            "price_quality", "corporate_action_flag", "trading_status", "trading_eligible",
        ]
        self.assertEqual(actual.index.tolist(), reference.index.tolist())
        for column in columns:
            categorical = {"ticker", "price_quality", "corporate_action_flag", "trading_status"}
            if column in categorical or actual[column].dtype == object or reference[column].dtype == object:
                self.assertEqual(actual[column].fillna("<NA>").tolist(), reference[column].fillna("<NA>").tolist(), f"{symbol}:{column}")
            elif str(actual[column].dtype) == "bool" or str(reference[column].dtype) == "bool":
                self.assertEqual(actual[column].fillna(False).tolist(), reference[column].fillna(False).tolist(), f"{symbol}:{column}")
            else:
                a, b = actual[column].to_numpy(float), reference[column].to_numpy(float)
                self.assertTrue(np.array_equal(np.isnan(a), np.isnan(b)), f"{symbol}:{column}:nan-mask")
                self.assertTrue(np.allclose(a[~np.isnan(a)], b[~np.isnan(b)], rtol=0.0, atol=1e-12), f"{symbol}:{column}:values")

    def test_normal_sessions_exact(self):
        self.compare_window("AEFES.IS", "2025-01-02", "2025-01-07")

    def test_rights_issue_exact(self):
        self.compare_window("HEKTS.IS", "2024-09-08", "2024-09-21")

    def test_bonus_issue_exact(self):
        self.compare_window("CCOLA.IS", "2024-08-14", "2024-08-18")

    def test_early_adjustment_and_unresolved_exact(self):
        self.compare_window("KBORU.IS", "2024-12-30", "2025-01-08")

    @staticmethod
    def historical_events():
        return EVENT_MAP

    def prospective_historical_views(self, target_date: str, start_date: str, selected_symbols: list[str] | None = None):
        target_ts, start_ts = pd.Timestamp(target_date), pd.Timestamp(start_date)
        contract = json.loads(target.CONTRACT_PATH.read_text())
        calendar = target.load_inputs(contract)[0]
        symbols = sorted(selected_symbols or target.load_inputs(contract)[1])
        result = {}
        for symbol in symbols:
            parent, _ = ext.load_view(symbol)
            parent = parent.loc[parent.index < start_ts]
            provider = pd.read_parquet(raw_path(symbol)).sort_index()
            provider.index = pd.to_datetime(provider.index).normalize()
            raw = provider.loc[(provider.index >= start_ts) & (provider.index <= target_ts)]
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "window.parquet"
                raw.to_parquet(path)
                frame, _ = ext.build_symbol(symbol, path, parent, self.historical_events())
            result[symbol] = pd.concat([parent, frame]).sort_index().reindex(calendar)
        return result

    def feature_matrix_pair(self, target_date: str = "2025-05-29", start_date: str = "2025-05-29"):
        contract = json.loads(target.CONTRACT_PATH.read_text())
        calendar, symbols, frozen_views, _ = target.load_inputs(contract)
        signal = pd.Timestamp(target_date)
        pos = calendar.get_loc(signal)
        frozen_rows, prospective_rows = {}, {}
        for symbol in symbols:
            frozen_rows[symbol] = target.feature_row(frozen_views[symbol], pos)
        eligible_symbols = [symbol for symbol in symbols if frozen_rows[symbol] is not None]
        prospective_views = self.prospective_historical_views(target_date, start_date, eligible_symbols)
        for symbol in eligible_symbols:
            prospective_rows[symbol] = target.feature_row(prospective_views[symbol], prospective_views[symbol].index.get_loc(signal))
        return symbols, frozen_rows, prospective_rows

    def test_feature_values_and_nan_masks_exact(self):
        symbols, frozen_rows, prospective_rows = self.feature_matrix_pair()
        eligible_symbols = [s for s in symbols if frozen_rows[s] is not None]
        for feature in target.FEATURES:
            for symbol in eligible_symbols:
                a = np.nan if frozen_rows[symbol] is None else frozen_rows[symbol].get(feature, np.nan)
                b = np.nan if prospective_rows[symbol] is None else prospective_rows[symbol].get(feature, np.nan)
                self.assertEqual(pd.isna(a), pd.isna(b), f"{symbol}:{feature}:nan-mask")
                if pd.notna(a):
                    self.assertTrue(np.allclose(float(a), float(b), rtol=0.0, atol=1e-12), f"{symbol}:{feature}")

    def test_eligible_universe_exact(self):
        symbols, frozen_rows, prospective_rows = self.feature_matrix_pair()
        self.assertEqual([s for s in symbols if frozen_rows[s] is not None], [s for s in symbols if prospective_rows.get(s) is not None])

    def test_candidate_score_and_rank_parity(self):
        symbols, frozen_rows, prospective_rows = self.feature_matrix_pair()
        eligible = [s for s in symbols if frozen_rows[s] is not None]
        frozen_x = pd.DataFrame([frozen_rows[s] for s in eligible], index=eligible)[target.FEATURES].to_numpy(float)
        prospective_x = pd.DataFrame([prospective_rows[s] for s in eligible], index=eligible)[target.FEATURES].to_numpy(float)
        self.assertTrue(np.array_equal(np.isnan(frozen_x), np.isnan(prospective_x)))
        for candidate in ("RC-LGBMR-001", "RC-LAMBDAMART-001"):
            _, artifact = fw.frozen_candidate(candidate)
            frozen_score = np.median(np.column_stack([model.predict(frozen_x) for model in artifact["bundle"]["models"]]), axis=1)
            prospective_score = np.median(np.column_stack([model.predict(prospective_x) for model in artifact["bundle"]["models"]]), axis=1)
            self.assertTrue(np.allclose(frozen_score, prospective_score, rtol=0.0, atol=1e-12), f"{candidate}:score")
            frozen_order = sorted(zip(eligible, frozen_score), key=lambda row: (-row[1], row[0]))
            prospective_order = sorted(zip(eligible, prospective_score), key=lambda row: (-row[1], row[0]))
            self.assertEqual([x[0] for x in frozen_order], [x[0] for x in prospective_order], f"{candidate}:rank")
            self.assertEqual([x[0] for x in frozen_order[:10]], [x[0] for x in prospective_order[:10]], f"{candidate}:top10")

    def test_prospective_partition_is_feature_ready(self):
        partition = RESEARCH / "data" / "prospective_canonical" / "pc_20260919T105500Z"
        manifest = json.loads((partition / "manifest.json").read_text())
        calendar = ext.load_view("XU100.IS")[0].index
        extension_dates = sorted({pd.Timestamp(d) for record in manifest["records"] for d in pd.read_parquet(RESEARCH / record["path"]).index})
        calendar = calendar.union(pd.DatetimeIndex(extension_dates))
        ready = 0
        for record in manifest["records"]:
            frame = pd.read_parquet(RESEARCH / record["path"]).sort_index()
            if frame.empty:
                continue
            combined, _ = ext.load_view(record["ticker"])
            combined = pd.concat([combined, frame]).sort_index().reindex(calendar)
            pos = combined.index.get_loc(pd.Timestamp("2026-09-16")) if pd.Timestamp("2026-09-16") in combined.index else -1
            if pos >= 0 and target.feature_row(combined, pos) is not None:
                ready += 1
        self.assertGreaterEqual(ready, 87)


if __name__ == "__main__":
    unittest.main()

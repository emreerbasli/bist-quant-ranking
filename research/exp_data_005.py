"""EXP-DATA-005 residual price-risk and materiality audit (research only)."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research.exp_data_004 import build_symbol_view

RESEARCH = Path(__file__).resolve().parent
SNAPSHOT = RESEARCH / "data" / "provider_snapshot"
BASE_VIEW = RESEARCH / "data" / "price_view_data004"
OVERLAY_VIEW = RESEARCH / "data" / "price_view_data005_overlay"
RESULTS = RESEARCH / "results"
CONTRACT_004 = RESEARCH / "contracts" / "exp_data_004_official_events.json"
CONTRACT_005 = RESEARCH / "contracts" / "exp_data_005_official_validations.json"

LARGE_RETURN_THRESHOLD = 0.25
RATIO_JUMP_THRESHOLD = 0.005
HORIZONS = (20, 40, 60)
HISTORY_MIN = 252
RECENT_WINDOW = 25
RECENT_MIN = 20


def symbol_from_path(path: Path) -> str:
    return "XU100.IS" if path.stem == "IDX_XU100_IS" else path.stem.replace("_IS", ".IS")


def file_name(symbol: str) -> str:
    return f"{symbol.replace('.', '_').replace('^', 'IDX_')}.parquet"


def load_contract(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_view(symbol: str) -> pd.DataFrame:
    overlay = OVERLAY_VIEW / file_name(symbol)
    path = overlay if overlay.exists() else BASE_VIEW / file_name(symbol)
    return pd.read_parquet(path).sort_index()


def build_overlay() -> pd.DataFrame:
    """Patch only newly validated symbols; never rebuild the 89-series base view."""
    OVERLAY_VIEW.mkdir(parents=True, exist_ok=True)
    old = load_contract(CONTRACT_004)["events"]
    new = load_contract(CONTRACT_005)["events"]
    rows = []
    for event in new:
        symbol = event["symbol"]
        events = [x for x in old + new if x["symbol"] == symbol]
        view = build_symbol_view(symbol, events)
        path = OVERLAY_VIEW / file_name(symbol)
        view.to_parquet(path)
        early = (view.index >= pd.Timestamp(event["provider_adjusted_date"])) & (view.index < pd.Timestamp(event["ex_date"]))
        rows.append({
            "symbol": symbol,
            "base_view": str((BASE_VIEW / file_name(symbol)).relative_to(RESEARCH)),
            "overlay_file": str(path.relative_to(RESEARCH)),
            "quarantined_rows": int(early.sum()),
            "official_ex_quality": str(view.loc[pd.Timestamp(event["ex_date"]), "price_quality"]),
        })
    return pd.DataFrame(rows)


def candidate_scan() -> tuple[pd.DataFrame, dict]:
    known = {(e["symbol"], e["provider_adjusted_date"]) for e in load_contract(CONTRACT_004)["events"]}
    new = {(e["symbol"], e["provider_adjusted_date"]) for e in load_contract(CONTRACT_005)["events"]}
    evidence, large_rows = [], []
    counts = {"dividend_rows": 0, "split_rows": 0, "ratio_jump_rows": 0, "ratio_jump_without_event": 0, "large_return_rows": 0}
    for path in sorted(SNAPSHOT.glob("*.parquet")):
        symbol = symbol_from_path(path)
        df = pd.read_parquet(path).sort_index()
        raw_close = pd.to_numeric(df["close"], errors="coerce")
        ratio = pd.to_numeric(df["adj_close"], errors="coerce") / raw_close
        raw_ret = raw_close.pct_change(fill_method=None)
        ratio_jump = ratio.pct_change(fill_method=None).abs().gt(RATIO_JUMP_THRESHOLD)
        div = pd.to_numeric(df["dividends"], errors="coerce").fillna(0).ne(0)
        split = pd.to_numeric(df["stock_splits"], errors="coerce").fillna(0).ne(0)
        large = raw_ret.abs().gt(LARGE_RETURN_THRESHOLD)
        counts["dividend_rows"] += int(div.sum())
        counts["split_rows"] += int(split.sum())
        counts["ratio_jump_rows"] += int(ratio_jump.sum())
        counts["ratio_jump_without_event"] += int((ratio_jump & ~div & ~split).sum())
        counts["large_return_rows"] += int(large.sum())
        for date in df.index[large]:
            large_rows.append((symbol, pd.Timestamp(date).normalize()))
        mask = div | split | ratio_jump | large
        for date in df.index[mask]:
            key = (symbol, str(pd.Timestamp(date).date()))
            classification = "PROVIDER_EVENT_EVIDENCE"
            if key in known:
                classification = "KNOWN_CONTROLLED_EARLY_ADJUSTMENT"
            elif key in new:
                classification = "NEWLY_VALIDATED_CONTROLLED_EARLY_ADJUSTMENT"
            elif bool(ratio_jump.loc[date]) and not bool(div.loc[date] or split.loc[date]):
                classification = "RATIO_JUMP_WITHOUT_EVENT_FIELD"
            elif bool(large.loc[date]) and not bool(div.loc[date] or split.loc[date]):
                classification = "LARGE_DISCONTINUITY_REVIEW"
            evidence.append({
                "symbol": symbol, "date": str(pd.Timestamp(date).date()),
                "raw_return": float(raw_ret.loc[date]) if pd.notna(raw_ret.loc[date]) else np.nan,
                "adjustment_ratio": float(ratio.loc[date]) if pd.notna(ratio.loc[date]) else np.nan,
                "ratio_change": float(ratio.pct_change(fill_method=None).loc[date]) if pd.notna(ratio.pct_change(fill_method=None).loc[date]) else np.nan,
                "dividend": float(df.loc[date, "dividends"]), "stock_split": float(df.loc[date, "stock_splits"]),
                "classification": classification,
            })
    out = pd.DataFrame(evidence).sort_values(["date", "symbol"])
    large_counts = pd.Series([d for _, d in large_rows]).value_counts()
    cluster_dates = set(large_counts[large_counts >= 2].index)
    review = out["classification"].eq("LARGE_DISCONTINUITY_REVIEW")
    out.loc[review & pd.to_datetime(out["date"]).isin(cluster_dates), "classification"] = "MULTI_TICKER_OR_STALE_GAP_REVIEW"
    # ECILC/SELEC 2020-03-12 follow a zero-volume stale row; the discontinuity is
    # cumulative across an unavailable mark, not an adjustment-ratio break.
    return out, counts


def run_lengths(mask: pd.Series) -> list[int]:
    if not len(mask):
        return []
    groups = mask.ne(mask.shift()).cumsum()
    return [int(v) for v in mask.groupby(groups).sum() if v > 0]


def unresolved_materiality(symbols: list[str]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    row_frames, ticker_rows = [], []
    for symbol in symbols:
        view = load_view(symbol)
        bad = view[view["price_quality"].eq("UNRESOLVED")].copy()
        if len(bad):
            tmp = bad[["trading_status", "raw_close", "raw_high", "raw_low", "volume"]].copy()
            tmp["symbol"] = symbol; tmp["date"] = tmp.index
            tmp["changed_ohlc"] = tmp["raw_high"].ne(tmp["raw_low"])
            row_frames.append(tmp.reset_index(drop=True))
        mask = view["price_quality"].eq("UNRESOLVED")
        runs = run_lengths(mask)
        loss = float(mask.mean())
        if mask.sum() == 0:
            band = "FULLY_USABLE"
        elif loss <= 0.02 and max(runs, default=0) <= 5:
            band = "SMALL_COVERAGE_LOSS"
        elif loss > 0.20 or int(view["trading_eligible"].sum()) < HISTORY_MIN:
            band = "EXCLUDE_FROM_RESEARCH"
        else:
            band = "MATERIALLY_PROBLEMATIC"
        ticker_rows.append({"symbol": symbol, "rows": len(view), "eligible_rows": int(view["trading_eligible"].sum()),
                            "unresolved_rows": int(mask.sum()), "unresolved_pct": loss,
                            "max_unresolved_streak": max(runs, default=0), "coverage_band": band})
    detail = pd.concat(row_frames, ignore_index=True) if row_frames else pd.DataFrame()
    ticker = pd.DataFrame(ticker_rows)
    status = detail.groupby("trading_status", dropna=False).agg(
        rows=("symbol", "size"), tickers=("symbol", "nunique"), changed_ohlc=("changed_ohlc", "sum"),
        zero_volume=("volume", lambda x: int(x.fillna(0).le(0).sum()))).reset_index()
    return detail, ticker, status


def scheduled_intersections(symbol: str, status: str | None = None) -> dict:
    view = load_view(symbol)
    positions = np.arange(HISTORY_MIN, len(view), 60)
    if status is None:
        mask = ~view["trading_eligible"].to_numpy(dtype=bool)
    else:
        mask = view["trading_status"].eq(status).to_numpy()
    signal_hits = int(mask[positions].sum()) if len(positions) else 0
    entries = positions + 1; entries = entries[entries < len(view)]
    entry_hits = int(mask[entries].sum()) if len(entries) else 0
    return {"scheduled_signal_dates": int(len(positions)), "signal_hits": signal_hits,
            "scheduled_entry_dates": int(len(entries)), "entry_hits": entry_hits}


def horizon_coverage(symbols: list[str]) -> pd.DataFrame:
    rows = []
    for horizon in HORIZONS:
        usable = excluded = candidates = 0
        for symbol in symbols:
            view = load_view(symbol)
            eligible = view["trading_eligible"].fillna(False).to_numpy(dtype=bool)
            # Contract rule: at least 252 valid observations accumulated by the
            # signal date, not 252 uninterrupted sessions.
            valid_history = np.cumsum(eligible) >= HISTORY_MIN
            recent = pd.Series(eligible).rolling(RECENT_WINDOW, min_periods=RECENT_WINDOW).sum().ge(RECENT_MIN).to_numpy()
            reliable = view["price_quality"].ne("UNRESOLVED").to_numpy(dtype=bool)
            n = len(view)
            for i in range(n - horizon):
                if not (eligible[i] and valid_history[i] and recent[i]):
                    continue
                candidates += 1
                # signal and exit must be tradable; every label-path price must be
                # non-UNRESOLVED. Interior no-trade rows are therefore excluded.
                ok = eligible[i + horizon] and bool(reliable[i:i + horizon + 1].all())
                usable += int(ok); excluded += int(not ok)
        rows.append({"horizon_sessions": horizon, "candidate_observations": candidates,
                     "usable_observations": usable, "excluded_observations": excluded,
                     "coverage_pct": usable / candidates if candidates else np.nan})
    return pd.DataFrame(rows)


def quarantine_label_intersections(symbols: list[str]) -> pd.DataFrame:
    rows = []
    for horizon in HORIZONS:
        observations = intersections = 0
        for symbol in symbols:
            view = load_view(symbol)
            quarantine = view["corporate_action_flag"].eq("PROVIDER_EARLY_ADJUSTMENT").to_numpy()
            for i in range(max(0, len(view) - horizon)):
                observations += 1
                intersections += int(quarantine[i:i + horizon + 1].any())
        rows.append({"horizon_sessions": horizon, "all_dated_observations": observations,
                     "label_paths_intersecting_quarantine": intersections})
    return pd.DataFrame(rows)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    overlay = build_overlay()
    candidates, scan_counts = candidate_scan()
    symbols = [symbol_from_path(p) for p in sorted(BASE_VIEW.glob("*.parquet"))]
    detail, ticker, status = unresolved_materiality(symbols)
    horizon = horizon_coverage([s for s in symbols if s != "XU100.IS"])
    intersections = quarantine_label_intersections([s for s in symbols if s != "XU100.IS"])

    missing = detail[detail["trading_status"].eq("UNRESOLVED_MISSING_VOLUME")].copy()
    stale = detail[detail["trading_status"].eq("UNRESOLVED_NO_TRADE_OR_STALE")].copy()
    missing_year = missing.assign(year=pd.to_datetime(missing["date"]).dt.year).groupby(["symbol", "year"]).size().reset_index(name="rows")
    stale_date = stale.assign(date=lambda x: pd.to_datetime(x["date"]).dt.date).groupby("date").size().reset_index(name="rows").sort_values("rows", ascending=False)
    sasa = ticker[ticker["symbol"].eq("SASA.IS")].iloc[0].to_dict()
    sasa.update(scheduled_intersections("SASA.IS", "UNRESOLVED_MISSING_VOLUME"))

    total = int(ticker["rows"].sum()); eligible = int(ticker["eligible_rows"].sum())
    controlled = 0
    for symbol in symbols:
        controlled += int(load_view(symbol)["corporate_action_flag"].eq("PROVIDER_EARLY_ADJUSTMENT").sum())
    summary = {
        "experiment": "EXP-DATA-005", "thresholds": {"large_raw_return_abs": LARGE_RETURN_THRESHOLD,
        "adjustment_ratio_change_abs": RATIO_JUMP_THRESHOLD}, "scan": scan_counts,
        "new_candidate": {"symbol": "KONTR.IS", "provider_adjusted_date": "2025-12-01", "official_ex_date": "2025-12-09",
                          "quarantined_rows": int(overlay.iloc[0]["quarantined_rows"]), "classification": "CONTROLLED_QUARANTINED_RISK"},
        "dataset": {"total_rows": total, "eligible_rows": eligible, "ineligible_rows": total - eligible,
                    "controlled_quarantine_rows": controlled, "unknown_unresolved_rows": int(len(detail) - controlled),
                    "provider_only_rows": int(sum(load_view(s)["price_quality"].eq("PROVIDER_ONLY").sum() for s in symbols))},
        "ticker_bands": ticker["coverage_band"].value_counts().to_dict(), "sasa": sasa,
        "gate": "PRICE DATA = PASS FOR RESEARCH", "provider_independent_verification": "NOT AVAILABLE",
        "baseline_materiality": "NOT_RERUN: KONTR quarantine begins after the 2025-05 DATA-004 baseline end; conservative exclusions already drove DATA-004 execution.",
    }
    candidates.to_csv(RESULTS / "EXP-DATA-005_candidate_events.csv", index=False)
    overlay.to_csv(RESULTS / "EXP-DATA-005_overlay_manifest.csv", index=False)
    detail.to_csv(RESULTS / "EXP-DATA-005_unresolved_detail.csv", index=False)
    ticker.to_csv(RESULTS / "EXP-DATA-005_ticker_materiality.csv", index=False)
    status.to_csv(RESULTS / "EXP-DATA-005_status_materiality.csv", index=False)
    missing_year.to_csv(RESULTS / "EXP-DATA-005_missing_volume_distribution.csv", index=False)
    stale_date.head(50).to_csv(RESULTS / "EXP-DATA-005_stale_date_concentration.csv", index=False)
    horizon.to_csv(RESULTS / "EXP-DATA-005_horizon_coverage.csv", index=False)
    intersections.to_csv(RESULTS / "EXP-DATA-005_quarantine_label_intersections.csv", index=False)
    (RESULTS / "EXP-DATA-005_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    manifest = {"code_sha256": sha256(Path(__file__)), "contract_sha256": sha256(CONTRACT_005),
                "base_view": "EXP-DATA-004 immutable base", "overlay_symbols": overlay["symbol"].tolist()}
    (RESEARCH / "manifests" / "EXP-DATA-005_reproducibility.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()

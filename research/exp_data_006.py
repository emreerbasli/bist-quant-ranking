"""EXP-DATA-006 fundamental PIT, vintage and accounting integrity audit."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = Path(__file__).resolve().parent
FUND_DIR = ROOT / "data" / "fundamentals"
CACHE_DIR = ROOT / "data" / "raw" / "isyatirim_cache"
RAW_DIR = ROOT / "data" / "raw"
RESULTS = RESEARCH / "results"
POC_CONTRACT = RESEARCH / "contracts" / "exp_data_006_poc_official.json"

FLOW_FIELDS = ["satislar", "ebitda", "op_gelir", "net_kar", "cfo", "fcf"]
BALANCE_FIELDS = ["ozkaynaklar", "toplam_borc", "net_borc", "nakit", "toplam_aktif"]
VALUATION_FIELDS = ["piyasa_degeri", "pd_usd", "hao_pd", "pb", "ev", "ev_ebitda", "fcf_verim"]
DERIVED_PROFIT_FIELDS = ["roe", "roa", "ev_ebitda", "fcf_verim"]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_fundamentals() -> pd.DataFrame:
    frames = []
    for path in sorted(FUND_DIR.glob("*.parquet")):
        df = pd.read_parquet(path).copy()
        df["source_file"] = str(path.relative_to(ROOT))
        df["gecerlilik_tarihi"] = pd.to_datetime(df["gecerlilik_tarihi"])
        df["ceyrek_bitis"] = pd.to_datetime(df["ceyrek_bitis"])
        frames.append(df)
    out = pd.concat(frames, ignore_index=True, sort=False)
    return out.sort_values(["ticker", "ceyrek_bitis"]).reset_index(drop=True)


def raw_cache_metadata(ticker: str, year: int) -> dict:
    clean = ticker.replace(".IS", "")
    candidates = sorted(CACHE_DIR.glob(f"{clean}_{year}_*.json"))
    if not candidates:
        return {"raw_cache_file": None, "statement_type": "UNKNOWN", "download_date": None}
    path = candidates[0]
    group = path.stem.rsplit("_", 2)[-2:]
    statement_type = "XI_29" if "XI_29" in path.stem else ("UFRS" if "UFRS" in path.stem else "UNKNOWN")
    return {"raw_cache_file": str(path.relative_to(ROOT)), "statement_type": statement_type,
            "download_date": pd.Timestamp(path.stat().st_mtime, unit="s").isoformat()}


def provenance(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in df.iterrows():
        meta = raw_cache_metadata(r.ticker, int(r.ceyrek_bitis.year))
        rows.append({
            "ticker": r.ticker, "financial_period": r.ceyrek,
            "period_end": r.ceyrek_bitis.date().isoformat(), "statement_type": meta["statement_type"],
            "source": r.kaynak, "source_id": None, "source_url": None,
            "download_date_filesystem_proxy": meta["download_date"],
            "announcement_date": None, "announcement_timestamp": None,
            "availability_proxy_date": r.gecerlilik_tarihi.date().isoformat(),
            "pit_quality": "APPROXIMATE_FIXED_LAG", "first_or_restated": "UNKNOWN",
            "consolidation_basis": "UNKNOWN", "raw_cache_file": meta["raw_cache_file"],
            "raw_fields": ";".join(FLOW_FIELDS + BALANCE_FIELDS),
            "derived_fields": ";".join(["toplam_borc", "net_borc", "ebitda", "ihracat_orani", "piyasa_degeri", "pb", "roe", "roa", "ev", "ev_ebitda", "fcf_verim"]),
        })
    return pd.DataFrame(rows)


def pit_coverage(prov: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for year, g in [("ALL", prov)] + list(prov.assign(year=pd.to_datetime(prov.period_end).dt.year).groupby("year")):
        counts = g["pit_quality"].value_counts()
        total = len(g)
        row = {"period_end_year": year, "total": total}
        for status in ["EXACT_TIMESTAMP", "EXACT_DATE", "APPROXIMATE_FIXED_LAG", "UNKNOWN"]:
            row[status.lower()] = int(counts.get(status, 0))
            row[f"{status.lower()}_pct"] = float(counts.get(status, 0) / total) if total else 0.0
        rows.append(row)
    return pd.DataFrame(rows)


def vintage_audit(df: pd.DataFrame) -> pd.DataFrame:
    dup = df.groupby(["ticker", "ceyrek"]).size().rename("local_versions")
    out = df[["ticker", "ceyrek", "ceyrek_bitis", "gecerlilik_tarihi"]].copy()
    out["local_versions"] = [int(dup.loc[(t, q)]) for t, q in zip(out.ticker, out.ceyrek)]
    out["first_publication_recoverable_locally"] = False
    out["restatement_flag_available"] = False
    out["retained_vintage"] = "UNKNOWN_CURRENT_SNAPSHOT"
    out["latest_overwrite_risk"] = True
    return out


def period_semantics(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for field in FLOW_FIELDS:
        rows.append({"field": field, "class": "FLOW", "stored_semantics": "YTD_CUMULATIVE_3_6_9_12_MONTH",
                     "single_quarter_available": False, "ttm_available": False,
                     "non_null_rows": int(df[field].notna().sum()), "risk": "LEGACY_NAME_DOES_NOT_ENCODE_YTD; NO_Q2_Q3_Q4_DECOMPOSITION"})
    for field in BALANCE_FIELDS:
        rows.append({"field": field, "class": "BALANCE", "stored_semantics": "POINT_IN_TIME_PERIOD_END",
                     "single_quarter_available": False, "ttm_available": False,
                     "non_null_rows": int(df[field].notna().sum()), "risk": "PIT_AND_VINTAGE_STILL_PROXY_UNKNOWN"})
    for field in DERIVED_PROFIT_FIELDS + ["ihracat_orani"]:
        rows.append({"field": field, "class": "DERIVED", "stored_semantics": "MIXED_YTD_FLOW_AND_POINT_IN_TIME_DENOMINATOR",
                     "single_quarter_available": False, "ttm_available": False,
                     "non_null_rows": int(df[field].notna().sum()), "risk": "NOT_COMPARABLE_ACROSS_QUARTERS_WITHOUT_EXPLICIT_TRANSFORM"})
    return pd.DataFrame(rows).drop_duplicates("field")


def capital_audit(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows, signal_rows = [], []
    tekil_cache: dict[str, pd.DataFrame] = {}
    price_cache: dict[str, pd.Series] = {}
    for _, r in df.iterrows():
        clean = r.ticker.replace(".IS", "")
        tekil_path = CACHE_DIR / f"{clean}_tekil.parquet"
        if clean not in tekil_cache:
            tekil_cache[clean] = pd.read_parquet(tekil_path).sort_index() if tekil_path.exists() else pd.DataFrame()
        tekil = tekil_cache[clean]
        t = pd.Timestamp(r.gecerlilik_tarihi)
        pd_val = np.nan; market_date = pd.NaT; source = "MISSING"
        historical_cap_available = False; fallback_cap_date = pd.NaT; fallback_capital = np.nan
        if not tekil.empty:
            prior = tekil[tekil.index <= t]
            if "SERMAYE" in tekil:
                prior_cap = prior["SERMAYE"].dropna() if not prior.empty else pd.Series(dtype=float)
                historical_cap_available = bool(len(prior_cap))
                all_cap = tekil["SERMAYE"].dropna()
                if len(all_cap):
                    fallback_cap_date = pd.Timestamp(all_cap.index[-1])
                    fallback_capital = float(all_cap.iloc[-1])
            if not prior.empty:
                market_date = pd.Timestamp(prior.index[-1])
                pd_val = pd.to_numeric(pd.Series([prior.iloc[-1].get("PD", np.nan)]), errors="coerce").iloc[0]
                if pd.notna(pd_val) and pd_val > 0:
                    source = "HISTORICAL_HISSETEKIL_PD"
        raw_price_path = RAW_DIR / f"{r.ticker.replace('.', '_')}.parquet"
        raw_price_available = False
        if (pd.isna(pd_val) or pd_val <= 0) and raw_price_path.exists() and not tekil.empty and "SERMAYE" in tekil:
            if clean not in price_cache:
                price_cache[clean] = pd.read_parquet(raw_price_path)["close"].sort_index()
            price = price_cache[clean]
            prior_price = price[price.index <= t]
            all_cap = tekil["SERMAYE"].dropna()
            raw_price_available = bool(len(prior_price))
            if len(prior_price) and len(all_cap):
                source = "RAW_PRICE_X_LATEST_CAPITAL_FALLBACK"
        future_fallback = bool(source == "RAW_PRICE_X_LATEST_CAPITAL_FALLBACK" and pd.notna(fallback_cap_date) and fallback_cap_date > t)
        if source == "RAW_PRICE_X_LATEST_CAPITAL_FALLBACK" or source == "MISSING":
            rows.append({"ticker": r.ticker, "financial_period": r.ceyrek, "availability_proxy_date": t.date().isoformat(),
                         "historical_capital_available": historical_cap_available, "fallback_capital_source_date": fallback_cap_date.date().isoformat() if pd.notna(fallback_cap_date) else None,
                         "fallback_capital": fallback_capital, "market_cap_source": source,
                         "future_last_capital_fallback": future_fallback,
                         "affected_fields": "piyasa_degeri;pb;ev;ev_ebitda;fcf_verim"})
        signal_rows.append({"ticker": r.ticker, "financial_period": r.ceyrek,
                            "financial_availability_proxy": t.date().isoformat(),
                            "market_value_observation_date": market_date.date().isoformat() if pd.notna(market_date) else None,
                            "market_cap_source": source, "valuation_recomputed_on_each_signal_date": False,
                            "carry_forward_status": "STALE_AFTER_PROXY_DATE",
                            "signal_date_valuation_consistent": False})
    return pd.DataFrame(rows), pd.DataFrame(signal_rows)


def field_status(df: pd.DataFrame, capital: pd.DataFrame) -> pd.DataFrame:
    fallback_keys = set(zip(capital.loc[capital.future_last_capital_fallback, "ticker"], capital.loc[capital.future_last_capital_fallback, "financial_period"]))
    fields = FLOW_FIELDS + BALANCE_FIELDS + ["ihracat_orani", "roe", "roa", "piyasa_degeri", "pb", "ev", "ev_ebitda", "fcf_verim", "tfrs29"]
    rows = []
    for _, r in df.iterrows():
        for field in fields:
            value = r.get(field, np.nan)
            if pd.isna(value):
                status, reason = "MISSING", "SOURCE_VALUE_UNAVAILABLE_OR_NOT_APPLICABLE"
            elif field == "tfrs29":
                status, reason = "INVALID", "MECHANICAL_DATE_FLAG_NOT_ACCOUNTING_BASIS_METADATA"
            elif field in ["roe", "roa", "ev_ebitda", "fcf_verim"]:
                status, reason = "INVALID", "YTD_FLOW_MIXED_WITH_POINT_IN_TIME_OR_SIGNAL_DATE_DENOMINATOR"
            elif field in ["piyasa_degeri", "pb", "ev"] and (r.ticker, r.ceyrek) in fallback_keys:
                status, reason = "INVALID", "FUTURE_LATEST_CAPITAL_FALLBACK"
            else:
                status, reason = "PROXY_UNVERIFIED", "FIXED_LAG_AND_VINTAGE_UNKNOWN"
            rows.append({"ticker": r.ticker, "financial_period": r.ceyrek, "field": field,
                         "status": status, "reason": reason})
    return pd.DataFrame(rows)


def family_readiness(df: pd.DataFrame, status: pd.DataFrame) -> pd.DataFrame:
    families = {
        "QUALITY": ["roe", "roa", "net_kar", "ozkaynaklar", "toplam_aktif"],
        "PROFITABILITY": ["satislar", "op_gelir", "ebitda", "net_kar"],
        "CASH_FLOW": ["cfo", "fcf", "fcf_verim"],
        "BALANCE_SHEET": BALANCE_FIELDS,
        "EARNINGS": ["net_kar", "satislar", "op_gelir"],
        "VALUE": ["piyasa_degeri", "pb", "ev", "ev_ebitda", "fcf_verim"],
    }
    rows = []
    for family, fields in families.items():
        available = df[fields].notna().any(axis=1)
        tickers = df.loc[available, "ticker"].nunique()
        years = df.loc[available, "ceyrek_bitis"].dt.year.nunique()
        fam_status = status[status.field.isin(fields)]
        counts = fam_status.status.value_counts()
        decision = "PARTIAL"
        if family == "VALUE":
            decision = "FAIL_CURRENT_STORED_RATIOS"
        rows.append({"feature_family": family, "row_coverage": int(available.sum()),
                     "row_coverage_pct": float(available.mean()), "ticker_coverage": int(tickers),
                     "year_coverage": int(years), "pit_quality": "APPROXIMATE_FIXED_LAG",
                     "vintage_quality": "UNKNOWN_CURRENT_SNAPSHOT", "accounting_semantics_quality": "PARTIAL" if family != "VALUE" else "INVALID_FOR_CARRY_FORWARD",
                     "historical_capital_dependency": family == "VALUE",
                     "verified_cells": int(counts.get("VERIFIED", 0)), "proxy_cells": int(counts.get("PROXY_UNVERIFIED", 0)),
                     "invalid_cells": int(counts.get("INVALID", 0)), "missing_cells": int(counts.get("MISSING", 0)),
                     "research_status": decision})
    return pd.DataFrame(rows)


def sector_applicability(df: pd.DataFrame) -> pd.DataFrame:
    financial = df.groupby("ticker")["is_bank"].max()
    rows = []
    for metric in ["ROIC", "NET_DEBT_EBITDA", "FCF", "EBITDA_MARGIN", "ROE", "PB"]:
        rows.append({"metric": metric, "industrial": "APPLICABLE_WITH_SEMANTIC_REPAIR",
                     "bank_or_insurance": "NOT_APPLICABLE" if metric in {"ROIC", "NET_DEBT_EBITDA", "FCF", "EBITDA_MARGIN"} else "APPLICABLE_WITH_SECTOR_SCHEMA",
                     "financial_tickers": int(financial.sum()), "industrial_tickers": int((~financial).sum()),
                     "missing_policy": "PRESERVE_MISSING; NEVER ZERO_IMPUTE_AS_ECONOMIC_VALUE"})
    return pd.DataFrame(rows)


def missing_zero_scan() -> pd.DataFrame:
    files = [ROOT / "features" / "fundamental_pit.py", ROOT / "features" / "temel_analiz.py",
             ROOT / "models" / "v3_ranking" / "ranking_pipeline.py", ROOT / "models" / "v4_ranking" / "ranking_pipeline_v4.py"]
    pattern = re.compile(r"fillna\(0(?:\.0)?\)|\.get\([^\n]+,\s*0(?:\.0)?\)|or\s+0\.0")
    rows = []
    for path in files:
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.search(line):
                rows.append({"file": str(path.relative_to(ROOT)), "line": lineno, "code": line.strip(),
                             "risk": "MISSING_CONVERTED_TO_NEUTRAL_OR_ZERO"})
    return pd.DataFrame(rows)


def poc_results(df: pd.DataFrame) -> pd.DataFrame:
    contract = json.loads(POC_CONTRACT.read_text(encoding="utf-8"))["observations"]
    rows = []
    for item in contract:
        local = df[(df.ticker == item["ticker"]) & (df.ceyrek == item["period"])]
        local_value = float(local.iloc[0].net_kar) if len(local) and pd.notna(local.iloc[0].net_kar) else np.nan
        exact = item["evidence_grade"] == "EXACT_FINANCIAL_REPORT"
        rows.append({**item, "local_record_found": bool(len(local)), "accepted_exact_recovery": exact,
                     "local_net_profit_try": local_value,
                     "official_vs_local_value_difference_try": (local_value - item.get("official_net_profit_ytd_thousand_try", np.nan) * 1000) if exact else np.nan})
    return pd.DataFrame(rows)


def local_recovery_inventory() -> pd.DataFrame:
    json_files = list(CACHE_DIR.glob("*.json"))
    tekil_files = list(CACHE_DIR.glob("*_tekil.parquet"))
    yf_files = list((RAW_DIR / "yf_pit_cache").glob("*.parquet"))
    return pd.DataFrame([
        {"artifact": "data/fundamentals/*.parquet", "files": len(list(FUND_DIR.glob("*.parquet"))),
         "notification_id": False, "disclosure_timestamp": False, "vintage_history": False,
         "period_mapping": True, "recovery_use": "DERIVED_DATASET_ONLY_FIXED_LAG"},
        {"artifact": "data/raw/isyatirim_cache/*_{year}_{group}.json", "files": len(json_files),
         "notification_id": False, "disclosure_timestamp": False, "vintage_history": False,
         "period_mapping": True, "recovery_use": "RAW_CURRENT_SNAPSHOT_VALUES_ONLY"},
        {"artifact": "data/raw/isyatirim_cache/*_tekil.parquet", "files": len(tekil_files),
         "notification_id": False, "disclosure_timestamp": False, "vintage_history": False,
         "period_mapping": False, "recovery_use": "DATED_MARKET_CAP_AND_CAPITAL_ONLY"},
        {"artifact": "data/raw/yf_pit_cache/*.parquet", "files": len(yf_files),
         "notification_id": False, "disclosure_timestamp": False, "vintage_history": False,
         "period_mapping": True, "recovery_use": "ALTERNATE_45_DAY_PROXY_NOT_PROVENANCE"},
        {"artifact": "data/events.csv", "files": int((ROOT / "data" / "events.csv").exists()),
         "notification_id": False, "disclosure_timestamp": False, "vintage_history": False,
         "period_mapping": False, "recovery_use": "SYNTHETIC_CALENDAR_NOT_COMPANY_FILINGS"},
        {"artifact": "scripts/kap_*.html and KAP scripts", "files": len(list((ROOT / "scripts").glob("kap_*.html"))),
         "notification_id": False, "disclosure_timestamp": False, "vintage_history": False,
         "period_mapping": False, "recovery_use": "AD_HOC_PAGES; EXISTING API SCRIPT_TIMED_OUT"},
        {"artifact": "targeted official KAP HTTP proof", "files": 0,
         "notification_id": True, "disclosure_timestamp": True, "vintage_history": "SINGLE_FILING_ONLY",
         "period_mapping": True, "recovery_use": "ACCURATE_PER_FILING_BUT_NOT_LOCALLY_INDEXED_OR_SCALABLE_YET"},
    ])


def main() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    df = load_fundamentals()
    prov = provenance(df)
    pit = pit_coverage(prov)
    vintage = vintage_audit(df)
    semantics = period_semantics(df)
    capital, signal = capital_audit(df)
    statuses = field_status(df, capital)
    families = family_readiness(df, statuses)
    sectors = sector_applicability(df)
    zero_scan = missing_zero_scan()
    poc = poc_results(df)
    recovery = local_recovery_inventory()

    outputs = {
        "EXP-DATA-006_provenance.csv": prov,
        "EXP-DATA-006_pit_coverage.csv": pit,
        "EXP-DATA-006_vintage_audit.csv": vintage,
        "EXP-DATA-006_period_semantics.csv": semantics,
        "EXP-DATA-006_capital_fallback.csv": capital,
        "EXP-DATA-006_signal_date_valuation.csv": signal,
        "EXP-DATA-006_field_status.csv": statuses,
        "EXP-DATA-006_feature_family_readiness.csv": families,
        "EXP-DATA-006_sector_applicability.csv": sectors,
        "EXP-DATA-006_missing_zero_findings.csv": zero_scan,
        "EXP-DATA-006_poc_official_validation.csv": poc,
        "EXP-DATA-006_local_recovery_inventory.csv": recovery,
    }
    for name, table in outputs.items():
        table.to_csv(RESULTS / name, index=False)

    tfrs_rows = int((df.tfrs29 == True).sum())
    summary = {
        "experiment": "EXP-DATA-006", "records": int(len(df)), "tickers": int(df.ticker.nunique()),
        "pit_quality": prov.pit_quality.value_counts().to_dict(),
        "local_duplicate_ticker_period_rows": int(df.duplicated(["ticker", "ceyrek"], keep=False).sum()),
        "vintage_unknown_rows": int(len(vintage)), "tfrs29_mechanical_flag_rows": tfrs_rows,
        "market_cap_fallback_candidate_or_missing_rows": int(len(capital)),
        "future_latest_capital_fallback_rows": int(capital.future_last_capital_fallback.sum()),
        "signal_date_dynamic_valuation_rows": int(signal.valuation_recomputed_on_each_signal_date.sum()),
        "missing_to_zero_code_findings": int(len(zero_scan)),
        "poc_exact_financial_reports": int(poc.accepted_exact_recovery.sum()),
        "field_status_cells": statuses.status.value_counts().to_dict(),
        "family_decisions": dict(zip(families.feature_family, families.research_status)),
        "readiness": {"QUALITY_FEATURES": "PARTIAL", "CASH_FLOW_FEATURES": "PARTIAL",
                      "BALANCE_SHEET_FEATURES": "PARTIAL", "EARNINGS_FEATURES": "PARTIAL",
                      "VALUE_FEATURES": "NO_CURRENT_STORED_RATIOS", "FULL_FUNDAMENTAL_ML": "NO"},
        "gate": "FUNDAMENTAL DATA = PARTIAL",
    }
    (RESULTS / "EXP-DATA-006_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest = {"code_sha256": sha256(Path(__file__)), "poc_contract_sha256": sha256(POC_CONTRACT),
                "source_fundamental_files": len(list(FUND_DIR.glob("*.parquet"))),
                "source_records": len(df), "production_data_written": False}
    (RESEARCH / "manifests" / "EXP-DATA-006_reproducibility.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

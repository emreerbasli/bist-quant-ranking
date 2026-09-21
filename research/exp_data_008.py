"""EXP-DATA-008: staged, resumable KAP PIT/vintage reconstruction.

Research-only. The locked legacy universe and methodology live in
contracts/exp_data_008_bulk.json. Production datasets are never written.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from datetime import datetime, time as dt_time, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import requests
from bs4 import BeautifulSoup

try:
    from research.exp_data_007 import (
        DETAIL_URL, FIELD_CODES, LIST_URL, classify_consolidation,
        exact_report_candidates, list_payload, parse_number,
        presentation_unit_info, select_lineage, timing_quality,
    )
except ModuleNotFoundError:  # Supports direct `python research/exp_data_008.py` execution.
    from exp_data_007 import (  # type: ignore
        DETAIL_URL, FIELD_CODES, LIST_URL, classify_consolidation,
        exact_report_candidates, list_payload, parse_number,
        presentation_unit_info, select_lineage, timing_quality,
    )

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / "research"
CONTRACT_PATH = RESEARCH / "contracts" / "exp_data_008_bulk.json"
FUND_DIR = ROOT / "data" / "fundamentals"
CACHE = RESEARCH / "cache" / "exp_data_008"
PILOT_CACHE = RESEARCH / "cache" / "exp_data_007"
CHECKPOINTS = RESEARCH / "checkpoints" / "exp_data_008"
RESULTS = RESEARCH / "results"
MANIFESTS = RESEARCH / "manifests"
MEMBERS_URL = "https://www.kap.org.tr/tr/sirketler/ALL"

LOCAL_FIELDS = {
    "revenue": "satislar",
    "operating_profit": "op_gelir",
    "ebitda": "ebitda",
    "net_income": "net_kar",
    "equity": "ozkaynaklar",
    "cfo": "cfo",
    "fcf": "fcf",
}
INSURERS = {"ANSGR", "TURSG"}


class BatchStop(RuntimeError):
    pass


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def atomic_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_bytes(content)
    temp.replace(path)


def cache_read(path: Path) -> bytes:
    content = path.read_bytes()
    digest = sha256_bytes(content)
    sidecar = path.with_suffix(path.suffix + ".sha256")
    if sidecar.exists() and sidecar.read_text(encoding="ascii").strip() != digest:
        raise BatchStop(f"CACHE_HASH_MISMATCH:{path}")
    if not sidecar.exists():
        atomic_bytes(sidecar, (digest + "\n").encode("ascii"))
    return content


def cache_write(path: Path, content: bytes) -> None:
    atomic_bytes(path, content)
    atomic_bytes(path.with_suffix(path.suffix + ".sha256"), (sha256_bytes(content) + "\n").encode("ascii"))


def request_cached(
    session: requests.Session,
    method: str,
    url: str,
    cache_path: Path,
    stats: dict[str, int],
    contract: dict[str, Any],
    payload: dict[str, Any] | None = None,
    pilot_fallback: Path | None = None,
    offline: bool = False,
) -> bytes:
    stats["logical_requests"] += 1
    if cache_path.exists():
        stats["cache_hits"] += 1
        return cache_read(cache_path)
    if pilot_fallback and pilot_fallback.exists():
        content = pilot_fallback.read_bytes()
        cache_write(cache_path, content)
        stats["pilot_cache_seed_hits"] += 1
        return content
    if offline:
        raise FileNotFoundError(f"OFFLINE_CACHE_MISS:{cache_path}")

    pauses = contract["execution"]["retry_pauses_seconds"]
    response = None
    for attempt, pause in enumerate(pauses):
        if pause:
            time.sleep(float(pause))
        stats["network_attempts"] += 1
        response = session.request(method, url, json=payload, timeout=90)
        if response.status_code == 429:
            stats["http_429"] += 1
            stats["retries"] += int(attempt < len(pauses) - 1)
            if stats["http_429"] > contract["stop_conditions"]["http_429_count_per_batch_max"]:
                raise BatchStop("HTTP_429_BATCH_LIMIT")
            continue
        response.raise_for_status()
        cache_write(cache_path, response.content)
        time.sleep(float(contract["execution"]["minimum_uncached_request_interval_seconds"]))
        return response.content
    assert response is not None
    response.raise_for_status()
    raise RuntimeError("unreachable")


def canonical_universe() -> tuple[pd.DataFrame, str]:
    rows: list[dict[str, Any]] = []
    for path in sorted(FUND_DIR.glob("*.parquet")):
        frame = pd.read_parquet(path)
        for item in frame.to_dict("records"):
            ticker = str(item["ticker"])
            rows.append({
                "legacy_observation_id": f"{ticker}:{item['ceyrek']}",
                "ticker": ticker,
                "kap_ticker": ticker.strip().replace(".IS", ""),
                "financial_period": str(item["ceyrek"]),
                "period_end": pd.Timestamp(item["ceyrek_bitis"]).date().isoformat(),
                "legacy_available_date": pd.Timestamp(item["gecerlilik_tarihi"]).date().isoformat(),
                "legacy_source_file": path.relative_to(ROOT).as_posix(),
                "legacy_sector": str(item.get("sektor", "UNKNOWN")),
                "legacy_is_bank": bool(item.get("is_bank", False)),
                **{f"local_{name}": clean_number(item.get(column)) for name, column in LOCAL_FIELDS.items()},
            })
    frame = pd.DataFrame(rows).sort_values("legacy_observation_id").reset_index(drop=True)
    hash_rows = frame[["legacy_observation_id", "ticker", "financial_period", "period_end", "legacy_available_date", "legacy_source_file"]].rename(
        columns={"legacy_source_file": "source_file"}
    )
    payload = "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        for row in hash_rows.to_dict("records")
    ).encode("utf-8")
    return frame, sha256_bytes(payload)


def clean_number(value: Any) -> float | None:
    try:
        return None if pd.isna(value) else float(value)
    except (TypeError, ValueError):
        return None


def accounting_type(row: pd.Series | dict[str, Any]) -> str:
    ticker = str(row["kap_ticker"])
    if ticker in INSURERS:
        return "INSURANCE"
    if bool(row["legacy_is_bank"]):
        return "BANK"
    return "INDUSTRIAL_OR_HOLDING"


def preferred_basis(kind: str) -> str:
    return "NON_CONSOLIDATED" if kind in {"BANK", "INSURANCE"} else "CONSOLIDATED"


def parse_member_inventory(content: bytes) -> dict[str, str]:
    text = content.decode("utf-8", errors="replace")
    pattern = re.compile(
        r'mkkMemberOid\\":\\"([0-9a-f]{32})\\".*?stockCode\\":\\"([^"\\]*)\\"',
        re.I,
    )
    mapping: dict[str, str] = {}
    for oid, stock_codes in pattern.findall(text):
        for code in re.split(r"[,;/\s]+", stock_codes):
            if code:
                mapping.setdefault(code.strip().upper(), oid)
    return mapping


def trading_sessions() -> pd.DatetimeIndex:
    frame = pd.read_parquet(ROOT / "data" / "raw" / "XU100_IS.parquet")
    index = pd.DatetimeIndex(frame.index).tz_localize(None).normalize().unique().sort_values()
    return index


def available_from(timestamp_text: str | None, sessions: pd.DatetimeIndex) -> str | None:
    if not timestamp_text:
        return None
    parsed = pd.to_datetime(timestamp_text, dayfirst=True, errors="coerce")
    if pd.isna(parsed):
        return None
    # Contract is deliberately conservative: first session close strictly after
    # the disclosure instant/date, even when publication occurred intraday.
    candidates = sessions[sessions > parsed.normalize()]
    if not len(candidates):
        return None
    return datetime.combine(candidates[0].date(), dt_time(18, 10)).isoformat()


def extract_context_values(row: Any) -> list[float | None]:
    cells = row.find_all("td", class_=lambda value: value and "taxonomy-context-value" in value)
    return [parse_number(cell.get_text(" ", strip=True), 1) for cell in cells]


def choose_xbrl_row(soup: BeautifulSoup, codes: Iterable[str]) -> dict[str, Any]:
    for code in codes:
        for row in soup.find_all("tr"):
            first = row.find("td", class_="taxonomy-field-name-cell")
            if not first:
                continue
            raw_label = first.get_text(" ", strip=True)
            raw_code = raw_label.split("|", 1)[0]
            if raw_code != code:
                continue
            if code == "ifrs-full_Equity" and "period" in raw_label.casefold():
                continue
            values = extract_context_values(row)
            if values:
                return {"xbrl_code": raw_code, "raw_label": raw_label, "raw_values": values}
    return {"xbrl_code": None, "raw_label": None, "raw_values": []}


def parse_detail(content: bytes, notification_id: int) -> dict[str, Any]:
    soup = BeautifulSoup(content, "html.parser")
    text = soup.get_text(" ", strip=True)
    unit = presentation_unit_info(soup)
    basis = "UNKNOWN"
    for row in soup.find_all("tr"):
        row_text = row.get_text(" ", strip=True)
        if "Finansal Tablo Niteli" in row_text or "Financial Statement Type" in row_text:
            basis = classify_consolidation(row_text)
            break
    fields: dict[str, Any] = {}
    for field, codes in FIELD_CODES.items():
        selected = choose_xbrl_row(soup, codes)
        raw_values = selected["raw_values"]
        multiplier = unit["multiplier"]
        normalized = [value * multiplier if value is not None and multiplier is not None else None for value in raw_values]
        fields[field] = {
            **selected,
            "current_raw_value": raw_values[0] if raw_values else None,
            "current_normalized_try": normalized[0] if normalized else None,
            "comparative_normalized_try": normalized[1] if len(normalized) > 1 else None,
        }
    return {
        "notification_id": notification_id,
        "source_url": DETAIL_URL.format(notification_id=notification_id),
        "consolidated_flag": basis,
        "unit_status": unit["status"],
        "unit_labels": unit["labels"],
        "unit_multiplier": unit["multiplier"],
        "correction_marker": bool(re.search(r"Düzeltilmiş Bildirim|Corrected Notification", text, re.I)),
        "tfrs29_mentioned": bool(re.search(r"TFRS\s*29|TMS\s*29|enflasyon muhasebes", text, re.I)),
        "fields": fields,
    }


def tfrs29_status(period: str, kind: str, mentioned: bool) -> str:
    if period < "2023Q4":
        return "PRE_TFRS29"
    if kind == "BANK":
        return "BANK_BDDK_NOT_APPLIED"
    if mentioned:
        return "POST_TFRS29_CONFIRMED"
    return "POST_TFRS29_UNKNOWN_COMPARATIVE"


def field_semantic(field: str, period: str) -> str:
    if field == "equity":
        return "BALANCE_SHEET_POINT_IN_TIME"
    return "FLOW_ANNUAL" if period.endswith("Q4") else "FLOW_YTD"


def local_comparison(field: str, local: float | None, official: float | None, contract: dict[str, Any]) -> dict[str, Any]:
    conditional = field in set(contract["local_comparison"]["conditionally_comparable_fields"])
    if local is None:
        return {"absolute_difference_try": None, "relative_difference_pct": None, "numeric_class": "MISSING_LOCAL", "audit_class": "MISSING_LOCAL"}
    if official is None:
        return {"absolute_difference_try": None, "relative_difference_pct": None, "numeric_class": "MISSING_OFFICIAL", "audit_class": "MISSING_OFFICIAL"}
    absolute = local - official
    relative = None if official == 0 else absolute / abs(official) * 100
    if abs(absolute) <= contract["local_comparison"]["exact_absolute_tolerance_try"]:
        numeric = "EXACT_MATCH"
    elif relative is not None and abs(relative) <= contract["local_comparison"]["small_absolute_relative_difference_pct_max"]:
        numeric = "SMALL_DIFFERENCE"
    else:
        numeric = "MATERIAL_DIFFERENCE"
    return {
        "absolute_difference_try": absolute,
        "relative_difference_pct": relative,
        "numeric_class": numeric,
        "audit_class": "SEMANTIC_MISMATCH" if conditional else numeric,
    }


def new_stats() -> dict[str, int]:
    return {key: 0 for key in ["logical_requests", "network_attempts", "cache_hits", "pilot_cache_seed_hits", "http_429", "retries", "source_errors", "parse_errors"]}


def fetch_json_list(session: requests.Session, oid: str, ticker: str, year: int, stats: dict[str, int], contract: dict[str, Any], offline: bool) -> list[dict[str, Any]]:
    file_name = f"{ticker}_{year}.json"
    content = request_cached(
        session, "POST", LIST_URL, CACHE / "list" / file_name, stats, contract,
        payload=list_payload(oid, year),
        pilot_fallback=PILOT_CACHE / "list" / f"{ticker}_IS_{year}.json",
        offline=offline,
    )
    data = json.loads(content.decode("utf-8"))
    if not isinstance(data, list):
        raise ValueError("KAP_LIST_NOT_ARRAY")
    return data


def fetch_detail(session: requests.Session, notification_id: int, stats: dict[str, int], contract: dict[str, Any], offline: bool) -> dict[str, Any]:
    content = request_cached(
        session, "GET", DETAIL_URL.format(notification_id=notification_id),
        CACHE / "detail" / f"{notification_id}.html", stats, contract,
        pilot_fallback=PILOT_CACHE / "detail" / f"{notification_id}.html",
        offline=offline,
    )
    return parse_detail(content, notification_id)


def period_number(period: str) -> int:
    return int(period[-1])


def process_ticker(
    ticker_rows: pd.DataFrame,
    oid: str | None,
    session: requests.Session,
    sessions: pd.DatetimeIndex,
    stats: dict[str, int],
    contract: dict[str, Any],
    offline: bool,
) -> dict[str, Any]:
    observations: list[dict[str, Any]] = []
    candidates_out: list[dict[str, Any]] = []
    fields_out: list[dict[str, Any]] = []
    comparisons: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    kap_ticker = str(ticker_rows.iloc[0].kap_ticker)
    if not oid:
        for row in ticker_rows.to_dict("records"):
            observations.append(base_failed_observation(row, "SOURCE_ERROR", "MISSING_MEMBER_OID"))
        return {"observations": observations, "candidates": [], "fields": [], "comparisons": [], "failures": [{"ticker": kap_ticker, "stage": "MEMBER_MAPPING", "reason": "MISSING_MEMBER_OID"}]}

    required_years: set[int] = set()
    max_year = datetime.now().year
    for period in ticker_rows.financial_period:
        year = int(str(period)[:4])
        required_years.add(year)
        if year + 1 <= max_year:
            required_years.add(year + 1)
    listings: list[dict[str, Any]] = []
    list_failed = False
    for year in sorted(required_years):
        try:
            listings.extend(fetch_json_list(session, oid, kap_ticker, year, stats, contract, offline))
        except BatchStop:
            raise
        except Exception as exc:
            stats["source_errors"] += 1
            list_failed = True
            failures.append({"ticker": kap_ticker, "stage": "LIST", "year": year, "reason": repr(exc)})
    listings = list({int(item["disclosureIndex"]): item for item in listings if item.get("disclosureIndex")}.values())

    detail_cache: dict[int, dict[str, Any]] = {}
    for row in ticker_rows.to_dict("records"):
        obs_id = row["legacy_observation_id"]
        kind = accounting_type(row)
        basis = preferred_basis(kind)
        exact = exact_report_candidates(listings, f"{kap_ticker}.IS", row["financial_period"])
        enriched: list[dict[str, Any]] = []
        detail_failed = False
        for item in exact:
            notification_id = int(item["disclosureIndex"])
            try:
                if notification_id not in detail_cache:
                    detail_cache[notification_id] = fetch_detail(session, notification_id, stats, contract, offline)
                enriched.append({**item, **detail_cache[notification_id]})
            except BatchStop:
                raise
            except Exception as exc:
                stats["parse_errors"] += 1
                detail_failed = True
                failures.append({"legacy_observation_id": obs_id, "ticker": kap_ticker, "stage": "DETAIL", "notification_id": notification_id, "reason": repr(exc)})
        lineage, mapping_failure = select_lineage(enriched, basis)
        first = lineage[0] if lineage else None
        latest = lineage[-1] if lineage else None
        for candidate in enriched:
            candidates_out.append({
                "legacy_observation_id": obs_id,
                "ticker": row["ticker"],
                "kap_ticker": kap_ticker,
                "financial_period": row["financial_period"],
                "notification_id": candidate.get("disclosureIndex"),
                "publication_timestamp": candidate.get("publishDate"),
                "consolidation_basis": candidate.get("consolidated_flag"),
                "preferred_basis": basis,
                "basis_match": candidate.get("consolidated_flag") == basis,
                "modify_status": candidate.get("modifyStatus"),
                "correction_marker": candidate.get("correction_marker"),
                "unit_status": candidate.get("unit_status"),
                "source_url": candidate.get("source_url"),
            })
        if not first:
            status = "SOURCE_ERROR" if (list_failed or detail_failed) else ("AMBIGUOUS" if exact else "UNRECOVERABLE")
            observations.append(base_failed_observation(row, status, mapping_failure or status, kind, basis))
            failures.append({"legacy_observation_id": obs_id, "ticker": kap_ticker, "stage": "MAPPING", "reason": mapping_failure or status})
            continue

        timing = timing_quality(first.get("publishDate"))
        unit_status = first.get("unit_status", "UNKNOWN")
        status = "RECOVERED_EXACT" if timing == "EXACT_TIMESTAMP" and unit_status == "RESOLVED" else (
            "RECOVERED_DATE_ONLY" if timing == "EXACT_DATE" and unit_status == "RESOLVED" else "PARTIAL_METADATA"
        )
        vintage_count = len(lineage)
        vintage_status = "FIRST_ONLY" if vintage_count == 1 else ("FIRST_PLUS_CORRECTION" if vintage_count == 2 else "MULTIPLE_REVISIONS")
        tfrs = tfrs29_status(row["financial_period"], kind, bool(first.get("tfrs29_mentioned")))
        correction_ids = [int(item["disclosureIndex"]) for item in lineage[1:]]
        observations.append({
            "legacy_observation_id": obs_id,
            "ticker": row["ticker"],
            "kap_ticker": kap_ticker,
            "financial_period": row["financial_period"],
            "period_end": row["period_end"],
            "statement_type": "ANNUAL" if row["financial_period"].endswith("Q4") else "INTERIM",
            "accounting_type": kind,
            "legacy_sector": row["legacy_sector"],
            "consolidation_basis": first.get("consolidated_flag"),
            "preferred_basis": basis,
            "first_publication_timestamp": first.get("publishDate"),
            "available_from": available_from(first.get("publishDate"), sessions),
            "legacy_available_date": row["legacy_available_date"],
            "first_notification_id": int(first["disclosureIndex"]),
            "correction_notification_ids": json.dumps(correction_ids),
            "latest_notification_id": int(latest["disclosureIndex"]),
            "vintage_count": vintage_count,
            "vintage_status": vintage_status,
            "lineage_confidence": "HIGH",
            "presentation_unit_status": unit_status,
            "presentation_unit": ";".join(first.get("unit_labels") or []),
            "tfrs29_status": tfrs,
            "restated_comparative_status": "UNKNOWN_NOT_SEPARATELY_PROVEN",
            "pit_quality": timing,
            "recovery_status": status,
            "source_url": first.get("source_url"),
            "source_hash": sha256(CACHE / "detail" / f"{int(first['disclosureIndex'])}.html"),
        })

        direct_values: dict[str, float | None] = {}
        for field in list(FIELD_CODES) + ["fcf"]:
            if field == "fcf":
                cfo = direct_values.get("cfo")
                investing = direct_values.get("investing_cash_flow")
                normalized = None if cfo is None or investing is None else cfo + investing
                raw_value = None
                raw_label = "DERIVED_CFO_PLUS_INVESTING_CASH_FLOW" if normalized is not None else None
                xbrl_code = "DERIVED"
            else:
                item = first["fields"][field]
                normalized = item["current_normalized_try"]
                raw_value = item["current_raw_value"]
                raw_label = item["raw_label"]
                xbrl_code = item["xbrl_code"]
            direct_values[field] = normalized
            fields_out.append({
                "legacy_observation_id": obs_id,
                "ticker": row["ticker"],
                "financial_period": row["financial_period"],
                "field": field,
                "xbrl_code": xbrl_code,
                "raw_field_label": raw_label,
                "raw_value": raw_value,
                "raw_unit": ";".join(first.get("unit_labels") or []),
                "normalized_value": normalized,
                "normalized_unit": "TRY" if normalized is not None else None,
                "semantic_class": field_semantic(field, row["financial_period"]),
                "semantic_confidence": "HIGH" if field in {"revenue", "net_income", "equity"} else "PARTIAL",
                "first_notification_id": int(first["disclosureIndex"]),
                "missing_official": normalized is None,
            })
            if field in LOCAL_FIELDS:
                local = row.get(f"local_{field}")
                comparisons.append({
                    "legacy_observation_id": obs_id,
                    "ticker": row["ticker"],
                    "financial_period": row["financial_period"],
                    "field": field,
                    "local_value_try": local,
                    "official_first_value_try": normalized,
                    **local_comparison(field, local, normalized, contract),
                })
    return {"observations": observations, "candidates": candidates_out, "fields": fields_out, "comparisons": comparisons, "failures": failures}


def base_failed_observation(row: dict[str, Any], status: str, reason: str, kind: str | None = None, basis: str | None = None) -> dict[str, Any]:
    kind = kind or accounting_type(row)
    return {
        "legacy_observation_id": row["legacy_observation_id"], "ticker": row["ticker"], "kap_ticker": row["kap_ticker"],
        "financial_period": row["financial_period"], "period_end": row["period_end"],
        "statement_type": "ANNUAL" if row["financial_period"].endswith("Q4") else "INTERIM",
        "accounting_type": kind, "legacy_sector": row["legacy_sector"], "consolidation_basis": "UNKNOWN",
        "preferred_basis": basis or preferred_basis(kind), "first_publication_timestamp": None, "available_from": None,
        "legacy_available_date": row["legacy_available_date"], "first_notification_id": None,
        "correction_notification_ids": "[]", "latest_notification_id": None, "vintage_count": 0,
        "vintage_status": "UNKNOWN", "lineage_confidence": "NONE", "presentation_unit_status": "UNKNOWN",
        "presentation_unit": None, "tfrs29_status": "UNKNOWN", "restated_comparative_status": "UNKNOWN",
        "pit_quality": "UNKNOWN", "recovery_status": status, "source_url": None, "source_hash": None,
        "failure_reason": reason,
    }


def batch_plan(tickers: list[str]) -> list[list[str]]:
    batches = [tickers[:3], tickers[3:13]]
    remaining = tickers[13:]
    batches.extend(remaining[index:index + 15] for index in range(0, len(remaining), 15))
    return [batch for batch in batches if batch]


def qc_batch(payloads: list[dict[str, Any]], stats: dict[str, int], contract: dict[str, Any]) -> dict[str, Any]:
    observations = pd.DataFrame([row for payload in payloads for row in payload["observations"]])
    candidates = pd.DataFrame([row for payload in payloads for row in payload["candidates"]])
    duplicate_ids = int(observations.legacy_observation_id.duplicated().sum()) if len(observations) else 0
    recovered = observations[observations.recovery_status.isin(["RECOVERED_EXACT", "RECOVERED_DATE_ONLY", "PARTIAL_METADATA"])] if len(observations) else observations
    unknown_unit = int((recovered.presentation_unit_status != "RESOLVED").sum()) if len(recovered) else 0
    basis_mismatch = int((recovered.consolidation_basis != recovered.preferred_basis).sum()) if len(recovered) else 0
    network_attempts = stats["network_attempts"]
    metrics = {
        "observations": int(len(observations)),
        "recovered": int(len(recovered)),
        "failures": int((~observations.recovery_status.isin(["RECOVERED_EXACT", "RECOVERED_DATE_ONLY"])).sum()) if len(observations) else 0,
        "ambiguous": int((observations.recovery_status == "AMBIGUOUS").sum()) if len(observations) else 0,
        "duplicate_legacy_ids": duplicate_ids,
        "unknown_selected_units": unknown_unit,
        "unknown_selected_unit_pct": 0.0 if not len(recovered) else unknown_unit / len(recovered) * 100,
        "basis_qc_mismatch": basis_mismatch,
        "basis_qc_mismatch_pct": 0.0 if not len(recovered) else basis_mismatch / len(recovered) * 100,
        "candidate_rows": int(len(candidates)),
        **stats,
    }
    stop = contract["stop_conditions"]
    reasons = []
    if duplicate_ids > stop["duplicate_legacy_id_max"]:
        reasons.append("DUPLICATE_LEGACY_ID")
    if metrics["unknown_selected_unit_pct"] > stop["unknown_or_mixed_selected_unit_pct_max"]:
        reasons.append("UNKNOWN_UNIT_RATE")
    if metrics["basis_qc_mismatch_pct"] > stop["official_key_or_basis_qc_mismatch_pct_max"]:
        reasons.append("BASIS_QC_MISMATCH")
    if network_attempts and stats["http_429"] / network_attempts * 100 > stop["http_429_network_attempt_pct_max"]:
        reasons.append("HTTP_429_RATE")
    if stats["http_429"] > stop["http_429_count_per_batch_max"]:
        reasons.append("HTTP_429_COUNT")
    metrics["stop_reasons"] = reasons
    metrics["gate"] = "STOP" if reasons else "CONTINUE"
    return metrics


def derive_single_quarters(fields: pd.DataFrame, observations: pd.DataFrame, contract: dict[str, Any]) -> pd.DataFrame:
    derived: list[dict[str, Any]] = []
    if fields.empty or observations.empty:
        return pd.DataFrame()
    obs = observations.set_index("legacy_observation_id")
    direct = fields.set_index(["ticker", "financial_period", "field"])
    for _, current_obs in observations.iterrows():
        period = str(current_obs.financial_period)
        quarter = int(period[-1])
        if quarter == 1 or current_obs.recovery_status not in {"RECOVERED_EXACT", "RECOVERED_DATE_ONLY"}:
            continue
        previous_period = f"{period[:4]}Q{quarter - 1}"
        previous_rows = observations[(observations.ticker == current_obs.ticker) & (observations.financial_period == previous_period)]
        if previous_rows.empty:
            continue
        previous_obs = previous_rows.iloc[0]
        comparable = (
            previous_obs.recovery_status in {"RECOVERED_EXACT", "RECOVERED_DATE_ONLY"}
            and previous_obs.consolidation_basis == current_obs.consolidation_basis
            and previous_obs.tfrs29_status == current_obs.tfrs29_status
            and not str(current_obs.tfrs29_status).endswith("UNKNOWN_COMPARATIVE")
        )
        if not comparable:
            continue
        for field in contract["period_semantics"]["single_quarter_derivation"]["enabled_only_for"]:
            current_key = (current_obs.ticker, period, field)
            previous_key = (current_obs.ticker, previous_period, field)
            if current_key not in direct.index or previous_key not in direct.index:
                continue
            current_value = direct.loc[current_key].normalized_value
            previous_value = direct.loc[previous_key].normalized_value
            if pd.isna(current_value) or pd.isna(previous_value):
                continue
            derived.append({
                "legacy_observation_id": current_obs.legacy_observation_id,
                "ticker": current_obs.ticker,
                "financial_period": period,
                "field": f"{field}_single_quarter",
                "xbrl_code": "DERIVED_CUMULATIVE_DIFFERENCE",
                "raw_field_label": None,
                "raw_value": None,
                "raw_unit": None,
                "normalized_value": float(current_value) - float(previous_value),
                "normalized_unit": "TRY",
                "semantic_class": "FLOW_SINGLE_QUARTER_DERIVED",
                "semantic_confidence": "HIGH",
                "first_notification_id": current_obs.first_notification_id,
                "missing_official": False,
                "derivation_predecessor_period": previous_period,
            })
    return pd.DataFrame(derived)


def finalize(universe: pd.DataFrame, contract: dict[str, Any]) -> dict[str, Any]:
    payloads = [json.loads(path.read_text(encoding="utf-8")) for path in sorted((CHECKPOINTS / "tickers").glob("*.json"))]
    stop_events = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(CHECKPOINTS.glob("stop_event_batch_*.json"))]
    observations = pd.DataFrame([row for payload in payloads for row in payload["observations"]])
    candidates = pd.DataFrame([row for payload in payloads for row in payload["candidates"]])
    fields = pd.DataFrame([row for payload in payloads for row in payload["fields"]])
    comparisons = pd.DataFrame([row for payload in payloads for row in payload["comparisons"]])
    failures = pd.DataFrame([row for payload in payloads for row in payload["failures"]])
    if len(observations):
        observations = observations.sort_values("legacy_observation_id").reset_index(drop=True)
    missing_ids = sorted(set(universe.legacy_observation_id) - set(observations.get("legacy_observation_id", [])))
    if missing_ids:
        stop_event_path = CHECKPOINTS / "stop_event_batch_2.json"
        missing_reason = "NOT_PROCESSED_RATE_LIMIT_STOP" if stop_event_path.exists() else "NOT_PROCESSED"
        missing_rows = universe[universe.legacy_observation_id.isin(missing_ids)]
        observations = pd.concat([observations, pd.DataFrame([base_failed_observation(row, "SOURCE_ERROR", missing_reason) for row in missing_rows.to_dict("records")])], ignore_index=True)
    derived = derive_single_quarters(fields, observations, contract)
    if len(derived):
        fields = pd.concat([fields, derived], ignore_index=True, sort=False)

    RESULTS.mkdir(parents=True, exist_ok=True)
    observations.to_csv(RESULTS / "EXP-DATA-008_observations.csv", index=False)
    candidates.to_csv(RESULTS / "EXP-DATA-008_lineage.csv", index=False)
    fields.to_csv(RESULTS / "EXP-DATA-008_fields.csv", index=False)
    comparisons.to_csv(RESULTS / "EXP-DATA-008_local_comparison.csv", index=False)
    failures.to_csv(RESULTS / "EXP-DATA-008_failures.csv", index=False)
    universe.to_csv(RESULTS / "EXP-DATA-008_input_universe.csv", index=False)

    counts = observations.recovery_status.value_counts().to_dict()
    total = len(observations)
    repeated_rate_limit_stop = any(
        event.get("stop_reasons") == ["HTTP_429_BATCH_LIMIT"]
        and int(event.get("http_429", event.get("http_429_count_minimum_observed", 0))) > contract["stop_conditions"]["http_429_count_per_batch_max"]
        for event in stop_events
    )
    summary = {
        "experiment": "EXP-DATA-008",
        "total_legacy_observations": total,
        "unique_legacy_observations": int(observations.legacy_observation_id.nunique()),
        "status_counts": {key: int(value) for key, value in counts.items()},
        "status_pct": {key: round(value / total * 100, 4) for key, value in counts.items()} if total else {},
        "fully_recovered": int(counts.get("RECOVERED_EXACT", 0) + counts.get("RECOVERED_DATE_ONLY", 0)),
        "partial_metadata": int(counts.get("PARTIAL_METADATA", 0)),
        "ambiguous": int(counts.get("AMBIGUOUS", 0)),
        "unrecoverable": int(counts.get("UNRECOVERABLE", 0)),
        "source_failure_or_not_processed_after_stop": int(counts.get("SOURCE_ERROR", 0)),
        "exact_timestamp": int((observations.pit_quality == "EXACT_TIMESTAMP").sum()),
        "exact_first_publication": int(observations.first_notification_id.notna().sum()),
        "vintage_lineage_recovered": int((observations.lineage_confidence == "HIGH").sum()),
        "accounting_semantics_resolved": int(fields[fields.semantic_class != "UNKNOWN"].legacy_observation_id.nunique()) if len(fields) else 0,
        "tfrs29_confirmed_or_pre": int(observations.tfrs29_status.isin(["PRE_TFRS29", "POST_TFRS29_CONFIRMED", "BANK_BDDK_NOT_APPLIED"]).sum()),
        "year_breakdown": observations.assign(year=observations.financial_period.str[:4]).groupby(["year", "recovery_status"]).size().unstack(fill_value=0).to_dict(orient="index"),
        "accounting_type_breakdown": observations.groupby(["accounting_type", "recovery_status"]).size().unstack(fill_value=0).to_dict(orient="index"),
        "completed_ticker_checkpoints": len(payloads),
        "completed_source_observations": int(sum(len(payload["observations"]) for payload in payloads)),
        "stop_events": stop_events,
        "kap_bulk_pit_vintage_gate": "PARTIAL" if stop_events else ("PASS" if len(payloads) == universe.kap_ticker.nunique() else "PARTIAL"),
        "fundamental_pit_vintage_gate": "PARTIAL",
        "public_kap_bulk_source": "BLOCKED_BY_RATE_LIMIT" if repeated_rate_limit_stop else "NOT_BLOCKED",
        "data_readiness": {
            "QUALITY": "PARTIAL",
            "BALANCE_SHEET": "PARTIAL",
            "CASH_FLOW": "NO",
            "EARNINGS": "PARTIAL",
            "VALUE": "NO"
        },
        "safe_subset": {
            "rule": "RECOVERED_EXACT + resolved unit + HIGH semantic-confidence field; PRE_TFRS29 or POST_TFRS29_CONFIRMED/BANK_BDDK_NOT_APPLIED when inflation-basis safety is required",
            "observation_count": int((observations.recovery_status == "RECOVERED_EXACT").sum()),
            "warning": "Alphabetical canary execution subset only; not representative and not authorized for alpha/model selection."
        },
        "production_data_written": False,
    }
    (RESULTS / "EXP-DATA-008_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    resume_result = {
        "experiment": "EXP-DATA-008R",
        "resume_attempts": 1,
        "cooldown_seconds": 60,
        "completed_observations": summary["completed_source_observations"],
        "fully_recovered": summary["fully_recovered"],
        "partial_metadata": summary["partial_metadata"],
        "unrecoverable": summary["unrecoverable"],
        "not_processed_after_rate_limit_stop": summary["source_failure_or_not_processed_after_stop"],
        "repeat_429_stop": repeated_rate_limit_stop,
        "fundamental_pit_vintage_gate": "PARTIAL",
        "public_kap_bulk_source": "BLOCKED_BY_RATE_LIMIT" if repeated_rate_limit_stop else "NOT_BLOCKED",
        "production_data_written": False,
    }
    (RESULTS / "EXP-DATA-008R_resume_result.json").write_text(json.dumps(resume_result, ensure_ascii=False, indent=2), encoding="utf-8")

    cache_files = sorted([path for path in CACHE.rglob("*") if path.is_file() and not path.name.endswith(".sha256")])
    output_files = sorted([*RESULTS.glob("EXP-DATA-008_*"), *RESULTS.glob("EXP-DATA-008R_*")])
    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "contract_sha256": sha256(CONTRACT_PATH),
        "code_sha256": sha256(Path(__file__)),
        "cache_files": len(cache_files),
        "cache_sha256": {path.relative_to(RESEARCH).as_posix(): sha256(path) for path in cache_files},
        "output_sha256": {path.relative_to(RESEARCH).as_posix(): sha256(path) for path in output_files},
        "production_data_written": False,
    }
    MANIFESTS.mkdir(parents=True, exist_ok=True)
    (MANIFESTS / "EXP-DATA-008_reproducibility.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--max-batches", type=int)
    parser.add_argument("--finalize-only", action="store_true")
    args = parser.parse_args()
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    universe, universe_hash = canonical_universe()
    expected = contract["input_universe"]
    if len(universe) != expected["required_observations"] or universe.legacy_observation_id.nunique() != expected["required_unique_legacy_ids"] or universe_hash != expected["canonical_jsonl_sha256"]:
        raise BatchStop(f"LOCKED_UNIVERSE_MISMATCH:{len(universe)}:{universe_hash}")
    if args.finalize_only:
        print(json.dumps(finalize(universe, contract), ensure_ascii=False, indent=2))
        return

    CHECKPOINTS.mkdir(parents=True, exist_ok=True)
    (CHECKPOINTS / "tickers").mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 EXP-DATA-008 research reconstruction", "Accept-Language": "tr"})
    inventory_stats = new_stats()
    members_content = request_cached(session, "GET", MEMBERS_URL, CACHE / "member_inventory.html", inventory_stats, contract, offline=args.offline)
    members = parse_member_inventory(members_content)
    needed_tickers = sorted(universe.kap_ticker.unique())
    missing_members = sorted(set(needed_tickers) - set(members))
    (CHECKPOINTS / "member_mapping.json").write_text(json.dumps({"mapped": {ticker: members.get(ticker) for ticker in needed_tickers}, "missing": missing_members, "stats": inventory_stats}, indent=2), encoding="utf-8")
    sessions = trading_sessions()
    batches = batch_plan(needed_tickers)
    if args.max_batches is not None:
        batches = batches[: args.max_batches]
    batch_log_path = CHECKPOINTS / "batch_log.json"
    batch_log = json.loads(batch_log_path.read_text(encoding="utf-8")) if batch_log_path.exists() else []
    already_logged = {int(row["batch_number"]) for row in batch_log}

    for batch_number, batch in enumerate(batches, 1):
        pending = [ticker for ticker in batch if not (CHECKPOINTS / "tickers" / f"{ticker}.json").exists()]
        if not pending:
            continue
        stats = new_stats()
        payloads: list[dict[str, Any]] = []
        started = datetime.now(timezone.utc)
        for ticker in pending:
            ticker_rows = universe[universe.kap_ticker == ticker]
            try:
                payload = process_ticker(ticker_rows, members.get(ticker), session, sessions, stats, contract, args.offline)
            except BatchStop as exc:
                stop_record = {
                    "batch_number": batch_number,
                    "tickers": pending,
                    "interrupted_ticker": ticker,
                    "started_at_utc": started.isoformat(),
                    "stopped_at_utc": datetime.now(timezone.utc).isoformat(),
                    **stats,
                    "gate": "STOP",
                    "stop_reasons": [str(exc)],
                }
                batch_log = [row for row in batch_log if int(row["batch_number"]) != batch_number]
                batch_log.append(stop_record)
                atomic_bytes(batch_log_path, json.dumps(batch_log, ensure_ascii=False, indent=2).encode("utf-8"))
                atomic_bytes(CHECKPOINTS / f"stop_event_batch_{batch_number}.json", json.dumps(stop_record, ensure_ascii=False, indent=2).encode("utf-8"))
                raise
            payload["checkpoint"] = {"ticker": ticker, "completed_at_utc": datetime.now(timezone.utc).isoformat(), "contract_sha256": sha256(CONTRACT_PATH)}
            checkpoint = CHECKPOINTS / "tickers" / f"{ticker}.json"
            atomic_bytes(checkpoint, json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))
            payloads.append(payload)
        metrics = qc_batch(payloads, stats, contract)
        metrics.update({"batch_number": batch_number, "tickers": pending, "started_at_utc": started.isoformat(), "completed_at_utc": datetime.now(timezone.utc).isoformat()})
        if batch_number not in already_logged:
            batch_log.append(metrics)
        else:
            batch_log = [metrics if int(row["batch_number"]) == batch_number else row for row in batch_log]
        atomic_bytes(batch_log_path, json.dumps(batch_log, ensure_ascii=False, indent=2).encode("utf-8"))
        print(json.dumps(metrics, ensure_ascii=False))
        if metrics["gate"] == "STOP":
            raise BatchStop(";".join(metrics["stop_reasons"]))

    summary = finalize(universe, contract)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

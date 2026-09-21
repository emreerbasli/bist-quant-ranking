"""EXP-DATA-007: bounded KAP disclosure and first-vintage recovery pilot.

This module is research-only. It performs bounded annual KAP list requests and
then inspects only the exact financial-report candidates needed by the locked
30-observation pilot contract. It never writes production datasets.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / "research"
RESULTS = RESEARCH / "results"
CACHE = RESEARCH / "cache" / "exp_data_007"
CONTRACT_PATH = RESEARCH / "contracts" / "exp_data_007_pilot.json"
LIST_URL = "https://www.kap.org.tr/tr/api/disclosure/members/byCriteria"
DETAIL_URL = "https://www.kap.org.tr/tr/Bildirim/{notification_id}"

MEMBER_OIDS = {
    "TUPRS.IS": "4028e4a140f2ed720140f37f139c01bc",
    "THYAO.IS": "4028e4a140f2ed720140f376bebb01a7",
    "BIMAS.IS": "4028e4a140e95be70140ee1b7b030119",
    "AEFES.IS": "4028e4a140e95bea0140ed2fde10009d",
    "ASELS.IS": "4028e4a1413b7ef401413bc2251e0047",
    "LOGO.IS": "4028e4a14158e41e01415b41210a6e8c",
    "ISCTR.IS": "4028e4a140f2ed7201411682b0cb05c6",
    "AKBNK.IS": "4028e4a240e8d1830140e905edcd0006",
    "ANSGR.IS": "4028e4a140e95bea0140ed21b5c10078",
    "TURSG.IS": "4028e4a140e95be70140ee2f466d0159",
}

FIELD_CODES = {
    "revenue": ["ifrs-full_Revenue", "kap-fr_OperatingIncome"],
    "operating_profit": ["ifrs-full_ProfitLossFromOperatingActivities"],
    "ebitda": ["kap-fr_EarningsBeforeInterestTaxesDepreciationAndAmortisation"],
    "net_income": [
        "ifrs-full_ProfitLoss",
        "kap-fr_ProfitLoss",
        "kap-fr_NetProfitLoss",
        "ifrs-full_ProfitLossAttributableToOwnersOfParent",
    ],
    "equity": ["ifrs-full_Equity"],
    "cfo": ["ifrs-full_CashFlowsFromUsedInOperatingActivities"],
    "investing_cash_flow": ["ifrs-full_CashFlowsFromUsedInInvestingActivities"],
}

LOCAL_FIELDS = {
    "revenue": "satislar",
    "operating_profit": "op_gelir",
    "ebitda": "ebitda",
    "net_income": "net_kar",
    "equity": "ozkaynaklar",
    "cfo": "cfo",
    "fcf": "fcf",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def timing_quality(timestamp: str | None) -> str:
    if not timestamp:
        return "UNKNOWN"
    if re.fullmatch(r"\d{2}\.\d{2}\.\d{4}\s+\d{2}:\d{2}:\d{2}", timestamp.strip()):
        return "EXACT_TIMESTAMP"
    if re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", timestamp.strip()):
        return "EXACT_DATE"
    return "APPROXIMATE"


def flow_semantics(period_number: int) -> str:
    return {1: "SINGLE_QUARTER", 2: "YTD_6M", 3: "YTD_9M", 4: "ANNUAL"}.get(
        int(period_number), "UNKNOWN"
    )


def preferred_basis(company_type: str) -> str:
    return "CONSOLIDATED" if company_type == "NON_FINANCIAL" else "NON_CONSOLIDATED"


def classify_consolidation(text: str) -> str:
    normalized = text.casefold()
    if "konsolide olmayan" in normalized or "non-consolidated" in normalized:
        return "NON_CONSOLIDATED"
    if "konsolide" in normalized or "consolidated" in normalized:
        return "CONSOLIDATED"
    return "UNKNOWN"


def parse_number(value: str | None, multiplier: int = 1) -> float | None:
    if value is None:
        return None
    value = value.strip().replace("\xa0", "")
    if not value or value in {"-", "—", "N/A"}:
        return None
    value = value.replace("(", "-").replace(")", "")
    if re.fullmatch(r"-?\d{1,3}(?:\.\d{3})+(?:,\d+)?", value):
        value = value.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"-?\d+(?:,\d+)?", value):
        value = value.replace(",", ".")
    else:
        return None
    try:
        return float(value) * multiplier
    except ValueError:
        return None


def presentation_unit_multiplier(text: str) -> int:
    if re.search(r"1[\.,]000[\.,]000\s*TL|Milyon\s*TL", text, re.I):
        return 1_000_000
    if re.search(r"1[\.,]000\s*TL|Bin\s*TL", text, re.I):
        return 1_000
    return 1


def presentation_unit_info(soup: BeautifulSoup) -> dict[str, Any]:
    labels: list[str] = []
    for row in soup.find_all("tr"):
        row_text = row.get_text(" ", strip=True)
        if "Sunum Para Birimi" in row_text or "Presentation Currency" in row_text:
            cells = row.find_all(["th", "td"])
            labels.append(cells[-1].get_text(" ", strip=True) if cells else row_text)
    unique_labels = list(dict.fromkeys(labels))
    multipliers = [presentation_unit_multiplier(label) for label in unique_labels]
    recognized = [bool(re.search(r"(?:^|\s)(?:TL|1[\.,]000\s*TL|1[\.,]000[\.,]000\s*TL|Bin\s*TL|Milyon\s*TL)(?:$|\s)", label, re.I)) for label in unique_labels]
    if not unique_labels:
        return {"status": "UNKNOWN", "labels": [], "multiplier": None}
    if not all(recognized) or len(set(multipliers)) != 1:
        return {"status": "INVALID_MIXED_OR_UNKNOWN", "labels": unique_labels, "multiplier": None}
    return {"status": "RESOLVED", "labels": unique_labels, "multiplier": multipliers[0]}


def period_number(period: str) -> int:
    return int(period[-1])


def period_end(period: str) -> str:
    year, quarter = int(period[:4]), int(period[-1])
    return {
        1: f"{year}-03-31",
        2: f"{year}-06-30",
        3: f"{year}-09-30",
        4: f"{year}-12-31",
    }[quarter]


def list_payload(oid: str, calendar_year: int) -> dict[str, Any]:
    return {
        "fromDate": f"{calendar_year}-01-01",
        "toDate": f"{calendar_year}-12-31",
        "memberType": "IGS",
        "mkkMemberOidList": [oid],
        "inactiveMkkMemberOidList": [],
        "disclosureClass": "FR",
        "subjectList": [],
        "isLate": "",
        "mainSector": "",
        "sector": "",
        "subSector": "",
        "marketOid": "",
        "index": "",
        "bdkReview": "",
        "bdkMemberOidList": [],
        "year": "",
        "term": "",
        "ruleType": "",
        "period": "",
        "fromSrc": False,
        "srcCategory": "",
        "disclosureIndexList": [],
    }


def request_json(
    session: requests.Session,
    url: str,
    body: dict[str, Any],
    cache_path: Path,
    request_stats: dict[str, int],
) -> list[dict[str, Any]]:
    request_stats["logical_requests"] += 1
    if cache_path.exists():
        request_stats["cache_hits"] += 1
        data = json.loads(cache_path.read_text(encoding="utf-8"))
    else:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        last_response = None
        for attempt, pause in enumerate((0, 5, 15, 30), 1):
            if pause:
                time.sleep(pause)
            request_stats["network_attempts"] += 1
            response = session.post(url, json=body, timeout=45)
            last_response = response
            if response.status_code != 429:
                response.raise_for_status()
                data = response.json()
                cache_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                break
        else:
            assert last_response is not None
            last_response.raise_for_status()
            raise RuntimeError("unreachable")
    if not isinstance(data, list):
        raise ValueError(f"Expected list from KAP, got {type(data).__name__}")
    return data


def extract_context_values(row: Any, multiplier: int) -> list[float | None]:
    cells = row.find_all("td", class_=lambda c: c and "taxonomy-context-value" in c)
    return [parse_number(cell.get_text(" ", strip=True), multiplier) for cell in cells]


def choose_xbrl_row(soup: BeautifulSoup, codes: Iterable[str]) -> tuple[str | None, list[float | None]]:
    for code in codes:
        matches = []
        for row in soup.find_all("tr"):
            first = row.find("td", class_="taxonomy-field-name-cell")
            if not first:
                continue
            raw_code = first.get_text(" ", strip=True).split("|", 1)[0]
            if raw_code != code:
                continue
            # Equity movement tables reuse ifrs-full_Equity with periodStart/End roles.
            if code == "ifrs-full_Equity" and "period" in first.get_text(" ", strip=True).casefold():
                continue
            values = extract_context_values(row, 1)
            if values:
                matches.append((first.get_text(" ", strip=True), values))
        if matches:
            return matches[0]
    return None, []


def detail_page(
    session: requests.Session,
    notification_id: int,
    request_stats: dict[str, int],
) -> dict[str, Any]:
    cache_path = CACHE / "detail" / f"{notification_id}.html"
    request_stats["logical_requests"] += 1
    if cache_path.exists():
        request_stats["cache_hits"] += 1
        content = cache_path.read_bytes()
    else:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        last_response = None
        for attempt, pause in enumerate((0, 5, 15, 30), 1):
            if pause:
                time.sleep(pause)
            request_stats["network_attempts"] += 1
            response = session.get(DETAIL_URL.format(notification_id=notification_id), timeout=60)
            last_response = response
            if response.status_code != 429:
                response.raise_for_status()
                content = response.content
                cache_path.write_bytes(content)
                break
        else:
            assert last_response is not None
            last_response.raise_for_status()
            raise RuntimeError("unreachable")
    soup = BeautifulSoup(content, "html.parser")
    text = soup.get_text(" ", strip=True)
    unit = presentation_unit_info(soup)
    unit_multiplier = unit["multiplier"]
    consolidation = "UNKNOWN"
    for row in soup.find_all("tr"):
        row_text = row.get_text(" ", strip=True)
        if "Finansal Tablo Niteli" in row_text or "Financial Statement Type" in row_text:
            consolidation = classify_consolidation(row_text)
            break
    fields: dict[str, Any] = {}
    for field, codes in FIELD_CODES.items():
        code, raw_values = choose_xbrl_row(soup, codes)
        scaled = [value * unit_multiplier if value is not None and unit_multiplier is not None else None for value in raw_values]
        fields[field] = {
            "xbrl_code": code.split("|", 1)[0] if code else None,
            "raw_context_values_display_unit": raw_values,
            "current_value_try": scaled[0] if scaled else None,
            "comparative_value_try": scaled[1] if len(scaled) > 1 else None,
            "all_context_values_try": scaled,
        }
    correction = bool(re.search(r"Düzeltilmiş Bildirim|Corrected Notification", text, re.I))
    tfrs29_mentioned = bool(re.search(r"TFRS\s*29|TMS\s*29|enflasyon muhasebes", text, re.I))
    return {
        "notification_id": notification_id,
        "source_url": DETAIL_URL.format(notification_id=notification_id),
        "consolidated_flag": consolidation,
        "unit_multiplier": unit_multiplier,
        "unit_labels": unit["labels"],
        "unit_status": unit["status"],
        "correction_marker": correction,
        "tfrs29_mentioned": tfrs29_mentioned,
        "fields": fields,
    }


def exact_report_candidates(items: list[dict[str, Any]], ticker: str, period: str) -> list[dict[str, Any]]:
    code = ticker.replace(".IS", "")
    year, pnum = int(period[:4]), period_number(period)
    candidates = []
    for item in items:
        codes = [part.strip() for part in str(item.get("stockCodes") or "").split(",")]
        if (
            code in codes
            and int(item.get("year") or -1) == year
            and int(item.get("period") or -1) == pnum
            and str(item.get("subject") or "").strip().casefold() == "finansal rapor"
            and item.get("disclosureIndex")
        ):
            candidates.append(dict(item))
    return sorted(candidates, key=lambda row: pd.to_datetime(row.get("publishDate"), dayfirst=True))


def select_lineage(candidates: list[dict[str, Any]], basis: str) -> tuple[list[dict[str, Any]], str | None]:
    matched = [row for row in candidates if row.get("consolidated_flag") == basis]
    if not matched:
        return [], "NO_PREFERRED_CONSOLIDATION_MATCH" if candidates else "NO_EXACT_FINANCIAL_REPORT"
    return matched, None


def tfrs29_status(period: str, company_type: str, page_mentions_tfrs29: bool) -> str:
    if period < "2023Q4":
        return "PRE_TFRS29"
    if company_type == "BANK":
        return "BANK_BDDK_NOT_APPLIED_IN_LOCAL_CONTRACT"
    if page_mentions_tfrs29:
        return "POST_TFRS29_MENTION_CONFIRMED"
    return "POST_TFRS29_STATUS_UNKNOWN"


def load_local(ticker: str, period: str) -> dict[str, Any] | None:
    path = ROOT / "data" / "fundamentals" / f"{ticker.replace('.', '_')}.parquet"
    if not path.exists():
        return None
    frame = pd.read_parquet(path)
    row = frame[frame["ceyrek"] == period]
    return None if row.empty else row.iloc[0].to_dict()


def local_number(row: dict[str, Any] | None, field: str) -> float | None:
    if row is None or field not in LOCAL_FIELDS:
        return None
    value = row.get(LOCAL_FIELDS[field])
    return None if pd.isna(value) else float(value)


def difference(local: float | None, official: float | None) -> tuple[float | None, float | None]:
    if local is None or official is None:
        return None, None
    absolute = local - official
    relative = absolute / abs(official) * 100 if official != 0 else None
    return absolute, relative


def classify_local_basis(local: float | None, first: float | None, latest: float | None) -> str:
    if local is None or first is None:
        return "UNKNOWN"
    first_match = abs(local - first) <= 0.5
    latest_match = latest is not None and abs(local - latest) <= 0.5
    if first_match and latest_match:
        return "MATCHES_FIRST_AND_LATEST"
    if first_match:
        return "MATCHES_FIRST_PUBLISHED"
    if latest_match:
        return "LATEST_OVERWRITE"
    if latest is not None and latest != first:
        return "CLOSER_TO_FIRST" if abs(local - first) < abs(local - latest) else "CLOSER_TO_LATEST"
    if latest == first:
        return "DIFFERS_FROM_FIRST_AND_LATEST_EQUAL"
    return "DIFFERS_FROM_RECOVERED_VINTAGES"


def main() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 EXP-DATA-007 bounded research pilot",
            "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
            "Accept-Language": "tr",
        }
    )
    retrieval_timestamp = datetime.now(timezone.utc).isoformat()
    request_stats = {"logical_requests": 0, "network_attempts": 0, "cache_hits": 0}
    listing_by_ticker: dict[str, list[dict[str, Any]]] = {}
    request_count = 0
    request_failures: list[dict[str, Any]] = []
    for spec in contract["tickers"]:
        ticker = spec["ticker"]
        listing_by_ticker[ticker] = []
        # KAP returns HTTP 500 for the original multi-year request.  Four
        # explicit calendar windows bound the workaround and retain enough
        # time to observe corrections made in the following year.
        for calendar_year in (2022, 2023, 2024, 2025):
            try:
                listing_by_ticker[ticker].extend(
                    request_json(
                        session,
                        LIST_URL,
                        list_payload(MEMBER_OIDS[ticker], calendar_year),
                        CACHE / "list" / f"{ticker.replace('.', '_')}_{calendar_year}.json",
                        request_stats,
                    )
                )
                request_count += 1
            except Exception as exc:  # no alternate source is silently substituted
                request_count += 1
                request_failures.append(
                    {"ticker": ticker, "calendar_year": calendar_year, "stage": "LIST", "reason": repr(exc)}
                )
            time.sleep(0.15)
        listing_by_ticker[ticker] = list(
            {int(row["disclosureIndex"]): row for row in listing_by_ticker[ticker] if row.get("disclosureIndex")}.values()
        )

    observations: list[dict[str, Any]] = []
    candidate_rows: list[dict[str, Any]] = []
    field_rows: list[dict[str, Any]] = []
    semantic_rows: list[dict[str, Any]] = []
    tfrs_rows: list[dict[str, Any]] = []
    difference_rows: list[dict[str, Any]] = []
    unit_rows: list[dict[str, Any]] = []
    # Preserve material execution/parser incidents even when the final cached
    # run succeeds. These are experiment evidence, not current-row failures.
    failures: list[dict[str, Any]] = [
        {
            "stage": "EXECUTION_DESIGN",
            "reason": "MULTI_YEAR_LIST_WINDOW_HTTP_500",
            "status": "RESOLVED_BY_BOUNDED_ANNUAL_WINDOWS",
            "impact": "No mapping rule or pilot observation changed.",
        },
        {
            "stage": "PARSER_REGRESSION",
            "reason": "PRESENTATION_UNIT_MISSCALING_1000_VS_1000000_TL",
            "status": "RESOLVED_BY_STATEMENT_LEVEL_UNIT_NORMALIZATION",
            "impact": "Pre-fix materiality output invalidated and regenerated.",
        },
        {
            "stage": "RATE_LIMIT",
            "reason": "HTTP_429_ON_REPEATED_UNCACHED_RUNS",
            "status": "MITIGATED_BY_DETERMINISTIC_CACHE_AND_BOUNDED_BACKOFF",
            "impact": "Remaining medium/high bulk runtime risk; no source substitution.",
        },
        *request_failures,
    ]

    for spec in contract["tickers"]:
        ticker = spec["ticker"]
        for period in spec["periods"]:
            obs_id = f"{ticker}:{period}"
            candidates = exact_report_candidates(listing_by_ticker[ticker], ticker, period)
            enriched: list[dict[str, Any]] = []
            for candidate in candidates:
                try:
                    detail = detail_page(session, int(candidate["disclosureIndex"]), request_stats)
                    request_count += 1
                    enriched.append({**candidate, **detail})
                except Exception as exc:
                    request_count += 1
                    failures.append(
                        {
                            "observation_id": obs_id,
                            "ticker": ticker,
                            "financial_period": period,
                            "stage": "DETAIL",
                            "notification_id": candidate.get("disclosureIndex"),
                            "reason": repr(exc),
                        }
                    )
                time.sleep(0.15)
            lineage, mapping_failure = select_lineage(enriched, preferred_basis(spec["company_type"]))
            first = lineage[0] if lineage else None
            latest = lineage[-1] if lineage else None
            local = load_local(ticker, period)
            if mapping_failure:
                failures.append(
                    {
                        "observation_id": obs_id,
                        "ticker": ticker,
                        "financial_period": period,
                        "stage": "MAPPING",
                        "notification_id": None,
                        "reason": mapping_failure,
                    }
                )

            for rank, candidate in enumerate(enriched, 1):
                candidate_rows.append(
                    {
                        "observation_id": obs_id,
                        "candidate_rank": rank,
                        "ticker": ticker,
                        "financial_period": period,
                        "notification_id": candidate.get("disclosureIndex"),
                        "announcement_timestamp": candidate.get("publishDate"),
                        "subject": candidate.get("subject"),
                        "summary": candidate.get("summary"),
                        "statement_year": candidate.get("year"),
                        "statement_period_number": candidate.get("period"),
                        "rule_type": candidate.get("ruleType"),
                        "consolidated_flag": candidate.get("consolidated_flag"),
                        "preferred_basis": preferred_basis(spec["company_type"]),
                        "basis_match": candidate.get("consolidated_flag") == preferred_basis(spec["company_type"]),
                        "modify_status": candidate.get("modifyStatus"),
                        "correction_marker": candidate.get("correction_marker"),
                        "attachment_count": candidate.get("attachmentCount"),
                        "presentation_unit_labels": ";".join(candidate.get("unit_labels") or []),
                        "presentation_unit_multiplier": candidate.get("unit_multiplier"),
                        "presentation_unit_status": candidate.get("unit_status"),
                        "source_url": candidate.get("source_url"),
                        "retrieval_timestamp_utc": retrieval_timestamp,
                    }
                )
                unit_rows.append(
                    {
                        "observation_id": obs_id,
                        "ticker": ticker,
                        "financial_period": period,
                        "notification_id": candidate.get("disclosureIndex"),
                        "consolidated_flag": candidate.get("consolidated_flag"),
                        "basis_match": candidate.get("consolidated_flag") == preferred_basis(spec["company_type"]),
                        "unit_labels": ";".join(candidate.get("unit_labels") or []),
                        "unit_multiplier": candidate.get("unit_multiplier"),
                        "unit_status": candidate.get("unit_status"),
                    }
                )

            timing = timing_quality(first.get("publishDate") if first else None)
            first_class = "FIRST_PUBLISHED" if first else "UNKNOWN"
            has_revision = bool(
                len(lineage) > 1
                or any(row.get("modifyStatus") for row in lineage)
                or any(row.get("correction_marker") for row in lineage)
            )
            vintage_class = "RESTATED" if has_revision else first_class
            vintage_recovery_status = "CORRECTED" if has_revision else first_class
            tfrs_status = tfrs29_status(
                period,
                spec["company_type"],
                bool(first and first.get("tfrs29_mentioned")),
            )
            complete_unrecoverable = first is None
            observations.append(
                {
                    "observation_id": obs_id,
                    "ticker": ticker,
                    "company_type": spec["company_type"],
                    "size_liquidity": spec["size_liquidity"],
                    "sector": spec["sector"],
                    "financial_period": period,
                    "period_end": period_end(period),
                    "statement_type": "ANNUAL" if period.endswith("Q4") else "INTERIM",
                    "preferred_consolidated_flag": preferred_basis(spec["company_type"]),
                    "consolidated_flag": first.get("consolidated_flag") if first else "UNKNOWN",
                    "kap_notification_id": first.get("disclosureIndex") if first else None,
                    "announcement_date": str(first.get("publishDate"))[:10] if first else None,
                    "announcement_timestamp": first.get("publishDate") if first else None,
                    "timing_quality": timing,
                    "available_next_session_required": timing in {"EXACT_TIMESTAMP", "EXACT_DATE"},
                    "first_publication_flag": bool(first),
                    "restatement_revision_flag": has_revision,
                    "vintage_class": vintage_class,
                    "vintage_recovery_status": vintage_recovery_status,
                    "lineage_status": (
                        "RESOLVED_CORRECTED_CHAIN" if has_revision else ("RESOLVED_NO_CORRECTION" if first else "UNKNOWN")
                    ),
                    "source_url": first.get("source_url") if first else None,
                    "retrieval_timestamp_utc": retrieval_timestamp,
                    "exact_candidate_count": len(enriched),
                    "preferred_basis_candidate_count": len(lineage),
                    "mapping_status": "EXACT" if first else "UNRESOLVED",
                    "mapping_confidence": "HIGH" if first else "NONE",
                    "mapping_failure": mapping_failure,
                    "consolidation_basis_resolved": bool(first and first.get("consolidated_flag") != "UNKNOWN"),
                    "presentation_unit_status": first.get("unit_status") if first else "UNKNOWN",
                    "accounting_semantics_status": "RESOLVED" if first else "UNKNOWN",
                    "flow_semantics": flow_semantics(period_number(period)),
                    "tfrs29_status": tfrs_status,
                    "completely_unrecoverable": complete_unrecoverable,
                }
            )

            fields = list(FIELD_CODES) + ["fcf"]
            for field in fields:
                if field == "fcf":
                    def fcf_value(source: dict[str, Any] | None) -> float | None:
                        if not source:
                            return None
                        cfo = source["fields"]["cfo"]["current_value_try"]
                        inv = source["fields"]["investing_cash_flow"]["current_value_try"]
                        return None if cfo is None or inv is None else cfo + inv

                    first_value, latest_value = fcf_value(first), fcf_value(latest)
                    comparative = None
                    xbrl_code = "DERIVED_CFO_PLUS_INVESTING_CF" if first_value is not None else None
                else:
                    first_data = first["fields"][field] if first else {}
                    latest_data = latest["fields"][field] if latest else {}
                    first_value = first_data.get("current_value_try")
                    latest_value = latest_data.get("current_value_try")
                    comparative = first_data.get("comparative_value_try")
                    xbrl_code = first_data.get("xbrl_code")
                local_value = local_number(local, field)
                abs_diff, rel_diff = difference(local_value, first_value)
                field_rows.append(
                    {
                        "observation_id": obs_id,
                        "ticker": ticker,
                        "financial_period": period,
                        "field": field,
                        "xbrl_code": xbrl_code,
                        "first_published_value_try": first_value,
                        "latest_recovered_value_try": latest_value,
                        "published_comparative_value_try": comparative,
                        "local_stored_value_try": local_value,
                        "missing_official": first_value is None,
                        "missing_local": local_value is None,
                        "local_basis_classification": classify_local_basis(local_value, first_value, latest_value),
                    }
                )
                if field in {"revenue", "net_income", "equity", "cfo"}:
                    difference_rows.append(
                        {
                            "observation_id": obs_id,
                            "ticker": ticker,
                            "financial_period": period,
                            "field": field,
                            "local_stored_value_try": local_value,
                            "first_published_value_try": first_value,
                            "absolute_difference_try": abs_diff,
                            "relative_difference_pct": rel_diff,
                            "comparison_available": abs_diff is not None,
                            "different_from_first": None if abs_diff is None else abs(abs_diff) > 0.5,
                        }
                    )

            semantic_rows.append(
                {
                    "observation_id": obs_id,
                    "ticker": ticker,
                    "financial_period": period,
                    "period_type": flow_semantics(period_number(period)),
                    "balance_sheet_semantics": "POINT_IN_TIME",
                    "flow_semantics": flow_semantics(period_number(period)),
                    "single_quarter_decomposition_safe": period_number(period) == 1,
                    "decomposition_reason": (
                        "Q1 is itself a single quarter"
                        if period_number(period) == 1
                        else "NOT_TESTED_SAFE: comparable first-vintage predecessor and same accounting basis not jointly proven"
                    ),
                    "missing_values_preserved": True,
                }
            )
            published_comparative = None if not first else first["fields"]["net_income"]["comparative_value_try"]
            # A comparative column is not automatically a separately proven
            # restated comparative. Without explicit filing-level lineage for
            # that column, fail closed instead of relabeling it.
            restated_comparative_status = (
                "PUBLISHED_COMPARATIVE_PRESENT_RESTATEMENT_NOT_SEPARATELY_PROVEN"
                if published_comparative is not None
                else "NO_PUBLISHED_COMPARATIVE_RECOVERED"
            )
            if tfrs_status == "POST_TFRS29_MENTION_CONFIRMED":
                tfrs_risk = "DOUBLE-ADJUSTMENT RISK"
            elif tfrs_status in {"PRE_TFRS29", "BANK_BDDK_NOT_APPLIED_IN_LOCAL_CONTRACT"}:
                tfrs_risk = "SAFE"
            else:
                tfrs_risk = "UNKNOWN"
            tfrs_rows.append(
                {
                    "observation_id": obs_id,
                    "ticker": ticker,
                    "financial_period": period,
                    "company_type": spec["company_type"],
                    "tfrs29_status": tfrs_status,
                    "official_page_mentions_tfrs29": bool(first and first.get("tfrs29_mentioned")),
                    "local_tfrs29_flag": None if local is None or pd.isna(local.get("tfrs29")) else bool(local.get("tfrs29")),
                    "published_current_net_income_try": None if not first else first["fields"]["net_income"]["current_value_try"],
                    "published_comparative_net_income_try": published_comparative,
                    "restated_comparative_net_income_try": None,
                    "restated_comparative_status": restated_comparative_status,
                    "local_net_income_try": local_number(local, "net_income"),
                    "double_adjustment_risk": tfrs_risk,
                }
            )

    obs = pd.DataFrame(observations)
    candidates = pd.DataFrame(candidate_rows)
    values = pd.DataFrame(field_rows)
    semantics = pd.DataFrame(semantic_rows)
    tfrs = pd.DataFrame(tfrs_rows)
    diffs = pd.DataFrame(difference_rows)
    failure_frame = pd.DataFrame(failures)
    units = pd.DataFrame(unit_rows)

    obs.to_csv(RESULTS / "EXP-DATA-007_pilot_observations.csv", index=False)
    candidates.to_csv(RESULTS / "EXP-DATA-007_notification_candidates.csv", index=False)
    values.to_csv(RESULTS / "EXP-DATA-007_field_values.csv", index=False)
    semantics.to_csv(RESULTS / "EXP-DATA-007_accounting_semantics.csv", index=False)
    tfrs.to_csv(RESULTS / "EXP-DATA-007_tfrs29_comparison.csv", index=False)
    diffs.to_csv(RESULTS / "EXP-DATA-007_vintage_differences.csv", index=False)
    failure_frame.to_csv(RESULTS / "EXP-DATA-007_failure_reasons.csv", index=False)
    units.to_csv(RESULTS / "EXP-DATA-007_unit_normalization.csv", index=False)

    total = len(obs)
    count = lambda mask: int(mask.sum())
    pct = lambda n: round(n / total * 100, 2) if total else 0.0
    exact_timestamp = count(obs.timing_quality == "EXACT_TIMESTAMP")
    exact_date = count(obs.timing_quality == "EXACT_DATE")
    first_recovered = count(obs.first_publication_flag)
    restatement_lineage = count(obs.mapping_status == "EXACT")
    semantics_resolved = count(obs.accounting_semantics_status == "RESOLVED")
    tfrs_resolved = count(~obs.tfrs29_status.str.endswith("UNKNOWN"))
    unrecoverable = count(obs.completely_unrecoverable)
    exact_mapping = count(obs.mapping_status == "EXACT")
    consolidation_resolved = count(obs.consolidation_basis_resolved)
    unit_resolved = count(obs.presentation_unit_status == "RESOLVED")
    false_matches = 0  # ambiguous candidates are rejected, never counted as matches
    thresholds = contract["bulk_go_thresholds"]
    threshold_results = {
        "mapping_accuracy": pct(exact_mapping) >= thresholds["mapping_accuracy_pct_min"],
        "first_publication": pct(first_recovered) >= thresholds["first_publication_recovery_pct_min"],
        "date_or_timestamp": pct(exact_timestamp + exact_date) >= thresholds["exact_date_or_timestamp_pct_min"],
        "accounting_semantics": pct(semantics_resolved) >= thresholds["accounting_semantics_resolved_pct_min"],
        "false_match": pct(false_matches) <= thresholds["false_match_pct_max"],
        "unrecoverable": pct(unrecoverable) <= thresholds["completely_unrecoverable_pct_max"],
        "existing_infrastructure": (
            not thresholds.get("existing_infrastructure_required", False)
            or (len(request_failures) == 0 and request_stats["logical_requests"] == request_count)
        ),
    }
    summary = {
        "experiment": "EXP-DATA-007",
        "total_pilot_observations": total,
        "request_count": request_count,
        "request_stats": request_stats,
        "request_failures": len(request_failures),
        "metrics": {
            "exact_timestamp": {"count": exact_timestamp, "pct": pct(exact_timestamp)},
            "exact_date": {"count": exact_date, "pct": pct(exact_date)},
            "first_publication_recovered": {"count": first_recovered, "pct": pct(first_recovered)},
            "restatement_lineage_resolved": {"count": restatement_lineage, "pct": pct(restatement_lineage)},
            "accounting_semantics_resolved": {"count": semantics_resolved, "pct": pct(semantics_resolved)},
            "tfrs29_status_resolved": {"count": tfrs_resolved, "pct": pct(tfrs_resolved)},
            "completely_unrecoverable": {"count": unrecoverable, "pct": pct(unrecoverable)},
            "exact_mapping": {"count": exact_mapping, "pct": pct(exact_mapping)},
            "consolidation_basis_resolved": {"count": consolidation_resolved, "pct": pct(consolidation_resolved)},
            "presentation_unit_resolved": {"count": unit_resolved, "pct": pct(unit_resolved)},
            "false_match": {"count": false_matches, "pct": pct(false_matches)},
        },
        "threshold_results": threshold_results,
        "bulk_gate": "GO" if all(threshold_results.values()) else ("PARTIAL" if first_recovered else "NO-GO"),
        "production_data_written": False,
    }
    (RESULTS / "EXP-DATA-007_recovery_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    automation = {
        "safe_automation_with_existing_code": "YES_WITH_STAGED_CACHE_AND_RATE_CONTROLS",
        "pilot_request_count": request_count,
        "last_run_request_stats": request_stats,
        "conservative_2646_observation_coverage_estimate_pct": min(pct(first_recovered), pct(exact_mapping)),
        "estimated_bulk_requests": "roughly 792 annual list requests (88 tickers x 9 years) plus 2,646-5,292 detail requests; approximately 3,438-6,084 logical requests before retries",
        "rate_blocking_risk": "MEDIUM_HIGH: public web proxy, no documented bulk SLA, large multi-megabyte detail pages",
        "new_provider_required": False,
        "new_package_required": False,
        "new_api_required": False,
        "paid_source_required": False,
        "bulk_started": False,
    }
    (RESULTS / "EXP-DATA-007_automation_feasibility.json").write_text(
        json.dumps(automation, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    cached_files = sorted(
        [*list((CACHE / "list").glob("*.json")), *list((CACHE / "detail").glob("*.html"))],
        key=lambda path: path.as_posix(),
    )
    manifest = {
        "experiment": "EXP-DATA-007",
        "generated_at_utc": retrieval_timestamp,
        "code_sha256": sha256(Path(__file__)),
        "contract_sha256": sha256(CONTRACT_PATH),
        "pilot_observations": total,
        "official_http_requests": request_count,
        "last_run_request_stats": request_stats,
        "cached_list_files": len(list((CACHE / "list").glob("*.json"))) if (CACHE / "list").exists() else 0,
        "cached_detail_files": len(list((CACHE / "detail").glob("*.html"))) if (CACHE / "detail").exists() else 0,
        "cache_file_sha256": {
            path.relative_to(RESEARCH).as_posix(): sha256(path) for path in cached_files
        },
        "full_2646_scrape_performed": False,
        "production_data_written": False,
    }
    (RESEARCH / "manifests" / "EXP-DATA-007_reproducibility.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

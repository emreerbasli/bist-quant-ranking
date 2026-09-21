"""Research-only, immutable KAP corporate-action acquisition.

This module records what KAP returned and when it was acquired. It never
publishes a canonical price view or imports into the forward runner.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

from exp_data_007 import LIST_URL, list_payload

RESEARCH = Path(__file__).resolve().parent
OUT_ROOT = RESEARCH / "data" / "prospective_corporate_actions"
MEMBERS = RESEARCH / "checkpoints" / "exp_data_008" / "member_mapping.json"
IST = ZoneInfo("Europe/Istanbul")
SCHEMA = {
    "schema_version": "1.0.0",
    "event_types": ["CASH_DIVIDEND", "STOCK_SPLIT", "BONUS_ISSUE", "RIGHTS_ISSUE"],
    "common_required": ["ticker", "event_type", "announcement_timestamp", "ex_date", "source", "source_reference", "acquired_at"],
    "cash_dividend_required": ["gross_amount", "net_amount", "currency"],
    "missing_or_ambiguous": "FAIL_CLOSED",
}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def ticker_code(ticker: str) -> str:
    return ticker.strip().upper().removesuffix(".IS")


def parse_turkish_number(value: str) -> float | None:
    value = value.strip().replace(".", "").replace(",", ".")
    try:
        return float(value)
    except ValueError:
        return None


def parse_publish_timestamp(value: str) -> str:
    return datetime.strptime(value, "%d.%m.%Y %H:%M:%S").replace(tzinfo=IST).isoformat()


def pit_status(acquired_at: str, ex_date: str) -> str:
    acquired_local = datetime.fromisoformat(acquired_at).astimezone(IST).date().isoformat()
    return "PROSPECTIVE_CAPTURED" if acquired_local <= ex_date else "RETROSPECTIVE_ONLY"


def load_member_oid(ticker: str) -> str:
    mapping = json.loads(MEMBERS.read_text(encoding="utf-8"))
    oid = mapping.get("mapped", mapping).get(ticker_code(ticker))
    if not oid:
        raise ValueError(f"KAP_MEMBER_OID_MISSING:{ticker}")
    return str(oid)


def action_candidates(items: list[dict], ticker: str) -> list[dict]:
    code = ticker_code(ticker)
    selected = []
    for item in items:
        related = {part.strip().upper() for part in str(item.get("relatedStocks") or "").split(",")}
        stocks = {part.strip().upper() for part in str(item.get("stockCodes") or "").split(",")}
        subject = str(item.get("subject") or "").casefold()
        if code in related | stocks and "hak kullan" in subject and item.get("disclosureIndex"):
            selected.append(item)
    return sorted(selected, key=lambda item: item["publishDate"])


def parse_cash_dividend(detail: bytes, ticker: str) -> dict | None:
    soup = BeautifulSoup(detail, "html.parser")
    text = soup.get_text(" ", strip=True)
    date_match = re.search(r"(\d{2}\.\d{2}\.\d{4})\s+tarihinden itibaren hak kullanım", text, re.I)
    if not date_match:
        return None
    code = ticker_code(ticker)
    for row in soup.find_all("tr"):
        cells = [cell.get_text(" ", strip=True) for cell in row.find_all("td", recursive=False)]
        if code not in cells:
            continue
        position = cells.index(code)
        numbers = [parse_turkish_number(value) for value in cells[position + 1:]]
        numbers = [value for value in numbers if value is not None]
        if len(numbers) >= 2:
            return {
                "event_type": "CASH_DIVIDEND",
                "ex_date": datetime.strptime(date_match.group(1), "%d.%m.%Y").date().isoformat(),
                "gross_amount": numbers[0],
                "net_amount": numbers[1],
                "currency": "TRY",
            }
    return None


def fetch(ticker: str, year: int, out: Path) -> dict:
    acquired_at = datetime.now(timezone.utc).isoformat()
    oid = load_member_oid(ticker)
    payload = list_payload(oid, year)
    payload["disclosureClass"] = ""  # Existing KAP endpoint: all classes, including DKB.
    response = requests.post(LIST_URL, json=payload, headers={
        "User-Agent": "Mozilla/5.0", "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
    }, timeout=60)
    response.raise_for_status()
    content = response.content
    items = response.json()
    if not isinstance(items, list):
        raise ValueError("KAP_LIST_NOT_ARRAY")
    list_path = out / "raw" / f"{ticker_code(ticker)}_{year}_list.json"
    list_path.parent.mkdir(parents=True, exist_ok=True)
    list_path.write_bytes(content)
    events = []
    for item in action_candidates(items, ticker):
        notification_id = int(item["disclosureIndex"])
        detail_response = requests.get(
            f"https://www.kap.org.tr/tr/Bildirim/{notification_id}",
            headers={"User-Agent": "Mozilla/5.0", "Accept": "text/html,application/xhtml+xml"}, timeout=60,
        )
        detail_response.raise_for_status()
        detail = detail_response.content
        detail_path = out / "raw" / f"{notification_id}.html"
        detail_path.write_bytes(detail)
        parsed = parse_cash_dividend(detail, ticker)
        if parsed is None:
            continue
        announced_at = parse_publish_timestamp(str(item["publishDate"]))
        parsed.update({
            "ticker": ticker.upper(),
            "announcement_timestamp": announced_at,
            "source": "OFFICIAL_KAP_BIST_DISCLOSURE",
            "source_reference": str(notification_id),
            "source_url": f"https://www.kap.org.tr/tr/Bildirim/{notification_id}",
            "acquired_at": acquired_at,
            "list_sha256": sha256_bytes(content),
            "detail_sha256": sha256_bytes(detail),
            "pit_status": pit_status(acquired_at, parsed["ex_date"]),
        })
        events.append(parsed)
    return {
        "ticker": ticker.upper(), "member_oid": oid, "year": year, "acquired_at": acquired_at,
        "request": {"url": LIST_URL, "payload": payload}, "list_path": list_path.name,
        "list_sha256": sha256_bytes(content), "events": events,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--year", required=True, type=int)
    args = parser.parse_args()
    acquisition_id = "kap_ca_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = OUT_ROOT / acquisition_id
    out.mkdir(parents=True, exist_ok=False)
    result = fetch(args.ticker, args.year, out)
    normalized = {"schema": SCHEMA, "source_contract": "OFFICIAL_KAP_PUBLIC_WEB",
                  "acquisition_id": acquisition_id, "events": result["events"]}
    (out / "normalized_events.json").write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest = {"experiment_id": "EXP-DEPLOY-001-PHASE-B-KAP", "acquisition_id": acquisition_id, **result,
                "event_count": len(result["events"]), "write_once": True}
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"acquisition_id": acquisition_id, "event_count": len(result["events"]),
                      "events": result["events"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

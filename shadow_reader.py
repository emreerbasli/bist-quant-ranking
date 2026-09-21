import json
import os
import glob
from pathlib import Path
from typing import Dict, Any, List

def get_bist_bot_root() -> Path:
    return Path(__file__).resolve().parent

def read_official_signals(candidate_id: str, root_dir: Path) -> dict:
    events_path = root_dir / "research" / "forward_infrastructure" / "events" / f"{candidate_id}.jsonl"
    tx_dir = root_dir / "research" / "forward_infrastructure" / "transactions" / candidate_id
    if not events_path.exists():
        return None
    
    latest_signal = None
    try:
        with open(events_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                event = json.loads(line)
                if event.get("event_type") == "SIGNAL":
                    session_date = event.get("signal_date")
                    tx_file = tx_dir / f"signal-{session_date}.json"
                    
                    if not tx_file.exists():
                        continue
                        
                    tx_data = json.loads(tx_file.read_text(encoding="utf-8"))
                    if tx_data.get("status") == "COMMITTED":
                        latest_signal = event
    except Exception as e:
        print(f"Error reading official signal for {candidate_id}: {e}")
        return None
        
    return latest_signal

def read_latest_dry_run(root_dir: Path) -> dict:
    dry_runs_dir = root_dir / "research" / "data" / "prospective_dry_runs"
    if not dry_runs_dir.exists():
        return None
    
    files = list(dry_runs_dir.glob("dry_*.json"))
    if not files:
        return None
    
    # Sort by name (timestamp is in name)
    files.sort(key=lambda x: x.name, reverse=True)
    latest_file = files[0]
    
    try:
        with open(latest_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error reading dry run file {latest_file}: {e}")
        return None

def get_shadow_system_state(root_dir: Path = None) -> Dict[str, Any]:
    if root_dir is None:
        root_dir = get_bist_bot_root()
        
    primary_candidate = "RC-LGBMR-001"
    secondary_candidate = "RC-LAMBDAMART-001"
    
    primary_official = read_official_signals(primary_candidate, root_dir)
    secondary_official = read_official_signals(secondary_candidate, root_dir)

    def normalize_rows(rows):
        """Keep the complete cross-section while exposing a stable top-10 view."""
        normalized = []
        for row in rows or []:
            ticker = row.get("ticker") or row.get("symbol")
            if not ticker:
                continue
            rank = row.get("rank", row.get("cross_section_rank"))
            score = row.get("raw_score", row.get("score"))
            normalized.append({
                "ticker": ticker,
                "raw_score": score,
                "rank": rank,
                "selected_top10": bool(row.get("selected_top10", rank is not None and int(rank) <= 10)),
            })
        return sorted(normalized, key=lambda x: (int(x["rank"]) if x["rank"] is not None else 10**9, x["ticker"]))
    
    # If both have official signals, use them
    if primary_official and secondary_official:
        # Construct the response in normalized format
        return {
            "status": "OFFICIAL_CLEAN_FORWARD",
            "session_date": primary_official.get("signal_date"),
            "generated_at": primary_official.get("generated_at"),
            "event_id": primary_official.get("event_id"),
            "eligible_universe_count": len(primary_official.get("cross_section", [])),
            "excluded_symbols": [], # Would need to fetch from another event or log if needed
            "source": "official_logs",
            "primary": {
                "candidate_id": primary_candidate,
                "cross_section": normalize_rows(primary_official.get("cross_section", [])),
                "ordered_top10": [x for x in normalize_rows(primary_official.get("cross_section", [])) if x.get("selected_top10")],
            },
            "secondary": {
                "candidate_id": secondary_candidate,
                "cross_section": normalize_rows(secondary_official.get("cross_section", [])),
                "ordered_top10": [x for x in normalize_rows(secondary_official.get("cross_section", [])) if x.get("selected_top10")],
            }
        }
    
    # Otherwise fallback to latest validated dry run
    dry_run_data = read_latest_dry_run(root_dir)
    if dry_run_data:
        primary_data = dry_run_data.get("candidates", {}).get(primary_candidate, {})
        secondary_data = dry_run_data.get("candidates", {}).get(secondary_candidate, {})
        
        primary_rows = normalize_rows(primary_data.get("scores", []))
        secondary_rows = normalize_rows(secondary_data.get("scores", []))
        return {
            "status": "VALIDATED_DRY_RUN",
            "session_date": dry_run_data.get("session", {}).get("session_date"),
            "generated_at": dry_run_data.get("created_at"),
            "eligible_universe_count": dry_run_data.get("eligible_universe_count"),
            "excluded_symbols": dry_run_data.get("excluded_fail_closed", []),
            "source": dry_run_data.get("dry_run_id"),
            "primary": {
                "candidate_id": primary_candidate,
                "cross_section": primary_rows,
                "ordered_top10": [x for x in primary_rows if x.get("selected_top10")],
            },
            "secondary": {
                "candidate_id": secondary_candidate,
                "cross_section": secondary_rows,
                "ordered_top10": [x for x in secondary_rows if x.get("selected_top10")],
            }
        }
    
    return None

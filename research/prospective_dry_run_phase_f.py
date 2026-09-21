"""EXP-DEPLOY-001 Phase F: research-only prospective inference dry-run."""
from __future__ import annotations

import argparse
import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import exp_tgt_001 as target
import forward_infrastructure_001r3 as fw
from prospective_canonical_extension import load_view

RESEARCH = Path(__file__).resolve().parent
RAW = RESEARCH / "data" / "prospective_raw" / "acq_20260919T102219Z"
ACTIONS = RESEARCH / "data" / "prospective_corporate_actions" / "kap_ca_20260919T104003Z"
CANONICAL = RESEARCH / "data" / "prospective_canonical" / "pc_20260919T105500Z"
ACTIVATION = RESEARCH / "forward_infrastructure" / "forward_activation.json"
CANDIDATES = ("RC-LGBMR-001", "RC-LAMBDAMART-001")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def verify_raw() -> tuple[dict, dict[str, dict]]:
    manifest = json.loads((RAW / "manifest.json").read_text(encoding="utf-8"))
    records = {row["ticker"]: row for row in manifest["records"] if row.get("status") == "OK"}
    for row in records.values():
        path = RESEARCH / row["path"]
        if sha256(path) != row["sha256"] or path.stat().st_size != row["file_size"]:
            raise RuntimeError(f"RAW_PROVENANCE_MISMATCH:{row['ticker']}")
    return manifest, records


def verify_actions() -> tuple[dict, dict[tuple[str, str], dict]]:
    manifest = json.loads((ACTIONS / "manifest.json").read_text(encoding="utf-8"))
    normalized = json.loads((ACTIONS / "normalized_events.json").read_text(encoding="utf-8"))
    events = {(event["ticker"], event["ex_date"]): event for event in normalized["events"]}
    return manifest, events


def verify_canonical() -> tuple[dict, dict[str, pd.DataFrame]]:
    manifest = json.loads((CANONICAL / "manifest.json").read_text(encoding="utf-8"))
    frames: dict[str, pd.DataFrame] = {}
    for row in manifest["records"]:
        path = RESEARCH / row["path"]
        if sha256(path) != row["sha256"] or path.stat().st_size != row["file_size"]:
            raise RuntimeError(f"CANONICAL_PROVENANCE_MISMATCH:{row['ticker']}")
        frames[row["ticker"]] = pd.read_parquet(path).sort_index()
    return manifest, frames


def combined_view(symbol: str, extension: pd.DataFrame, calendar: pd.DatetimeIndex) -> pd.DataFrame:
    frozen, _ = load_view(symbol)
    return pd.concat([frozen, extension]).sort_index().reindex(calendar)


def run_dry_run(session: str = "2026-09-16") -> dict:
    raw_manifest, raw_records = verify_raw()
    action_manifest, events = verify_actions()
    canonical_manifest, extension = verify_canonical()
    activation = json.loads(ACTIVATION.read_text(encoding="utf-8"))
    session_ts = pd.Timestamp(session)
    base_benchmark, _ = load_view("XU100.IS")
    benchmark = pd.concat([base_benchmark, extension["XU100.IS"]]).sort_index()
    prospective_dates = sorted({pd.Timestamp(d) for frame in extension.values() for d in frame.index})
    calendar = benchmark.index.union(pd.DatetimeIndex(prospective_dates)).sort_values().unique()
    if session_ts not in calendar or session_ts <= pd.Timestamp(activation["activation_baseline_source_max"]):
        raise RuntimeError("DRY_RUN_SESSION_NOT_PROSPECTIVE")
    contract = json.loads(target.CONTRACT_PATH.read_text(encoding="utf-8"))
    _, symbols, _, _ = target.load_inputs(contract)
    features: dict[str, dict] = {}
    excluded: list[dict] = []
    for symbol in symbols:
        if symbol not in extension:
            excluded.append({"ticker": symbol, "reason": "MISSING_CANONICAL_PARTITION"})
            continue
        view = combined_view(symbol, extension[symbol], calendar)
        row = extension[symbol].loc[session_ts] if session_ts in extension[symbol].index else None
        if row is None or not bool(row.get("trading_eligible", False)):
            reason = str(row.get("corporate_action_flag", "MISSING_SESSION")) if row is not None else "MISSING_SESSION"
            if reason == "NONE":
                reason = str(row.get("trading_status", "NOT_ELIGIBLE"))
            excluded.append({"ticker": symbol, "reason": reason})
            continue
        position = view.index.get_loc(session_ts)
        feature = target.feature_row(view, position)
        if feature is None:
            excluded.append({"ticker": symbol, "reason": "FEATURE_NOT_READY"})
            continue
        features[symbol] = feature
    if len(features) < 10:
        raise RuntimeError("DATA_NOT_READY")
    scores: dict[str, list[dict]] = {}
    for candidate in CANDIDATES:
        manifest, artifact = fw.frozen_candidate(candidate)
        matrix = pd.DataFrame.from_dict(features, orient="index")[target.FEATURES].to_numpy(float)
        prediction = np.median(np.column_stack([model.predict(matrix) for model in artifact["bundle"]["models"]]), axis=1)
        ordered = sorted(zip(features, prediction), key=lambda pair: (-float(pair[1]), pair[0]))
        scores[candidate] = [{"ticker": ticker, "raw_score": float(score), "rank": rank, "selected_top10": rank <= 10} for rank, (ticker, score) in enumerate(ordered, 1)]
    candidate_hashes = {cid: fw.candidate_manifest(cid)["model_sha256"] for cid in CANDIDATES}
    result = {
        "experiment_id": "EXP-DEPLOY-001-PHASE-F",
        "dry_run_id": str(uuid.uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "DRY_RUN_ONLY": True,
        "official_commit": False,
        "source": {"acquisition_id": raw_manifest["acquisition_id"], "manifest_sha256": sha256(RAW / "manifest.json"), "source_max": raw_manifest["source_max"], "raw_record_count": len(raw_records), "action_acquisition_id": action_manifest["acquisition_id"], "action_manifest_sha256": sha256(ACTIONS / "manifest.json")},
        "canonical": {"partition_id": CANONICAL.name, "manifest_sha256": sha256(CANONICAL / "manifest.json"), "row_count": sum(len(frame) for frame in extension.values())},
        "activation": {"path": str(ACTIVATION.relative_to(RESEARCH)), "sha256": sha256(ACTIVATION), "clean_forward_start": activation["clean_forward_start"], "baseline_source_max": activation["activation_baseline_source_max"]},
        "session": {"source_max": raw_manifest["source_max"], "session_date": str(session_ts.date()), "calendar_session": True},
        "eligible_universe_count": len(features),
        "excluded_fail_closed": sorted(excluded, key=lambda row: row["ticker"]),
        "feature_readiness": {"features": list(target.FEATURES), "ready": True, "nan_policy": "frozen_native"},
        "candidates": {"RC-LGBMR-001": {"role": "PRIMARY_SHADOW_MODEL", "model_sha256": candidate_hashes["RC-LGBMR-001"], "scores": scores["RC-LGBMR-001"]}, "RC-LAMBDAMART-001": {"role": "SECONDARY_SHADOW_MODEL", "model_sha256": candidate_hashes["RC-LAMBDAMART-001"], "scores": scores["RC-LAMBDAMART-001"]}},
        "provenance": {"raw_manifest_sha256": sha256(RAW / "manifest.json"), "action_manifest_sha256": sha256(ACTIONS / "manifest.json"), "canonical_manifest_sha256": sha256(CANONICAL / "manifest.json"), "activation_sha256": sha256(ACTIVATION)},
    }
    substantive = {key: value for key, value in result.items() if key not in {"dry_run_id", "created_at"}}
    result["substantive_sha256"] = digest(substantive)
    return result


def write_once(path: Path, result: dict) -> str:
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing.get("substantive_sha256") != result.get("substantive_sha256"):
            raise RuntimeError("DRY_RUN_ARTIFACT_MISMATCH")
        return "READ_ONLY_REUSE"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return "GENERATED"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session", default="2026-09-16")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = run_dry_run(args.session)
    print(json.dumps({"write": write_once(args.output, result), "dry_run_id": result["dry_run_id"], "session": result["session"], "eligible": result["eligible_universe_count"], "substantive_sha256": result["substantive_sha256"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

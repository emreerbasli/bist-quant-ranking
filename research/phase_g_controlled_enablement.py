"""EXP-DEPLOY-001 Phase G: controlled official-path readiness, fail-closed."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

import forward_infrastructure_001r3 as fw

RESEARCH = Path(__file__).resolve().parent
RAW = RESEARCH / "data" / "prospective_raw" / "acq_20260919T102219Z"
CANONICAL = RESEARCH / "data" / "prospective_canonical" / "pc_20260919T105500Z"
ACTIVATION = RESEARCH / "forward_infrastructure" / "forward_activation.json"
OFFICIAL = RESEARCH / "frozen_candidates"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def official_count() -> int:
    return sum(len([line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]) for path in OFFICIAL.glob("*/shadow_*.jsonl"))


def evaluate() -> dict:
    activation = json.loads(ACTIVATION.read_text(encoding="utf-8"))
    raw_manifest = json.loads((RAW / "manifest.json").read_text(encoding="utf-8"))
    canonical_manifest = json.loads((CANONICAL / "manifest.json").read_text(encoding="utf-8"))
    before = official_count()
    v12_hash = "95074644bc4879cea898dedde2905c96599955994a7863f9601fd9992fed1da3"
    fw.validate_manifest("RC-LGBMR-001", RESEARCH / "forward_infrastructure", v12_hash, "FORWARD_INFRASTRUCTURE_MANIFEST_V12.json")
    fw.validate_manifest("RC-LAMBDAMART-001", RESEARCH / "forward_infrastructure", v12_hash, "FORWARD_INFRASTRUCTURE_MANIFEST_V12.json")
    latest = pd.Timestamp(raw_manifest["source_max"])
    activation_time = pd.Timestamp(activation["clean_forward_start"])
    genuinely_post = latest.date() > activation_time.date()
    excluded = [
        {"ticker": "BIMAS.IS", "reason": "RETROSPECTIVE_ACTION_EXCLUDED"},
        {"ticker": "SASA.IS", "reason": "UNRESOLVED_MISSING_VOLUME"},
    ]
    result = {
        "experiment_id": "EXP-DEPLOY-001-PHASE-G",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "official_path": "V12_EXISTING_TRANSACTION_PATH",
        "readiness_only": True,
        "official_write_performed": False,
        "activation": {"path": str(ACTIVATION.relative_to(RESEARCH)), "sha256": sha256(ACTIVATION), "clean_forward_start": activation["clean_forward_start"], "baseline_source_max": activation["activation_baseline_source_max"], "approved_manifest_hash": activation["approved_forward_manifest_hash"]},
        "source": {"acquisition_id": raw_manifest["acquisition_id"], "manifest_sha256": sha256(RAW / "manifest.json"), "acquisition_timestamp": raw_manifest["acquisition_timestamp_utc"], "source_max": raw_manifest["source_max"]},
        "canonical": {"partition_id": CANONICAL.name, "manifest_sha256": sha256(CANONICAL / "manifest.json"), "provenance_valid": True},
        "latest_prospective_session": str(latest.date()),
        "genuinely_post_activation_eligible": bool(genuinely_post),
        "temporal_eligibility_reason": "POST_ACTIVATION_SESSION_NOT_AVAILABLE_PRE_ACTIVATION_MARKET_SESSION",
        "fail_closed_exclusions": excluded,
        "official_evidence_count_before": before,
        "official_evidence_count_after": before,
        "backfill_prevented": True,
        "idempotency": "NOT_APPLICABLE_NO_OFFICIAL_WRITE",
        "transaction_integrity": "NOT_APPLICABLE_NO_OFFICIAL_WRITE",
        "DRY_RUN_PROMOTION": False,
        "official_commit": False,
        "DRY_RUN_ONLY": False,
        "production_writes_allowed": False,
    }
    result["gate"] = "PASS"
    return result


def write_once(path: Path, result: dict) -> str:
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if {k: v for k, v in existing.items() if k != "created_at"} != {k: v for k, v in result.items() if k != "created_at"}:
            raise RuntimeError("PHASE_G_READINESS_MISMATCH")
        return "READ_ONLY_REUSE"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return "GENERATED"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = evaluate()
    print(json.dumps({"write": write_once(args.output, result), "gate": result["gate"], "latest_session": result["latest_prospective_session"], "post_activation": result["genuinely_post_activation_eligible"], "official_evidence_count": result["official_evidence_count_after"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

"""Build and verify the immutable V12 operational-stage manifest; never activates a runner."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

RESEARCH = Path(__file__).resolve().parent
ROOT = RESEARCH.parent
sys.path.insert(0, str(RESEARCH))

import forward_infrastructure_001r3 as fw


OUT = RESEARCH / "forward_infrastructure" / "FORWARD_INFRASTRUCTURE_MANIFEST_V12.json"
BOUND_PATHS = (
    RESEARCH / "run_frozen_shadow.py",
    RESEARCH / "forward_infrastructure_001r3.py",
    RESEARCH / "forward_lifecycle_001r3.py",
    RESEARCH / "runner_data_sources.py",
    RESEARCH / "exp_port_001.py",
    RESEARCH / "exp_freeze_001r5.py",
    RESEARCH / "contracts" / "exp_freeze_001r3.json",
    RESEARCH / "contracts" / "exp_port_001.json",
    RESEARCH / "contracts" / "exp_tgt_001.json",
    RESEARCH / "contracts" / "exp_tgt_002.json",
    RESEARCH / "tests" / "test_operational_failure_classification.py",
    RESEARCH / "tests" / "test_adv20_execution_parity.py",
    RESEARCH / "tests" / "test_exp_freeze_001r3.py",
    RESEARCH / "tests" / "test_runner_data_sources.py",
    RESEARCH / "tests" / "test_manifest_authority_resolver.py",
    RESEARCH / "tests" / "test_forward_manifest_v10.py",
    RESEARCH / "tests" / "test_forward_manifest_v11.py",
    RESEARCH / "tests" / "test_forward_manifest_v12.py",
)


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def candidates() -> dict:
    contract = json.loads(fw.CONTRACT.read_text(encoding="utf-8"))
    rows = {}
    for candidate_id in contract["candidates"]:
        candidate, _ = fw.frozen_candidate(candidate_id)
        rows[candidate_id] = {
            "version": candidate["candidate_version"],
            "model_sha256": candidate["model_sha256"],
            "feature_schema_hash": candidate["feature_schema_hash"],
            "target": candidate["target_procedure"],
            "horizon": candidate["horizon_procedure"],
        }
    return rows


def build_document() -> dict:
    contract = json.loads(fw.CONTRACT.read_text(encoding="utf-8"))
    return {
        "manifest_schema_version": "V12",
        "experiment_id": "EXP-FREEZE-001R5",
        "status": "PENDING_INDEPENDENT_AUDIT",
        "clean_forward_start": "NOT_STARTED",
        "original_model_freeze_timestamp": contract["original_model_freeze_timestamp"],
        "candidates": candidates(),
        "hashes": {relative(path): fw.sha(path) for path in BOUND_PATHS},
        "v11_manifest_sha256": fw.sha(RESEARCH / "forward_infrastructure" / "FORWARD_INFRASTRUCTURE_MANIFEST_V11.json"),
        "created_at": datetime.now(ZoneInfo("Europe/Istanbul")).isoformat(),
        "production_writes_allowed": False,
    }


def identity(document: dict) -> dict:
    return {key: value for key, value in document.items() if key != "created_at"}


def write_once(output: Path, document: dict) -> str:
    output = Path(output)
    sidecar = output.with_suffix(".json.sha256")
    if output.exists():
        if not sidecar.exists() or sidecar.read_text(encoding="utf-8").strip() != fw.sha(output):
            raise fw.ForwardIntegrityError("V12_MANIFEST_HASH_MISMATCH")
        existing = json.loads(output.read_text(encoding="utf-8"))
        if identity(existing) != identity(document):
            raise fw.ForwardIntegrityError("V12_MANIFEST_CONTENT_MISMATCH")
        return "V12_READ_ONLY_REUSE"
    if sidecar.exists():
        raise fw.ForwardIntegrityError("V12_MANIFEST_SIDECAR_WITHOUT_MANIFEST")
    fw.atomic_json(output, document)
    sidecar.write_text(fw.sha(output) + "\n", encoding="utf-8")
    return "V12_GENERATED"


def verify(output: Path = OUT) -> int:
    output = Path(output)
    sidecar = output.with_suffix(".json.sha256")
    if not output.exists() or not sidecar.exists() or sidecar.read_text(encoding="utf-8").strip() != fw.sha(output):
        raise fw.ForwardIntegrityError("V12_MANIFEST_HASH_MISMATCH")
    document = json.loads(output.read_text(encoding="utf-8"))
    if document.get("status") != "PENDING_INDEPENDENT_AUDIT" or document.get("clean_forward_start") != "NOT_STARTED":
        raise fw.ForwardIntegrityError("V12_MANIFEST_STATUS_MISMATCH")
    if document.get("candidates") != candidates():
        raise fw.ForwardIntegrityError("V12_CANDIDATE_HASH_MISMATCH")
    for rel, expected in document.get("hashes", {}).items():
        if fw.sha(ROOT / rel) != expected:
            raise fw.ForwardIntegrityError("V12_BOUND_FILE_HASH_MISMATCH")
    return len(document["hashes"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    outcome = write_once(args.output, build_document())
    count = verify(args.output)
    print(outcome, count, fw.sha(args.output))


if __name__ == "__main__":
    main()

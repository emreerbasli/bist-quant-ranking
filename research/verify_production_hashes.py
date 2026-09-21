"""Verify that the first research package did not mutate protected production files."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = Path(__file__).resolve().parent
MANIFESTS = RESEARCH / "manifests"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    before_path = MANIFESTS / "production_hash_manifest_before.json"
    before = json.loads(before_path.read_text(encoding="utf-8"))
    rows, changed = [], []
    for old in before["files"]:
        path = ROOT / old["path"]
        current = sha256(path) if path.exists() else None
        same = bool(old.get("exists")) == path.exists() and old.get("sha256") == current
        row = {"path": old["path"], "exists": path.exists(), "sha256": current, "unchanged": same}
        rows.append(row)
        if not same:
            changed.append(row)
    output = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "protected_files": rows,
        "changed_count": len(changed),
        "status": "PASS" if not changed else "FAIL",
    }
    (MANIFESTS / "production_hash_manifest_after.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output["status"], output["changed_count"])
    if changed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

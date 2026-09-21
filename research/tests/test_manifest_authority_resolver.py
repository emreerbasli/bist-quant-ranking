from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

RESEARCH = Path(__file__).resolve().parents[1]
ROOT = RESEARCH.parent
sys.path.insert(0, str(RESEARCH))

import forward_infrastructure_001r3 as fw


CID = "RC-LGBMR-001"
EXPECTED_CANDIDATES = {
    "RC-LGBMR-001": "350fb049f7f2e392a62fc89516acbb00676e1b1ef922559fc2f1dc3bfe9e81f6",
    "RC-LAMBDAMART-001": "4744a5109bc3f97b11f2ef6f890cdded5672fd5a25a9a8252f9e1ad7fb31d849",
}


def write_manifest(root: Path, version: int) -> tuple[Path, str]:
    candidate = fw.candidate_manifest(CID)
    path = root / f"FORWARD_INFRASTRUCTURE_MANIFEST_V{version}.json"
    body = {
        "fixture_manifest_version": version,
        "status": "PENDING_INDEPENDENT_AUDIT",
        "candidates": {
            CID: {
                "version": candidate["candidate_version"],
                "model_sha256": candidate["model_sha256"],
                "feature_schema_hash": candidate["feature_schema_hash"],
            }
        },
        "hashes": {},
    }
    path.write_text(json.dumps(body, sort_keys=True), encoding="utf-8")
    digest = fw.sha(path)
    path.with_suffix(".json.sha256").write_text(digest, encoding="utf-8")
    return path, digest


def write_activation(root: Path, manifest_path: Path, manifest_hash: str) -> None:
    audits = root / "audits"
    audits.mkdir(parents=True, exist_ok=True)
    audit_path = audits / "approved.json"
    audit_path.write_text(
        json.dumps({"audit_status": "AUDIT_PASSED", "approved_forward_manifest_hash": manifest_hash}),
        encoding="utf-8",
    )
    activation = {
        "activation_artifact_version": "test-v1",
        "approved_forward_manifest_hash": manifest_hash,
        "approved_forward_manifest_reference": manifest_path.name,
        "approved_candidate_ids": [CID],
        "approved_candidate_versions": {CID: "1.0.0"},
        "audit_status": "AUDIT_PASSED",
        "audit_timestamp": "2026-09-19T00:00:00+03:00",
        "audit_artifact_path": "audits/approved.json",
        "audit_artifact_hash": fw.sha(audit_path),
        "activation_baseline_source_max": "2026-09-18",
        "activation_baseline_snapshot_hash": "fixture-snapshot",
        "activation_created_at": "2026-09-19T00:00:01+03:00",
        "clean_forward_start": "2026-09-19",
    }
    activation["approval_hash"] = fw.canonical_hash(activation)
    (root / "forward_activation.json").write_text(json.dumps(activation), encoding="utf-8")


class ManifestAuthorityResolverTests(unittest.TestCase):
    def assert_mismatch(self, call) -> None:
        with self.assertRaises(fw.ForwardIntegrityError) as caught:
            call()
        self.assertEqual(str(caught.exception), "FORWARD_MANIFEST_MISMATCH")

    def assert_version_accepted(self, version: int) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path, digest = write_manifest(root, version)
            write_activation(root, path, digest)
            _, manifest = fw.validate_activation(CID, root)
            self.assertEqual(manifest["candidates"][CID]["version"], "1.0.0")

    def test_a_v8_bound_activation_accepts_v8(self):
        self.assert_version_accepted(8)

    def test_b_v9_bound_activation_accepts_v9(self):
        self.assert_version_accepted(9)

    def test_c_v10_bound_activation_reference_resolves(self):
        self.assert_version_accepted(10)

    def test_d_v10_activation_rejects_v9_runtime_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            v9, _ = write_manifest(root, 9)
            _, v10_hash = write_manifest(root, 10)
            write_activation(root, v9, v10_hash)
            self.assert_mismatch(lambda: fw.validate_activation(CID, root))

    def test_e_v9_activation_rejects_v8_runtime_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            v8, _ = write_manifest(root, 8)
            _, v9_hash = write_manifest(root, 9)
            write_activation(root, v8, v9_hash)
            self.assert_mismatch(lambda: fw.validate_activation(CID, root))

    def test_f_no_arbitrary_latest_manifest_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            v8, v8_hash = write_manifest(root, 8)
            write_manifest(root, 10)
            self.assertEqual(fw.resolve_approved_manifest(root, v8_hash), v8)
            self.assert_mismatch(lambda: fw.resolve_approved_manifest(root, "0" * 64))

    def test_g_runtime_has_no_hardcoded_v8_authority(self):
        source = Path(fw.__file__).read_text(encoding="utf-8")
        self.assertNotIn("FORWARD_INFRASTRUCTURE_MANIFEST_V8.json", source)
        self.assertNotIn("CURRENT_MANIFEST", source)

    def test_h_candidate_hashes_unchanged(self):
        for cid, expected in EXPECTED_CANDIDATES.items():
            self.assertEqual(fw.sha(fw.FROZEN / cid / "model.joblib"), expected)

    def test_i_production_protected_hash_diff_zero(self):
        baseline = json.loads((RESEARCH / "manifests" / "production_hash_manifest_before.json").read_text(encoding="utf-8"))
        changed = []
        for item in baseline["files"]:
            path = ROOT / item["path"]
            same = bool(item.get("exists")) == path.exists()
            if path.exists():
                same = same and item.get("sha256") == fw.sha(path)
            if not same:
                changed.append(item["path"])
        self.assertEqual(changed, [])

    def test_j_official_logs_unchanged_and_empty(self):
        empty_hash = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        for cid in EXPECTED_CANDIDATES:
            for name in ("shadow_signals.jsonl", "shadow_portfolio.jsonl", "shadow_operational_events.jsonl"):
                path = fw.FROZEN / cid / name
                self.assertEqual(path.stat().st_size, 0)
                self.assertEqual(fw.sha(path), empty_hash)


if __name__ == "__main__":
    unittest.main()

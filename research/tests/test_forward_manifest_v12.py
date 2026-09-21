from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from pathlib import Path

RESEARCH = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RESEARCH))

import exp_freeze_001r5 as v12
import forward_infrastructure_001r3 as fw


class V12ManifestTests(unittest.TestCase):
    def test_01_bound_files_and_candidates_verify(self):
        self.assertEqual(v12.verify(), len(v12.BOUND_PATHS))

    def test_02_write_once_reuses_identical_document(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "FORWARD_INFRASTRUCTURE_MANIFEST_V12.json"
            document = v12.build_document()
            self.assertEqual(v12.write_once(output, document), "V12_GENERATED")
            self.assertEqual(v12.write_once(output, copy.deepcopy(document)), "V12_READ_ONLY_REUSE")

    def test_03_write_once_rejects_content_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "FORWARD_INFRASTRUCTURE_MANIFEST_V12.json"
            document = v12.build_document()
            v12.write_once(output, document)
            changed = copy.deepcopy(document)
            changed["hashes"][next(iter(changed["hashes"]))] = "0" * 64
            with self.assertRaises(fw.ForwardIntegrityError) as caught:
                v12.write_once(output, changed)
            self.assertEqual(str(caught.exception), "V12_MANIFEST_CONTENT_MISMATCH")


if __name__ == "__main__":
    unittest.main()

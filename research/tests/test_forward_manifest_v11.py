from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from pathlib import Path

RESEARCH = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RESEARCH))

import exp_freeze_001r4 as v11
import forward_infrastructure_001r3 as fw


class V11ManifestTests(unittest.TestCase):
    def test_01_historical_v11_rejects_changed_runtime_bytes(self):
        with self.assertRaises(fw.ForwardIntegrityError) as caught:
            v11.verify()
        self.assertEqual(str(caught.exception), "V11_BOUND_FILE_HASH_MISMATCH")

    def test_02_write_once_reuses_identical_document(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "FORWARD_INFRASTRUCTURE_MANIFEST_V11.json"
            document = v11.build_document()
            self.assertEqual(v11.write_once(output, document), "V11_GENERATED")
            self.assertEqual(v11.write_once(output, copy.deepcopy(document)), "V11_READ_ONLY_REUSE")

    def test_03_write_once_rejects_content_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "FORWARD_INFRASTRUCTURE_MANIFEST_V11.json"
            document = v11.build_document()
            v11.write_once(output, document)
            changed = copy.deepcopy(document)
            changed["hashes"][next(iter(changed["hashes"]))] = "0" * 64
            with self.assertRaises(fw.ForwardIntegrityError) as caught:
                v11.write_once(output, changed)
            self.assertEqual(str(caught.exception), "V11_MANIFEST_CONTENT_MISMATCH")


if __name__ == "__main__":
    unittest.main()

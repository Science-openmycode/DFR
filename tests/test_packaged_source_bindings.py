from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PackagedSourceBindingsTest(unittest.TestCase):
    def test_all_legacy_source_manifests_match(self) -> None:
        manifests = sorted(ROOT.rglob("SOURCE_MANIFEST.json"))
        # The DFR package contains its source directly and intentionally does
        # not ship a legacy algorithm source manifest.
        if not manifests:
            return
        for manifest in manifests:
            entries = json.loads(manifest.read_text(encoding="utf-8-sig"))
            self.assertEqual(len(entries), 38)
            for entry in entries:
                with self.subTest(manifest=manifest, source=entry["file"]):
                    path = manifest.parent / entry["file"]
                    self.assertTrue(path.is_file())
                    data = path.read_bytes()
                    self.assertEqual(hashlib.sha256(data).hexdigest(), entry["sha256"])


if __name__ == "__main__":
    unittest.main()

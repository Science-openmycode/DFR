"""Repair legacy JSON manifests with unescaped Windows path separators.

The evaluator already wrote the numeric results; this utility only makes the
JSON representation standards-compliant. It never changes values or reruns an
experiment. A backup is written next to every repaired file before replacing
it, and a SHA-256 audit is recorded in ``repair_manifest.json``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


_INVALID_ESCAPE = re.compile(r"\\(?![\"\\/bfnrt]|u[0-9a-fA-F]{4})")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def repair_text(text: str) -> str:
    """Escape only backslashes that are not valid JSON escape sequences."""
    repaired = _INVALID_ESCAPE.sub(r"\\\\", text)
    json.loads(repaired)  # fail closed: never write an unparsable result
    return repaired


def repair_file(path: Path) -> dict:
    original = path.read_text(encoding="utf-8")
    try:
        json.loads(original)
        return {"path": str(path), "status": "already_valid", "sha256": sha256(path)}
    except json.JSONDecodeError:
        pass
    repaired = repair_text(original)
    backup = path.with_suffix(path.suffix + ".before_json_repair")
    if not backup.exists():
        backup.write_text(original, encoding="utf-8", newline="")
    path.write_text(repaired, encoding="utf-8", newline="")
    return {
        "path": str(path),
        "status": "repaired",
        "backup": str(backup),
        "before_sha256": sha256(backup),
        "after_sha256": sha256(path),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--pattern", default="metrics.json")
    args = parser.parse_args()
    files = sorted(args.root.rglob(args.pattern))
    results = [repair_file(path) for path in files]
    manifest = args.root / "repair_manifest.json"
    manifest.write_text(
        json.dumps({"schema_version": 1, "files": results}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"files": len(files), "repaired": sum(r["status"] == "repaired" for r in results)}, ensure_ascii=False))


if __name__ == "__main__":
    main()

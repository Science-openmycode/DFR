"""Shared release provenance; no downstream task evaluation."""
import hashlib
import json
from pathlib import Path

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def base_release_hash(path: Path, seen: frozenset[Path] = frozenset()) -> str:
    """Bind a routed view to the release it reconstructs, not just its label."""
    path = path.resolve()
    if path in seen or len(seen) >= 32:
        raise ValueError("Cyclic or excessive release derivation chain")
    seen = seen | {path}
    digest = sha256_file(path)
    sidecar = path.with_name(path.name + ".manifest.json")
    if sidecar.is_file():
        manifest = json.loads(sidecar.read_text(encoding="utf-8-sig"))
        source_record = None
        if manifest.get("schema") == "road-route-coordinate-derivation-v1":
            if manifest.get("coordinates", {}).get("sha256") != digest:
                raise ValueError(f"Road coordinate derivation output hash mismatch: {path}")
            source_record = manifest.get("route_source", {})
        elif manifest.get("router") in {"FMM", "STMatch"}:
            if manifest.get("output", {}).get("sha256") != digest:
                raise ValueError(f"Routed view output hash mismatch: {path}")
            source_record = manifest.get("inputs", {}).get("source", {})
        if source_record is not None:
            source = source_record.get("sha256")
            if not source:
                raise ValueError(f"Routed view missing source release binding: {path}")
            raw_source = source_record.get("path")
            if raw_source:
                original = Path(raw_source)
                original = original if original.is_absolute() else path.parent / original
                if original.is_file():
                    if sha256_file(original) != source:
                        raise ValueError(f"Derivation source file hash mismatch: {original}")
                    return base_release_hash(original, seen)
            return source
    return digest

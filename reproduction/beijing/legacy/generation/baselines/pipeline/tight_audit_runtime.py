"""Load the upstream synth-audit epsilon estimator without package-name collisions."""
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
from types import ModuleType


def load_upstream_audit(synth_audit_root: str | Path) -> ModuleType:
    source = Path(synth_audit_root).resolve() / "utils" / "audit.py"
    if not source.exists():
        raise FileNotFoundError(f"upstream synth-audit utility not found: {source}")
    spec = importlib.util.spec_from_file_location("upstream_synth_audit", source)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {source}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--synth-audit-root", type=Path, required=True)
    args = parser.parse_args()
    module = load_upstream_audit(args.synth_audit_root)
    if not callable(getattr(module, "estimate_eps", None)):
        raise RuntimeError("upstream audit module did not expose estimate_eps")
    print(f"[tight-audit] upstream estimator ready: {module.__file__}")


if __name__ == "__main__":
    main()

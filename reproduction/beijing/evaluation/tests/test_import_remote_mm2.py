from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

ISOLATED_ROOT = Path(__file__).resolve().parents[2]
if str(ISOLATED_ROOT) not in sys.path:
    sys.path.insert(0, str(ISOLATED_ROOT))

from tools import import_remote_mm2


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_validate_remote_measurement_binding_rejects_hash_mismatch(tmp_path: Path) -> None:
    measurement = tmp_path / "measurement.pkl"
    measurement.write_bytes(b"local-measurement")
    remote_info = {
        "M": "SPRT",
        "records": 3,
        "measurement_sha256": "not-the-local-hash",
        "export_sha256": "remote-export",
    }

    with pytest.raises(ValueError, match="measurement hash mismatch"):
        import_remote_mm2.validate_remote_measurement_binding(
            remote_info,
            measurement,
            expected_records=3,
        )


def test_validate_remote_measurement_binding_checks_count_and_hash(tmp_path: Path) -> None:
    measurement = tmp_path / "measurement.pkl"
    measurement.write_bytes(b"local-measurement")
    remote_info = {
        "M": "SPRT",
        "records": 3,
        "measurement_sha256": _sha256(measurement),
        "export_sha256": "remote-export",
    }

    result = import_remote_mm2.validate_remote_measurement_binding(
        remote_info,
        measurement,
        expected_records=3,
    )

    assert result["measurement_sha256"] == _sha256(measurement)
    assert result["records"] == 3


def test_import_root_is_configurable_and_does_not_overwrite_existing(tmp_path: Path) -> None:
    batch = tmp_path / "batch"
    configured = tmp_path / "staging"
    result = import_remote_mm2.cell_output_dir(
        batch,
        "SPRT",
        out_root=configured,
    )
    assert result == configured / "SPRT" / "MM2-MDP"

    result.mkdir(parents=True)
    with pytest.raises(FileExistsError):
        import_remote_mm2.ensure_empty_cell(result)


def test_validate_downloaded_csv_hash(tmp_path: Path) -> None:
    csv_path = tmp_path / "matches.csv"
    csv_path.write_text("id,aborted\n0,no\n", encoding="utf-8")
    assert import_remote_mm2.validate_downloaded_csv(csv_path, _sha256(csv_path))
    with pytest.raises(ValueError, match="downloaded MM2 CSV hash mismatch"):
        import_remote_mm2.validate_downloaded_csv(csv_path, "0" * 64)


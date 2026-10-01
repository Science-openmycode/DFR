"""Read-only inspector for the Portal-Fiber differential-privacy ledger."""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", required=True, type=Path)
    args = parser.parse_args()
    if not args.ledger.is_file():
        raise FileNotFoundError(args.ledger)

    connection = sqlite3.connect(f"file:{args.ledger}?mode=ro", uri=True)
    try:
        table_names = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
        ]
        print(f"ledger={args.ledger}")
        for table_name in table_names:
            columns = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
            rows = connection.execute(f"SELECT * FROM {table_name}").fetchall()
            print(f"\n[{table_name}] rows={len(rows)}")
            print("columns=" + ", ".join(column[1] for column in columns))
            for row in rows[-10:]:
                print(row)
    finally:
        connection.close()


if __name__ == "__main__":
    main()

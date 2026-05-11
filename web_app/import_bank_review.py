from __future__ import annotations

from datetime import datetime
from pathlib import Path
import argparse
import csv
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "review_app.sqlite3"


def main() -> int:
    parser = argparse.ArgumentParser(description="Import bank-centric review CSV into the review app.")
    parser.add_argument("--bank-review", required=True)
    parser.add_argument("--batch", default="")
    parser.add_argument("--replace-batch", action="store_true")
    args = parser.parse_args()

    rows = read_csv(args.bank_review)
    batch = args.batch or Path(args.bank_review).parent.name
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        create_table(conn)
        if args.replace_batch:
            conn.execute("DELETE FROM bank_review_rows WHERE source_batch = ?", (batch,))
        now = datetime.utcnow().isoformat()
        for row in rows:
            state = "approved" if row.get("row_type") == "bank_matched" and int(row.get("confidence") or 0) >= 80 else "review"
            conn.execute(
                """
                INSERT INTO bank_review_rows (
                    row_type, bank_row_id, bank_date, bank_amount, bank_description, inferred_card_last4,
                    order_id, amazon_date, amazon_amount, split_group_total, split_charge_count,
                    match_status, confidence, reason, review_state, note, source_batch, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', ?, ?)
                """,
                (
                    row.get("row_type", ""),
                    row.get("bank_row_id", ""),
                    row.get("bank_date", ""),
                    row.get("bank_amount", ""),
                    row.get("bank_description", ""),
                    row.get("inferred_card_last4", ""),
                    row.get("order_id", ""),
                    row.get("amazon_date", ""),
                    row.get("amazon_amount", ""),
                    row.get("split_group_total", ""),
                    row.get("split_charge_count", ""),
                    row.get("match_status", ""),
                    int(row.get("confidence") or 0),
                    row.get("reason", ""),
                    state,
                    batch,
                    now,
                ),
            )
    print(f"Imported {len(rows)} bank review rows into batch {batch}.")
    print(DB_PATH.resolve())
    return 0


def read_csv(path_value: str) -> list[dict[str, str]]:
    with Path(path_value).open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def create_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS bank_review_rows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            row_type TEXT NOT NULL,
            bank_row_id TEXT,
            bank_date TEXT,
            bank_amount TEXT,
            bank_description TEXT,
            inferred_card_last4 TEXT,
            order_id TEXT,
            amazon_date TEXT,
            amazon_amount TEXT,
            split_group_total TEXT,
            split_charge_count TEXT,
            match_status TEXT,
            confidence INTEGER,
            reason TEXT,
            review_state TEXT NOT NULL DEFAULT 'review',
            note TEXT NOT NULL DEFAULT '',
            source_batch TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL
        )
        """
    )


if __name__ == "__main__":
    sys.exit(main())

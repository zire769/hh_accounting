from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
import argparse
import csv
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "review_app.sqlite3"


def main() -> int:
    parser = argparse.ArgumentParser(description="Import match CSV rows into the private review web app database.")
    parser.add_argument("--matches", required=True)
    parser.add_argument("--orders", required=True)
    parser.add_argument("--batch", default="")
    parser.add_argument("--replace-batch", action="store_true")
    args = parser.parse_args()

    batch = args.batch or Path(args.matches).parent.name
    matches = read_csv(args.matches)
    orders = {row["order_id"]: row for row in read_csv(args.orders)}

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        create_table(conn)
        if args.replace_batch:
            conn.execute("DELETE FROM review_rows WHERE source_batch = ?", (batch,))
        insert_rows(conn, matches, orders, batch)
    print(f"Imported {len(matches)} rows into batch {batch}.")
    print(DB_PATH.resolve())
    return 0


def read_csv(path_value: str) -> list[dict[str, str]]:
    with Path(path_value).open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def create_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS review_rows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT NOT NULL,
            amazon_date TEXT,
            amazon_status TEXT,
            card_last4 TEXT,
            amazon_amount REAL NOT NULL,
            merchant TEXT,
            bank_row_id TEXT,
            bank_date TEXT,
            bank_amount REAL,
            bank_description TEXT,
            match_status TEXT,
            confidence INTEGER,
            reason TEXT,
            split_status TEXT,
            split_group_total REAL,
            split_charge_count INTEGER,
            split_charge_index INTEGER,
            review_state TEXT NOT NULL DEFAULT 'review',
            note TEXT NOT NULL DEFAULT '',
            source_batch TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL
        )
        """
    )


def insert_rows(conn: sqlite3.Connection, matches: list[dict[str, str]], orders: dict[str, dict[str, str]], batch: str) -> None:
    order_counts = Counter(row.get("order_id", "") for row in matches)
    per_order_index: defaultdict[str, int] = defaultdict(int)
    now = datetime.utcnow().isoformat()
    for row in matches:
        order_id = row.get("order_id", "")
        order = orders.get(order_id, {})
        per_order_index[order_id] += 1
        split_count = int_or_default(order.get("amazon_transaction_count"), order_counts[order_id])
        review_state = "approved" if row.get("match_status") == "Matched" and int_or_default(row.get("confidence"), 0) >= 80 else "review"
        conn.execute(
            """
            INSERT INTO review_rows (
                order_id, amazon_date, amazon_status, card_last4, amazon_amount, merchant,
                bank_row_id, bank_date, bank_amount, bank_description, match_status, confidence,
                reason, split_status, split_group_total, split_charge_count, split_charge_index,
                review_state, note, source_batch, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', ?, ?)
            """,
            (
                order_id,
                row.get("amazon_date", ""),
                row.get("amazon_status", ""),
                row.get("card_last4", ""),
                money(row.get("amazon_amount")),
                row.get("merchant", ""),
                row.get("bank_row_id", ""),
                row.get("bank_date", ""),
                money(row.get("bank_amount")),
                row.get("bank_description", ""),
                row.get("match_status", ""),
                int_or_default(row.get("confidence"), 0),
                row.get("reason", ""),
                order.get("split_status", "split Amazon charge" if split_count > 1 else "single Amazon charge"),
                money(order.get("amazon_group_total")),
                split_count,
                per_order_index[order_id],
                review_state,
                batch,
                now,
            ),
        )


def int_or_default(value: str | None, default: int) -> int:
    try:
        return int(value or "")
    except ValueError:
        return default


def money(value: str | None) -> float | None:
    if not value:
        return None
    return float(value)


if __name__ == "__main__":
    sys.exit(main())

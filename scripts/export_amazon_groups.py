from __future__ import annotations

from pathlib import Path
import argparse
import csv
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from amazon_recon.amazon_parser import group_transactions, load_amazon_transactions
from amazon_recon.cli import filter_by_date


def main() -> int:
    parser = argparse.ArgumentParser(description="Export grouped Amazon transaction CSV without bank matching.")
    parser.add_argument("--amazon", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    args = parser.parse_args()

    txs = filter_by_date(load_amazon_transactions(args.amazon), args.start_date, args.end_date)
    groups = group_transactions(txs)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    with out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "order_id",
                "card_last4",
                "transaction_count",
                "group_total",
                "group_status",
                "split_status",
                "transaction_dates",
                "transaction_amounts",
                "merchants",
                "order_urls",
            ],
        )
        writer.writeheader()
        for group in groups:
            writer.writerow(
                {
                    "order_id": group.order_id,
                    "card_last4": group.card_last4,
                    "transaction_count": group.transaction_count,
                    "group_total": f"{group.total:.2f}",
                    "group_status": group.status,
                    "split_status": group.split_status,
                    "transaction_dates": "; ".join(str(tx.transaction_date or "") for tx in group.transactions),
                    "transaction_amounts": "; ".join(f"{tx.amount_abs:.2f}" for tx in group.transactions),
                    "merchants": "; ".join(sorted({tx.merchant for tx in group.transactions if tx.merchant})),
                    "order_urls": "; ".join(sorted({tx.order_url for tx in group.transactions if tx.order_url})),
                }
            )

    print(f"Exported {len(txs)} transactions grouped into {len(groups)} orders.")
    print(out.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

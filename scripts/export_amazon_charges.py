from __future__ import annotations

from pathlib import Path
import argparse
import csv
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from amazon_recon.amazon_parser import group_transactions, load_amazon_transactions
from amazon_recon.cli import filter_by_date


def main() -> int:
    parser = argparse.ArgumentParser(description="Export charge-level Amazon transactions for QBO prep.")
    parser.add_argument("--amazon", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--default-category", default="")
    args = parser.parse_args()

    txs = filter_by_date(load_amazon_transactions(args.amazon), args.start_date, args.end_date)
    groups = {(group.order_id, group.card_last4): group for group in group_transactions(txs)}

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    with out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "date",
                "vendor",
                "amount",
                "payment_account_hint",
                "card_last4",
                "order_id",
                "split_group_total",
                "split_charge_count",
                "split_charge_index",
                "category",
                "description",
                "memo",
                "amazon_status",
                "order_url",
            ],
        )
        writer.writeheader()
        for tx in sorted(txs, key=lambda item: (item.transaction_date or "", item.order_id, item.amount_abs)):
            group = groups[(tx.order_id, tx.card_last4)]
            sorted_group_txs = sorted(group.transactions, key=lambda item: (item.transaction_date or "", item.amount_abs, item.raw_text))
            split_index = sorted_group_txs.index(tx) + 1
            is_split = group.transaction_count > 1
            memo_parts = [f"Amazon order {tx.order_id}"]
            if is_split:
                memo_parts.append(f"split charge {split_index} of {group.transaction_count}; group total ${group.total:.2f}")
            if tx.status:
                memo_parts.append(f"Amazon status: {tx.status}")

            writer.writerow(
                {
                    "date": tx.transaction_date or "",
                    "vendor": "Amazon",
                    "amount": f"{tx.amount_abs:.2f}",
                    "payment_account_hint": f"Card ending {tx.card_last4}" if tx.card_last4 else "",
                    "card_last4": tx.card_last4,
                    "order_id": tx.order_id,
                    "split_group_total": f"{group.total:.2f}",
                    "split_charge_count": group.transaction_count,
                    "split_charge_index": split_index,
                    "category": args.default_category,
                    "description": tx.merchant or "Amazon purchase",
                    "memo": "; ".join(memo_parts),
                    "amazon_status": tx.status,
                    "order_url": tx.order_url,
                }
            )

    print(f"Exported {len(txs)} charge-level Amazon transaction rows.")
    print(out.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

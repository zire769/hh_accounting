from __future__ import annotations

from pathlib import Path
import argparse
import csv
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from amazon_recon.amazon_parser import group_transactions, load_amazon_transactions
from amazon_recon.cli import filter_by_date
from amazon_recon.matcher import match_orders
from amazon_recon.qbo_parser import load_bank_csv


def main() -> int:
    parser = argparse.ArgumentParser(description="Export a bank-centric review CSV with inferred Amazon card/order matches.")
    parser.add_argument("--amazon", required=True)
    parser.add_argument("--bank", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--date-tolerance", type=int, default=5)
    args = parser.parse_args()

    amazon_transactions = filter_by_date(load_amazon_transactions(args.amazon), args.start_date, args.end_date)
    bank_transactions = load_bank_csv(args.bank)
    matches = match_orders(group_transactions(amazon_transactions), bank_transactions, date_tolerance_days=args.date_tolerance)

    bank_match_by_row_id = {}
    amazon_unmatched = []
    for order_match in matches:
        for charge_match in order_match.charge_matches:
            if charge_match.bank_tx:
                bank_match_by_row_id[charge_match.bank_tx.row_id] = (order_match.group, charge_match)
            elif "pending" not in charge_match.status.lower():
                amazon_unmatched.append((order_match.group, charge_match))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "row_type",
                "bank_row_id",
                "bank_date",
                "bank_amount",
                "bank_description",
                "inferred_card_last4",
                "order_id",
                "amazon_date",
                "amazon_amount",
                "split_group_total",
                "split_charge_count",
                "match_status",
                "confidence",
                "reason",
            ],
        )
        writer.writeheader()
        for bank_tx in bank_transactions:
            matched = bank_match_by_row_id.get(bank_tx.row_id)
            if matched:
                group, charge_match = matched
                amazon_tx = charge_match.amazon_tx
                writer.writerow(
                    {
                        "row_type": "bank_matched",
                        "bank_row_id": bank_tx.row_id,
                        "bank_date": bank_tx.transaction_date or "",
                        "bank_amount": f"{bank_tx.amount_abs:.2f}",
                        "bank_description": bank_tx.description,
                        "inferred_card_last4": amazon_tx.card_last4,
                        "order_id": amazon_tx.order_id,
                        "amazon_date": amazon_tx.transaction_date or "",
                        "amazon_amount": f"{amazon_tx.amount_abs:.2f}",
                        "split_group_total": f"{group.total:.2f}",
                        "split_charge_count": group.transaction_count,
                        "match_status": "Matched",
                        "confidence": charge_match.confidence,
                        "reason": charge_match.reason,
                    }
                )
            else:
                writer.writerow(
                    {
                        "row_type": "bank_unmatched",
                        "bank_row_id": bank_tx.row_id,
                        "bank_date": bank_tx.transaction_date or "",
                        "bank_amount": f"{bank_tx.amount_abs:.2f}",
                        "bank_description": bank_tx.description,
                        "inferred_card_last4": "unknown",
                        "order_id": "",
                        "amazon_date": "",
                        "amazon_amount": "",
                        "split_group_total": "",
                        "split_charge_count": "",
                        "match_status": "Unmatched bank transaction",
                        "confidence": 0,
                        "reason": "No Amazon transaction matched this Chase row by amount/date.",
                    }
                )

        for group, charge_match in amazon_unmatched:
            amazon_tx = charge_match.amazon_tx
            writer.writerow(
                {
                    "row_type": "amazon_unmatched",
                    "bank_row_id": "",
                    "bank_date": "",
                    "bank_amount": "",
                    "bank_description": "",
                    "inferred_card_last4": amazon_tx.card_last4,
                    "order_id": amazon_tx.order_id,
                    "amazon_date": amazon_tx.transaction_date or "",
                    "amazon_amount": f"{amazon_tx.amount_abs:.2f}",
                    "split_group_total": f"{group.total:.2f}",
                    "split_charge_count": group.transaction_count,
                    "match_status": "Amazon charge not found in Chase",
                    "confidence": 0,
                    "reason": charge_match.reason,
                }
            )

    print(f"Exported {len(bank_transactions)} Chase rows and {len(amazon_unmatched)} Amazon-only review rows.")
    print(out.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

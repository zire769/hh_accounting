from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .amazon_parser import group_transactions, load_amazon_transactions
from .date_utils import parse_date
from .matcher import match_orders
from .qbo_parser import load_bank_csv
from .report import write_reports


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="amazon-recon",
        description="Group Amazon payment transactions and match them to QuickBooks/bank CSV rows.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    parse_cmd = subparsers.add_parser("parse-amazon", help="Parse an Amazon transaction page or CSV.")
    parse_cmd.add_argument("--amazon", required=True, help="Path to saved Amazon transaction HTML, copied text, or CSV.")
    parse_cmd.add_argument("--start-date", help="Optional inclusive start date, for example 2026-03-01.")
    parse_cmd.add_argument("--end-date", help="Optional inclusive end date, for example 2026-04-30.")
    parse_cmd.add_argument("--card-last4", help="Optional Amazon card last 4 filter, for example 3255.")

    reconcile_cmd = subparsers.add_parser("reconcile", help="Match Amazon transactions to a bank/QBO CSV.")
    reconcile_cmd.add_argument("--amazon", required=True, help="Path to saved Amazon transaction HTML, copied text, or CSV.")
    reconcile_cmd.add_argument("--bank", required=True, help="Path to QuickBooks/bank CSV export.")
    reconcile_cmd.add_argument("--out", default="output", help="Output directory for CSV and HTML reports.")
    reconcile_cmd.add_argument("--date-tolerance", type=int, default=5, help="Max days between Amazon and bank dates.")
    reconcile_cmd.add_argument("--start-date", help="Optional inclusive Amazon transaction start date.")
    reconcile_cmd.add_argument("--end-date", help="Optional inclusive Amazon transaction end date.")
    reconcile_cmd.add_argument("--card-last4", help="Optional Amazon card last 4 filter for this bank/card file.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "parse-amazon":
        txs = filter_by_card(
            filter_by_date(load_amazon_transactions(args.amazon), args.start_date, args.end_date),
            args.card_last4,
        )
        groups = group_transactions(txs)
        print(f"Parsed {len(txs)} Amazon transaction(s).")
        print(f"Grouped into {len(groups)} order group(s).")
        for group in groups:
            print(
                f"{group.order_id} card ****{group.card_last4} "
                f"{group.transaction_count} charge(s) total ${group.total:.2f} {group.split_status}"
            )
        return 0

    if args.command == "reconcile":
        amazon_path = Path(args.amazon)
        bank_path = Path(args.bank)
        if not amazon_path.exists():
            print(f"Amazon input not found: {amazon_path}", file=sys.stderr)
            return 2
        if not bank_path.exists():
            print(f"Bank CSV not found: {bank_path}", file=sys.stderr)
            return 2

        amazon_transactions = filter_by_card(
            filter_by_date(load_amazon_transactions(amazon_path), args.start_date, args.end_date),
            args.card_last4,
        )
        groups = group_transactions(amazon_transactions)
        bank_transactions = load_bank_csv(bank_path)
        matches = match_orders(groups, bank_transactions, date_tolerance_days=args.date_tolerance)
        write_reports(matches, args.out)
        print(f"Parsed {len(amazon_transactions)} Amazon transaction(s).")
        print(f"Grouped into {len(groups)} Amazon order group(s).")
        print(f"Loaded {len(bank_transactions)} bank/QBO transaction(s).")
        print(f"Wrote reports to {Path(args.out).resolve()}")
        return 0

    return 1


def filter_by_date(transactions, start_value: str | None, end_value: str | None):
    start = parse_date(start_value)
    end = parse_date(end_value)
    if not start and not end:
        return transactions

    filtered = []
    for tx in transactions:
        if tx.transaction_date is None:
            continue
        if start and tx.transaction_date < start:
            continue
        if end and tx.transaction_date > end:
            continue
        filtered.append(tx)
    return filtered


def filter_by_card(transactions, card_last4: str | None):
    if not card_last4:
        return transactions
    normalized = card_last4.strip()
    return [tx for tx in transactions if tx.card_last4 == normalized]


if __name__ == "__main__":
    raise SystemExit(main())

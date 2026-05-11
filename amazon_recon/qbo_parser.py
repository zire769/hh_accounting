from __future__ import annotations

from pathlib import Path
import csv
import re

from .date_utils import parse_date
from .models import BankTransaction


DATE_KEYS = ("date", "transaction date", "posted date", "post date")
DESC_KEYS = ("description", "memo", "name", "payee", "transaction", "bank detail")
ACCOUNT_KEYS = ("account", "bank account", "card", "credit card")
AMOUNT_KEYS = ("amount", "spent", "charge", "payment", "debit")


def load_bank_csv(path: str | Path) -> list[BankTransaction]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)

    bank_rows: list[BankTransaction] = []
    for index, row in enumerate(rows, start=1):
        normalized = {normalize_header(key): value for key, value in row.items() if key}
        amount = find_amount(normalized)
        if amount is None:
            continue
        bank_rows.append(
            BankTransaction(
                row_id=str(index),
                transaction_date=parse_date(first_value(normalized, DATE_KEYS)),
                amount=amount,
                description=first_value(normalized, DESC_KEYS),
                account=first_value(normalized, ACCOUNT_KEYS),
                raw=row,
            )
        )
    return bank_rows


def normalize_header(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def first_value(row: dict[str, str], keys: tuple[str, ...]) -> str:
    for key in keys:
        if row.get(key):
            return row[key]
    return ""


def find_amount(row: dict[str, str]) -> float | None:
    for key in AMOUNT_KEYS:
        value = row.get(key)
        parsed = parse_money(value)
        if parsed is not None:
            return parsed

    # Common QBO exports use separate money-in/money-out columns.
    money_out = parse_money(row.get("money out") or row.get("spent"))
    money_in = parse_money(row.get("money in") or row.get("received"))
    if money_out is not None:
        return -abs(money_out)
    if money_in is not None:
        return abs(money_in)
    return None


def parse_money(value: str | None) -> float | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    negative = cleaned.startswith("(") and cleaned.endswith(")")
    cleaned = cleaned.replace("$", "").replace(",", "").replace("(", "").replace(")", "")
    try:
        amount = float(cleaned)
    except ValueError:
        return None
    return -abs(amount) if negative else amount

from __future__ import annotations

from collections import defaultdict
from html.parser import HTMLParser
from pathlib import Path
import csv
import re

from .date_utils import parse_date
from .models import AmazonOrderGroup, AmazonTransaction


AMOUNT_RE = re.compile(r"-?\$[\d,]+(?:\.\d{2})")
CARD_RE = re.compile(r"\b(?:Visa|Mastercard|MasterCard|Amex|American Express|Discover)\s+\*+(\d{4})\b", re.I)
DATE_RE = re.compile(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},\s+\d{4}\b", re.I)
ORDER_RE = re.compile(r"\bOrder\s*#?\s*(\d{3}-\d{7}-\d{7})\b", re.I)


class TextAndLinksParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.current_href = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"br", "p", "div", "li", "tr", "section", "article"}:
            self.parts.append("\n")
        if tag == "a":
            attrs_dict = dict(attrs)
            self.current_href = attrs_dict.get("href") or ""

    def handle_endtag(self, tag: str) -> None:
        if tag in {"p", "div", "li", "tr", "section", "article"}:
            self.parts.append("\n")
        if tag == "a":
            self.current_href = ""

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if not text:
            return
        if self.current_href and ORDER_RE.search(text):
            self.parts.append(f"{text} [href={self.current_href}]\n")
        else:
            self.parts.append(text + "\n")

    def text(self) -> str:
        return "".join(self.parts)


def html_to_text(html: str) -> str:
    parser = TextAndLinksParser()
    parser.feed(html)
    return parser.text()


def load_amazon_transactions(path: str | Path) -> list[AmazonTransaction]:
    path = Path(path)
    content = path.read_text(encoding="utf-8", errors="ignore")
    if path.suffix.lower() in {".csv", ".tsv"}:
        return load_amazon_csv(path)
    if "<html" in content.lower() or "<body" in content.lower() or "<div" in content.lower():
        content = html_to_text(content)
    return parse_transactions_text(content)


def load_amazon_csv(path: str | Path) -> list[AmazonTransaction]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)

    transactions: list[AmazonTransaction] = []
    for index, row in enumerate(rows, start=1):
        lowered = {key.lower().strip(): value for key, value in row.items() if key}
        date_value = first_value(lowered, ("date", "transaction_date", "transaction date"))
        status = first_value(lowered, ("status", "state")) or "completed"
        card = first_value(lowered, ("card_last4", "card last4", "card", "payment method"))
        order_id = first_value(lowered, ("order_id", "order id", "order", "order number"))
        amount = parse_amount(first_value(lowered, ("amount", "charge", "total")))
        merchant = first_value(lowered, ("merchant", "description")) or ""
        if not order_id or amount is None:
            continue
        card_last4 = extract_card_last4(card or "") or ""
        transactions.append(
            AmazonTransaction(
                transaction_date=parse_date(date_value),
                status=status.strip(),
                card_last4=card_last4,
                amount=amount,
                order_id=normalize_order_id(order_id),
                merchant=merchant,
                raw_text=f"csv row {index}",
            )
        )
    return transactions


def parse_transactions_text(text: str) -> list[AmazonTransaction]:
    lines = normalize_lines(text)
    transactions: list[AmazonTransaction] = []
    current_date = None
    current_status = ""

    for index, line in enumerate(lines):
        date_match = DATE_RE.search(line)
        if date_match:
            current_date = parse_date(date_match.group(0))
            continue

        lowered = line.lower()
        if lowered in {"completed", "in progress"}:
            current_status = line
            continue

        order_match = ORDER_RE.search(line)
        if not order_match:
            continue

        window = lines[max(0, index - 6) : min(len(lines), index + 6)]
        amount = find_nearest_amount(window)
        card_last4 = find_nearest_card(window)
        merchant = find_merchant(window)
        order_url = find_order_href(line)
        status = find_transaction_status(lines, index, current_status)

        if amount is None:
            continue

        transactions.append(
            AmazonTransaction(
                transaction_date=current_date,
                status=status,
                card_last4=card_last4,
                amount=amount,
                order_id=order_match.group(1),
                merchant=merchant,
                order_url=order_url,
                raw_text="\n".join(window),
            )
        )

    return dedupe_transactions(transactions)


def group_transactions(transactions: list[AmazonTransaction]) -> list[AmazonOrderGroup]:
    groups: dict[tuple[str, str], list[AmazonTransaction]] = defaultdict(list)
    for tx in transactions:
        groups[(tx.order_id, tx.card_last4)].append(tx)
    return [
        AmazonOrderGroup(order_id=order_id, card_last4=card_last4, transactions=tuple(items))
        for (order_id, card_last4), items in sorted(groups.items())
    ]


def normalize_lines(text: str) -> list[str]:
    text = re.sub(r"\r\n?", "\n", text)
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.split("\n")]
    return [line for line in lines if line]


def parse_amount(value: str | None) -> float | None:
    if not value:
        return None
    match = AMOUNT_RE.search(value.replace(",", ""))
    if not match:
        return None
    return float(match.group(0).replace("$", "").replace(",", ""))


def find_nearest_amount(lines: list[str]) -> float | None:
    amounts: list[float] = []
    for line in lines:
        for amount in AMOUNT_RE.findall(line.replace(",", "")):
            amounts.append(float(amount.replace("$", "")))
    if not amounts:
        return None
    return amounts[-1]


def find_nearest_card(lines: list[str]) -> str:
    for line in lines:
        card = extract_card_last4(line)
        if card:
            return card
    return ""


def extract_card_last4(value: str) -> str:
    match = CARD_RE.search(value)
    if match:
        return match.group(1)
    fallback = re.search(r"\*+(\d{4})", value)
    return fallback.group(1) if fallback else ""


def find_merchant(lines: list[str]) -> str:
    for line in lines:
        if "amzn" in line.lower() or "amazon" in line.lower():
            return line
    return ""


def find_order_href(line: str) -> str:
    match = re.search(r"\[href=([^\]]+)\]", line)
    return match.group(1) if match else ""


def find_transaction_status(lines: list[str], order_line_index: int, section_status: str) -> str:
    nearby = lines[max(0, order_line_index - 3) : min(len(lines), order_line_index + 3)]
    if any(line.lower() == "pending" for line in nearby):
        return "Pending"
    return section_status or "Completed"


def normalize_order_id(value: str) -> str:
    match = ORDER_RE.search(value)
    return match.group(1) if match else value.strip().replace("Order #", "")


def first_value(row: dict[str, str], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = row.get(key)
        if value:
            return value
    return ""


def dedupe_transactions(transactions: list[AmazonTransaction]) -> list[AmazonTransaction]:
    seen: set[tuple[str, str, float, str, object]] = set()
    unique: list[AmazonTransaction] = []
    for tx in transactions:
        key = (tx.order_id, tx.card_last4, tx.amount_abs, tx.status.lower(), tx.transaction_date)
        if key in seen:
            continue
        seen.add(key)
        unique.append(tx)
    return unique

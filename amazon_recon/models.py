from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class AmazonTransaction:
    transaction_date: date | None
    status: str
    card_last4: str
    amount: float
    order_id: str
    merchant: str = ""
    order_url: str = ""
    raw_text: str = ""

    @property
    def amount_abs(self) -> float:
        return round(abs(self.amount), 2)


@dataclass(frozen=True)
class AmazonOrderGroup:
    order_id: str
    card_last4: str
    transactions: tuple[AmazonTransaction, ...]

    @property
    def total(self) -> float:
        return round(sum(tx.amount_abs for tx in self.transactions), 2)

    @property
    def status(self) -> str:
        statuses = {tx.status.lower() for tx in self.transactions}
        if any("pending" in status or "in progress" in status for status in statuses):
            return "pending"
        return "completed"

    @property
    def transaction_count(self) -> int:
        return len(self.transactions)

    @property
    def split_status(self) -> str:
        return "split Amazon charge" if self.transaction_count > 1 else "single Amazon charge"


@dataclass(frozen=True)
class BankTransaction:
    row_id: str
    transaction_date: date | None
    amount: float
    description: str
    account: str = ""
    raw: dict[str, str] = field(default_factory=dict)

    @property
    def amount_abs(self) -> float:
        return round(abs(self.amount), 2)


@dataclass(frozen=True)
class ChargeMatch:
    amazon_tx: AmazonTransaction
    bank_tx: BankTransaction | None
    confidence: int
    status: str
    reason: str


@dataclass(frozen=True)
class OrderMatch:
    group: AmazonOrderGroup
    charge_matches: tuple[ChargeMatch, ...]

    @property
    def status(self) -> str:
        if self.group.status == "pending":
            return "Pending in Amazon"
        if all(match.bank_tx for match in self.charge_matches):
            return "Split matched" if self.group.transaction_count > 1 else "Exact matched"
        if any(match.bank_tx for match in self.charge_matches):
            return "Partially matched"
        return "Needs review"

    @property
    def confidence(self) -> int:
        if not self.charge_matches:
            return 0
        return round(sum(match.confidence for match in self.charge_matches) / len(self.charge_matches))

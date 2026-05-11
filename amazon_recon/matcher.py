from __future__ import annotations

from .date_utils import date_distance_days
from .models import AmazonOrderGroup, BankTransaction, ChargeMatch, OrderMatch


def match_orders(
    groups: list[AmazonOrderGroup],
    bank_transactions: list[BankTransaction],
    date_tolerance_days: int = 5,
) -> list[OrderMatch]:
    used_bank_ids: set[str] = set()
    results: list[OrderMatch] = []

    for group in groups:
        charge_matches: list[ChargeMatch] = []
        for amazon_tx in group.transactions:
            amazon_status = amazon_tx.status.lower()
            if "pending" in amazon_status or "in progress" in amazon_status:
                charge_matches.append(
                    ChargeMatch(
                        amazon_tx=amazon_tx,
                        bank_tx=None,
                        confidence=100,
                        status="Pending in Amazon",
                        reason="Amazon still marks this transaction as pending; wait for card posting.",
                    )
                )
                continue

            candidates = [
                bank_tx
                for bank_tx in bank_transactions
                if bank_tx.row_id not in used_bank_ids
                and amounts_equal(amazon_tx.amount_abs, bank_tx.amount_abs)
            ]
            ranked = sorted(
                (score_candidate(amazon_tx_date=amazon_tx.transaction_date, bank_tx=bank_tx, card_last4=amazon_tx.card_last4, tolerance=date_tolerance_days) for bank_tx in candidates),
                key=lambda item: item[0],
                reverse=True,
            )

            if ranked and ranked[0][0] >= 70:
                confidence, bank_tx, reason = ranked[0]
                used_bank_ids.add(bank_tx.row_id)
                charge_matches.append(
                    ChargeMatch(
                        amazon_tx=amazon_tx,
                        bank_tx=bank_tx,
                        confidence=confidence,
                        status="Matched",
                        reason=reason,
                    )
                )
            else:
                charge_matches.append(
                    ChargeMatch(
                        amazon_tx=amazon_tx,
                        bank_tx=None,
                        confidence=0,
                        status="Needs review",
                        reason="No unused bank transaction matched this Amazon charge by amount/date/card.",
                    )
                )

        results.append(OrderMatch(group=group, charge_matches=tuple(charge_matches)))

    return results


def amounts_equal(left: float, right: float) -> bool:
    return round(abs(left) - abs(right), 2) == 0


def score_candidate(
    amazon_tx_date,
    bank_tx: BankTransaction,
    card_last4: str,
    tolerance: int,
) -> tuple[int, BankTransaction, str]:
    score = 70
    reasons = ["amount matches exactly"]

    distance = date_distance_days(amazon_tx_date, bank_tx.transaction_date)
    if distance is not None and distance <= tolerance:
        score += max(0, 15 - (distance * 2))
        reasons.append(f"date is within {distance} day(s)")
    elif distance is not None:
        score -= 30
        reasons.append(f"date is {distance} day(s) away")
    else:
        score -= 5
        reasons.append("date could not be compared")

    description = f"{bank_tx.description} {bank_tx.account}".lower()
    if "amazon" in description or "amzn" in description:
        score += 10
        reasons.append("bank description looks like Amazon")

    if card_last4 and card_last4 in description:
        score += 10
        reasons.append("card last 4 appears in bank row")
    elif card_last4 and bank_tx.account and card_last4 not in bank_tx.account:
        score -= 5
        reasons.append("card last 4 was not visible in bank row")

    return min(score, 100), bank_tx, "; ".join(reasons)

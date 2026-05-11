from __future__ import annotations

from pathlib import Path
import csv
import html

from .models import OrderMatch


def write_reports(matches: list[OrderMatch], out_dir: str | Path) -> None:
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    write_order_summary(matches, out_path / "amazon_order_summary.csv")
    write_charge_detail(matches, out_path / "amazon_charge_matches.csv")
    write_html_report(matches, out_path / "amazon_reconciliation_report.html")


def write_order_summary(matches: list[OrderMatch], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "order_id",
                "card_last4",
                "amazon_transaction_count",
                "amazon_group_total",
                "amazon_status",
                "split_status",
                "match_status",
                "confidence",
            ],
        )
        writer.writeheader()
        for match in matches:
            writer.writerow(
                {
                    "order_id": match.group.order_id,
                    "card_last4": match.group.card_last4,
                    "amazon_transaction_count": match.group.transaction_count,
                    "amazon_group_total": f"{match.group.total:.2f}",
                    "amazon_status": match.group.status,
                    "split_status": match.group.split_status,
                    "match_status": match.status,
                    "confidence": match.confidence,
                }
            )


def write_charge_detail(matches: list[OrderMatch], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "order_id",
                "amazon_date",
                "amazon_status",
                "card_last4",
                "amazon_amount",
                "merchant",
                "bank_row_id",
                "bank_date",
                "bank_amount",
                "bank_description",
                "match_status",
                "confidence",
                "reason",
            ],
        )
        writer.writeheader()
        for order_match in matches:
            for charge_match in order_match.charge_matches:
                bank = charge_match.bank_tx
                writer.writerow(
                    {
                        "order_id": charge_match.amazon_tx.order_id,
                        "amazon_date": charge_match.amazon_tx.transaction_date or "",
                        "amazon_status": charge_match.amazon_tx.status,
                        "card_last4": charge_match.amazon_tx.card_last4,
                        "amazon_amount": f"{charge_match.amazon_tx.amount_abs:.2f}",
                        "merchant": charge_match.amazon_tx.merchant,
                        "bank_row_id": bank.row_id if bank else "",
                        "bank_date": bank.transaction_date if bank else "",
                        "bank_amount": f"{bank.amount_abs:.2f}" if bank else "",
                        "bank_description": bank.description if bank else "",
                        "match_status": charge_match.status,
                        "confidence": charge_match.confidence,
                        "reason": charge_match.reason,
                    }
                )


def write_html_report(matches: list[OrderMatch], path: Path) -> None:
    cards = []
    for order_match in matches:
        rows = []
        for charge_match in order_match.charge_matches:
            bank = charge_match.bank_tx
            rows.append(
                "<tr>"
                f"<td>{html.escape(str(charge_match.amazon_tx.transaction_date or ''))}</td>"
                f"<td>${charge_match.amazon_tx.amount_abs:.2f}</td>"
                f"<td>{html.escape(charge_match.amazon_tx.status)}</td>"
                f"<td>{html.escape(bank.description if bank else '')}</td>"
                f"<td>{html.escape(str(bank.transaction_date if bank else ''))}</td>"
                f"<td>{html.escape(charge_match.status)}</td>"
                f"<td>{charge_match.confidence}</td>"
                f"<td>{html.escape(charge_match.reason)}</td>"
                "</tr>"
            )
        cards.append(
            "<section class='order'>"
            f"<h2>{html.escape(order_match.group.order_id)} <span>{html.escape(order_match.status)}</span></h2>"
            f"<p>Card ****{html.escape(order_match.group.card_last4)} | "
            f"{order_match.group.transaction_count} Amazon charge(s) | "
            f"Group total ${order_match.group.total:.2f} | Confidence {order_match.confidence}</p>"
            "<table><thead><tr><th>Amazon date</th><th>Amazon amount</th><th>Amazon status</th>"
            "<th>Bank description</th><th>Bank date</th><th>Status</th><th>Conf.</th><th>Reason</th>"
            "</tr></thead><tbody>"
            + "".join(rows)
            + "</tbody></table></section>"
        )

    path.write_text(
        "<!doctype html><html><head><meta charset='utf-8'><title>Amazon Reconciliation</title>"
        "<style>"
        "body{font-family:Arial,sans-serif;margin:32px;background:#f6f7f8;color:#111827}"
        "h1{font-size:28px}.order{background:white;border:1px solid #d6d9de;border-radius:8px;margin:16px 0;padding:16px}"
        "h2{font-size:18px;margin:0 0 8px}h2 span{font-size:13px;background:#eef2ff;padding:4px 8px;border-radius:999px}"
        "p{color:#4b5563}table{width:100%;border-collapse:collapse;font-size:13px}th,td{border-top:1px solid #e5e7eb;padding:8px;text-align:left;vertical-align:top}"
        "th{background:#f9fafb}"
        "</style></head><body><h1>Amazon Reconciliation Report</h1>"
        + "".join(cards)
        + "</body></html>",
        encoding="utf-8",
    )

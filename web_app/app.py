from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from functools import wraps
from pathlib import Path
import csv
import io
import os
import secrets
import sqlite3
from typing import Any

from flask import (
    Flask,
    Response,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

ROOT = Path(__file__).resolve().parents[1]
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
DB_PATH = Path(os.environ.get("REVIEW_DB_PATH", ROOT / "data" / "review_app.sqlite3"))
SEED_DB_PATH = ROOT / "data" / "review_app.sqlite3"
DEFAULT_PASSWORD = "change-me"


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = os.environ.get("REVIEW_APP_SECRET", secrets.token_hex(32))
    init_db()

    def login_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not session.get("logged_in"):
                return redirect(url_for("login", next=request.path))
            return view(*args, **kwargs)

        return wrapped

    @app.get("/login")
    def login():
        return render_template("login.html")

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    @app.post("/login")
    def login_post():
        password = os.environ.get("REVIEW_APP_PASSWORD", DEFAULT_PASSWORD)
        if request.form.get("password") == password:
            session["logged_in"] = True
            return redirect(request.args.get("next") or url_for("index"))
        flash("Wrong password.")
        return redirect(url_for("login"))

    @app.post("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.get("/")
    @login_required
    def index():
        rows = query_rows()
        stats = {
            "total": len(rows),
            "matched": sum(1 for row in rows if row["match_status"] == "Matched"),
            "approved": sum(1 for row in rows if row["review_state"] == "approved"),
            "review": sum(1 for row in rows if row["review_state"] == "review"),
            "rejected": sum(1 for row in rows if row["review_state"] == "rejected"),
            "split": sum(1 for row in rows if row["split_charge_count"] > 1),
        }
        filters = {
            "q": request.args.get("q", "").strip(),
            "review_state": request.args.get("review_state", ""),
            "match_status": request.args.get("match_status", ""),
            "split": request.args.get("split", ""),
            "card_last4": request.args.get("card_last4", ""),
        }
        filtered = filter_rows(rows, filters)
        cards = sorted({row["card_last4"] for row in rows if row["card_last4"]})
        return render_template("index.html", rows=filtered, stats=stats, filters=filters, cards=cards)

    @app.get("/bank")
    @login_required
    def bank():
        rows = query_bank_rows()
        filters = {
            "q": request.args.get("q", "").strip(),
            "review_state": request.args.get("review_state", ""),
            "row_type": request.args.get("row_type", ""),
            "card_last4": request.args.get("card_last4", ""),
        }
        filtered = filter_bank_rows(rows, filters)
        stats = {
            "total": len(rows),
            "matched": sum(1 for row in rows if row["row_type"] == "bank_matched"),
            "bank_unmatched": sum(1 for row in rows if row["row_type"] == "bank_unmatched"),
            "amazon_unmatched": sum(1 for row in rows if row["row_type"] == "amazon_unmatched"),
            "approved": sum(1 for row in rows if row["review_state"] == "approved"),
            "review": sum(1 for row in rows if row["review_state"] == "review"),
        }
        cards = sorted({row["inferred_card_last4"] for row in rows if row["inferred_card_last4"] and row["inferred_card_last4"] != "unknown"})
        return render_template("bank.html", rows=filtered, stats=stats, filters=filters, cards=cards)

    @app.get("/admin")
    @login_required
    def admin():
        return render_template("admin.html")

    @app.post("/admin/import-bank")
    @login_required
    def admin_import_bank():
        upload = request.files.get("bank_review")
        if not upload or not upload.filename:
            flash("Choose a bank review CSV first.")
            return redirect(url_for("admin"))
        batch = request.form.get("batch", "").strip() or Path(upload.filename).stem
        rows = read_uploaded_csv(upload)
        with connect() as conn:
            if request.form.get("replace_batch"):
                db_execute(conn, "DELETE FROM bank_review_rows WHERE source_batch = ?", (batch,))
            import_bank_review_rows(conn, rows, batch)
        flash(f"Imported {len(rows)} bank review rows into batch {batch}.")
        return redirect(url_for("bank"))

    @app.post("/admin/import-matches")
    @login_required
    def admin_import_matches():
        matches_upload = request.files.get("matches")
        orders_upload = request.files.get("orders")
        if not matches_upload or not orders_upload or not matches_upload.filename or not orders_upload.filename:
            flash("Choose both Amazon match CSV files first.")
            return redirect(url_for("admin"))
        batch = request.form.get("batch", "").strip() or Path(matches_upload.filename).stem
        matches = read_uploaded_csv(matches_upload)
        orders = {row["order_id"]: row for row in read_uploaded_csv(orders_upload) if row.get("order_id")}
        with connect() as conn:
            if request.form.get("replace_batch"):
                db_execute(conn, "DELETE FROM review_rows WHERE source_batch = ?", (batch,))
            import_match_rows(conn, matches, orders, batch)
        flash(f"Imported {len(matches)} Amazon match rows into batch {batch}.")
        return redirect(url_for("index"))

    @app.post("/decision/<int:row_id>")
    @login_required
    def decision(row_id: int):
        review_state = request.form.get("review_state", "review")
        note = request.form.get("note", "")
        if review_state not in {"approved", "review", "rejected"}:
            review_state = "review"
        with connect() as conn:
            db_execute(
                conn,
                """
                UPDATE review_rows
                SET review_state = ?, note = ?, updated_at = ?
                WHERE id = ?
                """,
                (review_state, note, datetime.utcnow().isoformat(), row_id),
            )
        return redirect(request.referrer or url_for("index"))

    @app.post("/bank/decision/<int:row_id>")
    @login_required
    def bank_decision(row_id: int):
        review_state = request.form.get("review_state", "review")
        note = request.form.get("note", "")
        if review_state not in {"approved", "review", "rejected"}:
            review_state = "review"
        with connect() as conn:
            db_execute(
                conn,
                """
                UPDATE bank_review_rows
                SET review_state = ?, note = ?, updated_at = ?
                WHERE id = ?
                """,
                (review_state, note, datetime.utcnow().isoformat(), row_id),
            )
        return redirect(request.referrer or url_for("bank"))

    @app.get("/export/approved.csv")
    @login_required
    def export_approved():
        rows = [row for row in query_rows() if row["review_state"] == "approved"]
        buffer = io.StringIO()
        fieldnames = [
            "order_id",
            "amazon_date",
            "card_last4",
            "amazon_amount",
            "bank_row_id",
            "bank_date",
            "bank_amount",
            "bank_description",
            "split_charge_count",
            "split_charge_index",
            "review_note",
        ]
        writer = csv.DictWriter(buffer, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "order_id": row["order_id"],
                    "amazon_date": row["amazon_date"],
                    "card_last4": row["card_last4"],
                    "amazon_amount": f"{row['amazon_amount']:.2f}",
                    "bank_row_id": row["bank_row_id"],
                    "bank_date": row["bank_date"],
                    "bank_amount": f"{row['bank_amount']:.2f}" if row["bank_amount"] is not None else "",
                    "bank_description": row["bank_description"],
                    "split_charge_count": row["split_charge_count"],
                    "split_charge_index": row["split_charge_index"],
                    "review_note": row["note"],
                }
            )
        return Response(
            buffer.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=approved_amazon_matches.csv"},
        )

    @app.get("/export/approved-bank.csv")
    @login_required
    def export_approved_bank():
        rows = [row for row in query_bank_rows() if row["review_state"] == "approved"]
        buffer = io.StringIO()
        fieldnames = [
            "row_type",
            "bank_row_id",
            "bank_date",
            "bank_amount",
            "bank_description",
            "inferred_card_last4",
            "order_id",
            "amazon_date",
            "amazon_amount",
            "match_status",
            "review_note",
        ]
        writer = csv.DictWriter(buffer, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row[key] if key != "review_note" else row["note"] for key in fieldnames})
        return Response(
            buffer.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=approved_bank_review.csv"},
        )

    return app


def init_db() -> None:
    if not using_postgres():
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        if not DB_PATH.exists() and SEED_DB_PATH.exists() and SEED_DB_PATH.resolve() != DB_PATH.resolve():
            DB_PATH.write_bytes(SEED_DB_PATH.read_bytes())
    with connect() as conn:
        db_execute(conn, review_rows_schema())
        db_execute(conn, bank_review_rows_schema())


def review_rows_schema() -> str:
    if using_postgres():
        return """
            CREATE TABLE IF NOT EXISTS review_rows (
                id SERIAL PRIMARY KEY,
                order_id TEXT NOT NULL,
                amazon_date TEXT,
                amazon_status TEXT,
                card_last4 TEXT,
                amazon_amount DOUBLE PRECISION NOT NULL,
                merchant TEXT,
                bank_row_id TEXT,
                bank_date TEXT,
                bank_amount DOUBLE PRECISION,
                bank_description TEXT,
                match_status TEXT,
                confidence INTEGER,
                reason TEXT,
                split_status TEXT,
                split_group_total DOUBLE PRECISION,
                split_charge_count INTEGER,
                split_charge_index INTEGER,
                review_state TEXT NOT NULL DEFAULT 'review',
                note TEXT NOT NULL DEFAULT '',
                source_batch TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            )
            """
    return """
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


def bank_review_rows_schema() -> str:
    if using_postgres():
        return """
            CREATE TABLE IF NOT EXISTS bank_review_rows (
                id SERIAL PRIMARY KEY,
                row_type TEXT NOT NULL,
                bank_row_id TEXT,
                bank_date TEXT,
                bank_amount TEXT,
                bank_description TEXT,
                inferred_card_last4 TEXT,
                order_id TEXT,
                amazon_date TEXT,
                amazon_amount TEXT,
                split_group_total TEXT,
                split_charge_count TEXT,
                match_status TEXT,
                confidence INTEGER,
                reason TEXT,
                review_state TEXT NOT NULL DEFAULT 'review',
                note TEXT NOT NULL DEFAULT '',
                source_batch TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            )
            """
    return """
            CREATE TABLE IF NOT EXISTS bank_review_rows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                row_type TEXT NOT NULL,
                bank_row_id TEXT,
                bank_date TEXT,
                bank_amount TEXT,
                bank_description TEXT,
                inferred_card_last4 TEXT,
                order_id TEXT,
                amazon_date TEXT,
                amazon_amount TEXT,
                split_group_total TEXT,
                split_charge_count TEXT,
                match_status TEXT,
                confidence INTEGER,
                reason TEXT,
                review_state TEXT NOT NULL DEFAULT 'review',
                note TEXT NOT NULL DEFAULT '',
                source_batch TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            )
            """


def connect() -> Any:
    if using_postgres():
        import psycopg
        from psycopg.rows import dict_row

        return psycopg.connect(DATABASE_URL, row_factory=dict_row)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def db_execute(conn: Any, sql: str, params: tuple[Any, ...] = ()) -> Any:
    if using_postgres():
        sql = sql.replace("?", "%s")
    return conn.execute(sql, params)


def using_postgres() -> bool:
    return bool(DATABASE_URL)


def query_rows() -> list[Any]:
    with connect() as conn:
        return list(db_execute(conn, "SELECT * FROM review_rows ORDER BY amazon_date DESC, order_id, split_charge_index"))


def query_bank_rows() -> list[Any]:
    with connect() as conn:
        return list(db_execute(conn, "SELECT * FROM bank_review_rows ORDER BY bank_date DESC, amazon_date DESC, id"))


def filter_rows(rows: list[Any], filters: dict[str, str]) -> list[Any]:
    result = []
    query = filters["q"].lower()
    for row in rows:
        if filters["review_state"] and row["review_state"] != filters["review_state"]:
            continue
        if filters["match_status"] and row["match_status"] != filters["match_status"]:
            continue
        if filters["split"] == "split" and row["split_charge_count"] <= 1:
            continue
        if filters["split"] == "single" and row["split_charge_count"] > 1:
            continue
        if filters.get("card_last4") and row["card_last4"] != filters["card_last4"]:
            continue
        if query:
            haystack = " ".join(str(row[key] or "") for key in row.keys()).lower()
            if query not in haystack:
                continue
        result.append(row)
    return result


def filter_bank_rows(rows: list[Any], filters: dict[str, str]) -> list[Any]:
    result = []
    query = filters["q"].lower()
    for row in rows:
        if filters["review_state"] and row["review_state"] != filters["review_state"]:
            continue
        if filters["row_type"] and row["row_type"] != filters["row_type"]:
            continue
        if filters["card_last4"] and row["inferred_card_last4"] != filters["card_last4"]:
            continue
        if query:
            haystack = " ".join(str(row[key] or "") for key in row.keys()).lower()
            if query not in haystack:
                continue
        result.append(row)
    return result


def read_uploaded_csv(upload) -> list[dict[str, str]]:
    text = upload.read().decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text)))


def import_bank_review_rows(conn: Any, rows: list[dict[str, str]], batch: str) -> None:
    now = datetime.utcnow().isoformat()
    for row in rows:
        state = "approved" if row.get("row_type") == "bank_matched" and int_or_default(row.get("confidence"), 0) >= 80 else "review"
        db_execute(
            conn,
            """
            INSERT INTO bank_review_rows (
                row_type, bank_row_id, bank_date, bank_amount, bank_description, inferred_card_last4,
                order_id, amazon_date, amazon_amount, split_group_total, split_charge_count,
                match_status, confidence, reason, review_state, note, source_batch, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', ?, ?)
            """,
            (
                row.get("row_type", ""),
                row.get("bank_row_id", ""),
                row.get("bank_date", ""),
                row.get("bank_amount", ""),
                row.get("bank_description", ""),
                row.get("inferred_card_last4", ""),
                row.get("order_id", ""),
                row.get("amazon_date", ""),
                row.get("amazon_amount", ""),
                row.get("split_group_total", ""),
                row.get("split_charge_count", ""),
                row.get("match_status", ""),
                int_or_default(row.get("confidence"), 0),
                row.get("reason", ""),
                state,
                batch,
                now,
            ),
        )


def import_match_rows(conn: Any, matches: list[dict[str, str]], orders: dict[str, dict[str, str]], batch: str) -> None:
    order_counts = Counter(row.get("order_id", "") for row in matches)
    per_order_index: defaultdict[str, int] = defaultdict(int)
    now = datetime.utcnow().isoformat()
    for row in matches:
        order_id = row.get("order_id", "")
        order = orders.get(order_id, {})
        per_order_index[order_id] += 1
        split_count = int_or_default(order.get("amazon_transaction_count"), order_counts[order_id])
        review_state = "approved" if row.get("match_status") == "Matched" and int_or_default(row.get("confidence"), 0) >= 80 else "review"
        db_execute(
            conn,
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
                money(row.get("amazon_amount")) or 0,
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
    return float(value.replace("$", "").replace(",", "").strip())


app = create_app()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    host = os.environ.get("HOST", "127.0.0.1")
    app.run(host=host, port=port, debug=os.environ.get("FLASK_DEBUG") == "1")

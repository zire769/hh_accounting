from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
import argparse
import csv
import html
import json
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a local accountant review interface from match CSVs.")
    parser.add_argument("--matches", required=True, help="Path to amazon_charge_matches.csv.")
    parser.add_argument("--orders", default="", help="Optional path to amazon_order_summary.csv.")
    parser.add_argument("--out", required=True, help="Output HTML file.")
    parser.add_argument("--title", default="Amazon Reconciliation Review")
    args = parser.parse_args()

    match_rows = read_csv(args.matches)
    order_rows = {row["order_id"]: row for row in read_csv(args.orders)} if args.orders else {}
    enriched = enrich_rows(match_rows, order_rows)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_html(args.title, enriched), encoding="utf-8")
    print(f"Generated review interface for {len(enriched)} charge rows.")
    print(out_path.resolve())
    return 0


def read_csv(path_value: str) -> list[dict[str, str]]:
    if not path_value:
        return []
    path = Path(path_value)
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def enrich_rows(match_rows: list[dict[str, str]], order_rows: dict[str, dict[str, str]]) -> list[dict[str, str]]:
    order_counts = Counter(row.get("order_id", "") for row in match_rows)
    per_order_index: defaultdict[str, int] = defaultdict(int)
    enriched: list[dict[str, str]] = []

    for index, row in enumerate(match_rows, start=1):
        order_id = row.get("order_id", "")
        per_order_index[order_id] += 1
        order = order_rows.get(order_id, {})
        charge_count = int_or_default(order.get("amazon_transaction_count"), order_counts[order_id])
        charge_index = per_order_index[order_id]
        initial_review = "approved" if row.get("match_status") == "Matched" and int_or_default(row.get("confidence"), 0) >= 80 else "review"
        enriched.append(
            {
                "id": f"row-{index}",
                "order_id": order_id,
                "amazon_date": row.get("amazon_date", ""),
                "amazon_status": row.get("amazon_status", ""),
                "card_last4": row.get("card_last4", ""),
                "amazon_amount": row.get("amazon_amount", ""),
                "merchant": row.get("merchant", ""),
                "bank_row_id": row.get("bank_row_id", ""),
                "bank_date": row.get("bank_date", ""),
                "bank_amount": row.get("bank_amount", ""),
                "bank_description": row.get("bank_description", ""),
                "match_status": row.get("match_status", ""),
                "confidence": row.get("confidence", ""),
                "reason": row.get("reason", ""),
                "order_status": order.get("match_status", ""),
                "split_status": order.get("split_status", "split Amazon charge" if charge_count > 1 else "single Amazon charge"),
                "split_group_total": order.get("amazon_group_total", ""),
                "split_charge_count": str(charge_count),
                "split_charge_index": str(charge_index),
                "initial_review": initial_review,
            }
        )
    return enriched


def int_or_default(value: str | None, default: int) -> int:
    try:
        return int(value or "")
    except ValueError:
        return default


def render_html(title: str, rows: list[dict[str, str]]) -> str:
    data = json.dumps(rows, ensure_ascii=False)
    escaped_title = html.escape(title)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escaped_title}</title>
  <style>
    :root {{
      --bg: #f5f6f8;
      --panel: #ffffff;
      --ink: #111827;
      --muted: #5b6472;
      --line: #d9dde5;
      --accent: #0f766e;
      --warn: #b45309;
      --bad: #b91c1c;
      --good-bg: #e8f5f1;
      --warn-bg: #fff7ed;
      --bad-bg: #fef2f2;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: var(--bg); color: var(--ink); font-family: Arial, sans-serif; }}
    header {{ position: sticky; top: 0; z-index: 2; background: var(--panel); border-bottom: 1px solid var(--line); }}
    .bar {{ max-width: 1320px; margin: 0 auto; padding: 16px 20px; display: grid; grid-template-columns: 1fr auto; gap: 16px; align-items: center; }}
    h1 {{ margin: 0; font-size: 22px; line-height: 1.2; }}
    .sub {{ margin-top: 4px; color: var(--muted); font-size: 13px; }}
    main {{ max-width: 1320px; margin: 0 auto; padding: 18px 20px 40px; }}
    .controls {{ display: grid; grid-template-columns: minmax(220px, 1fr) repeat(4, auto); gap: 10px; align-items: center; margin-bottom: 14px; }}
    input, select, button, textarea {{ font: inherit; }}
    input, select {{ height: 36px; border: 1px solid var(--line); border-radius: 6px; padding: 0 10px; background: white; min-width: 0; }}
    button {{ border: 1px solid var(--line); border-radius: 6px; background: white; height: 34px; padding: 0 10px; cursor: pointer; }}
    button.primary {{ background: var(--accent); color: white; border-color: var(--accent); }}
    button:hover {{ filter: brightness(0.97); }}
    .stats {{ display: grid; grid-template-columns: repeat(5, minmax(120px, 1fr)); gap: 10px; margin-bottom: 14px; }}
    .stat {{ background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 12px; }}
    .stat b {{ display: block; font-size: 20px; }}
    .stat span {{ color: var(--muted); font-size: 12px; }}
    table {{ width: 100%; border-collapse: separate; border-spacing: 0; background: var(--panel); border: 1px solid var(--line); border-radius: 8px; overflow: hidden; }}
    th, td {{ border-bottom: 1px solid var(--line); padding: 9px 8px; font-size: 13px; text-align: left; vertical-align: top; }}
    th {{ background: #eef1f5; color: #303846; position: sticky; top: 73px; z-index: 1; }}
    tr:last-child td {{ border-bottom: 0; }}
    tr.approved {{ background: var(--good-bg); }}
    tr.review {{ background: var(--warn-bg); }}
    tr.rejected {{ background: var(--bad-bg); }}
    .pill {{ display: inline-block; border-radius: 999px; padding: 3px 7px; font-size: 12px; border: 1px solid var(--line); background: white; white-space: nowrap; }}
    .pill.good {{ border-color: #8fc7b8; color: #065f46; }}
    .pill.warn {{ border-color: #fed7aa; color: var(--warn); }}
    .pill.bad {{ border-color: #fecaca; color: var(--bad); }}
    .amount {{ text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }}
    .actions {{ display: flex; flex-wrap: wrap; gap: 5px; min-width: 180px; }}
    .actions button {{ height: 28px; font-size: 12px; }}
    textarea {{ width: 100%; min-width: 170px; height: 50px; resize: vertical; border: 1px solid var(--line); border-radius: 6px; padding: 6px; }}
    .muted {{ color: var(--muted); }}
    .mono {{ font-family: Consolas, monospace; }}
    @media (max-width: 900px) {{
      .bar, .controls, .stats {{ grid-template-columns: 1fr; }}
      th {{ position: static; }}
      table {{ display: block; overflow-x: auto; }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="bar">
      <div>
        <h1>{escaped_title}</h1>
        <div class="sub">Review Amazon-to-bank matches. Decisions are saved in this browser and can be exported.</div>
      </div>
      <button class="primary" id="exportApproved">Export approved CSV</button>
    </div>
  </header>
  <main>
    <section class="stats" id="stats"></section>
    <section class="controls">
      <input id="search" placeholder="Search order, amount, card, bank text">
      <select id="reviewFilter">
        <option value="">All review states</option>
        <option value="approved">Approved</option>
        <option value="review">Needs review</option>
        <option value="rejected">Rejected</option>
      </select>
      <select id="matchFilter">
        <option value="">All match statuses</option>
        <option value="Matched">Matched</option>
        <option value="Needs review">Needs review</option>
      </select>
      <select id="splitFilter">
        <option value="">All orders</option>
        <option value="split">Split only</option>
        <option value="single">Single only</option>
      </select>
      <button id="resetFilters">Reset</button>
    </section>
    <table>
      <thead>
        <tr>
          <th>Review</th>
          <th>Amazon</th>
          <th class="amount">Amount</th>
          <th>Bank Match</th>
          <th>Split</th>
          <th>Confidence</th>
          <th>Notes</th>
          <th>Actions</th>
        </tr>
      </thead>
      <tbody id="rows"></tbody>
    </table>
  </main>
  <script>
    const rows = {data};
    const storageKey = "amazon-review:" + location.pathname;
    const saved = JSON.parse(localStorage.getItem(storageKey) || "{{}}");
    const state = Object.fromEntries(rows.map(row => [row.id, {{ review: row.initial_review, note: "" }}]));
    Object.assign(state, saved);

    const rowsEl = document.getElementById("rows");
    const statsEl = document.getElementById("stats");
    const searchEl = document.getElementById("search");
    const reviewFilterEl = document.getElementById("reviewFilter");
    const matchFilterEl = document.getElementById("matchFilter");
    const splitFilterEl = document.getElementById("splitFilter");

    function persist() {{
      localStorage.setItem(storageKey, JSON.stringify(state));
    }}

    function money(value) {{
      return value ? "$" + Number(value).toFixed(2) : "";
    }}

    function pill(text, kind) {{
      return `<span class="pill ${{kind || ""}}">${{escapeHtml(text || "")}}</span>`;
    }}

    function escapeHtml(value) {{
      return String(value ?? "").replace(/[&<>"']/g, char => ({{ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }}[char]));
    }}

    function filteredRows() {{
      const query = searchEl.value.trim().toLowerCase();
      return rows.filter(row => {{
        const rowState = state[row.id]?.review || row.initial_review;
        if (reviewFilterEl.value && rowState !== reviewFilterEl.value) return false;
        if (matchFilterEl.value && row.match_status !== matchFilterEl.value) return false;
        if (splitFilterEl.value === "split" && Number(row.split_charge_count) <= 1) return false;
        if (splitFilterEl.value === "single" && Number(row.split_charge_count) > 1) return false;
        if (!query) return true;
        return JSON.stringify(row).toLowerCase().includes(query) || (state[row.id]?.note || "").toLowerCase().includes(query);
      }});
    }}

    function renderStats() {{
      const counts = rows.reduce((acc, row) => {{
        const review = state[row.id]?.review || row.initial_review;
        acc[review] = (acc[review] || 0) + 1;
        if (row.match_status === "Matched") acc.matched += 1;
        if (Number(row.split_charge_count) > 1) acc.split += 1;
        return acc;
      }}, {{ approved: 0, review: 0, rejected: 0, matched: 0, split: 0 }});
      statsEl.innerHTML = [
        ["Total rows", rows.length],
        ["Matched charges", counts.matched],
        ["Split charge rows", counts.split],
        ["Approved", counts.approved],
        ["Needs review", counts.review],
      ].map(([label, value]) => `<div class="stat"><b>${{value}}</b><span>${{label}}</span></div>`).join("");
    }}

    function render() {{
      renderStats();
      const visible = filteredRows();
      rowsEl.innerHTML = visible.map(row => {{
        const rowState = state[row.id]?.review || row.initial_review;
        const note = state[row.id]?.note || "";
        const matchKind = row.match_status === "Matched" ? "good" : "bad";
        const reviewKind = rowState === "approved" ? "good" : rowState === "rejected" ? "bad" : "warn";
        const splitText = Number(row.split_charge_count) > 1
          ? `${{row.split_charge_index}}/${{row.split_charge_count}} · group $${{Number(row.split_group_total || 0).toFixed(2)}}`
          : "single";
        return `<tr class="${{rowState}}">
          <td>${{pill(rowState, reviewKind)}}</td>
          <td>
            <div class="mono">${{escapeHtml(row.order_id)}}</div>
            <div>${{escapeHtml(row.amazon_date)}} · Card ****${{escapeHtml(row.card_last4)}}</div>
            <div class="muted">${{escapeHtml(row.merchant || "Amazon")}}</div>
          </td>
          <td class="amount">${{money(row.amazon_amount)}}</td>
          <td>
            ${{pill(row.match_status, matchKind)}}
            <div>${{escapeHtml(row.bank_date)}} ${{row.bank_amount ? "· $" + Number(row.bank_amount).toFixed(2) : ""}}</div>
            <div class="muted">${{escapeHtml(row.bank_description)}}</div>
          </td>
          <td>${{escapeHtml(splitText)}}</td>
          <td>
            <b>${{escapeHtml(row.confidence || "0")}}</b>
            <div class="muted">${{escapeHtml(row.reason)}}</div>
          </td>
          <td><textarea data-note="${{row.id}}">${{escapeHtml(note)}}</textarea></td>
          <td>
            <div class="actions">
              <button data-action="approved" data-id="${{row.id}}">Approve</button>
              <button data-action="review" data-id="${{row.id}}">Review</button>
              <button data-action="rejected" data-id="${{row.id}}">Reject</button>
            </div>
          </td>
        </tr>`;
      }}).join("");
    }}

    function exportCsv() {{
      const approved = rows.filter(row => (state[row.id]?.review || row.initial_review) === "approved");
      const headers = ["order_id", "amazon_date", "card_last4", "amazon_amount", "bank_row_id", "bank_date", "bank_amount", "bank_description", "split_charge_count", "split_charge_index", "review_note"];
      const csvRows = [headers.join(",")].concat(approved.map(row => headers.map(key => {{
        const value = key === "review_note" ? (state[row.id]?.note || "") : (row[key] || "");
        return '"' + String(value).replaceAll('"', '""') + '"';
      }}).join(",")));
      const blob = new Blob([csvRows.join("\\n")], {{ type: "text/csv;charset=utf-8" }});
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "approved_amazon_matches.csv";
      link.click();
      URL.revokeObjectURL(url);
    }}

    document.addEventListener("click", event => {{
      const button = event.target.closest("button[data-action]");
      if (!button) return;
      state[button.dataset.id] = state[button.dataset.id] || {{}};
      state[button.dataset.id].review = button.dataset.action;
      persist();
      render();
    }});
    document.addEventListener("input", event => {{
      if (event.target.matches("textarea[data-note]")) {{
        const id = event.target.dataset.note;
        state[id] = state[id] || {{}};
        state[id].note = event.target.value;
        persist();
      }}
      if ([searchEl, reviewFilterEl, matchFilterEl, splitFilterEl].includes(event.target)) render();
    }});
    document.getElementById("resetFilters").addEventListener("click", () => {{
      searchEl.value = "";
      reviewFilterEl.value = "";
      matchFilterEl.value = "";
      splitFilterEl.value = "";
      render();
    }});
    document.getElementById("exportApproved").addEventListener("click", exportCsv);
    render();
  </script>
</body>
</html>"""


if __name__ == "__main__":
    sys.exit(main())

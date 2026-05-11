# Amazon Reconciliation Bot

This is a first MVP for the Amazon accounting headache:

```text
Amazon payment transactions -> linked Amazon orders -> QuickBooks/bank transaction matching
```

It is a reconciliation bot, not a full accounting system. The math is deterministic. AI can be added later for category classification and accountant-facing explanations.

## What It Solves

Amazon often splits one order into multiple card charges. QuickBooks sees card charges, while employees/accountants tend to think in Amazon order totals.

This tool groups Amazon charges by:

```text
order_id + card_last4
```

Then it matches each Amazon charge to QuickBooks/bank CSV rows by:

```text
amount + date window + card/account text + Amazon merchant text
```

## Quick Smoke Test

```powershell
python -m amazon_recon parse-amazon --amazon samples/amazon_transactions_sample.txt
python -m amazon_recon reconcile --amazon samples/amazon_transactions_sample.txt --bank samples/qbo_bank_sample.csv --out output/sample
```

Open:

```text
output/sample/amazon_reconciliation_report.html
```

## Real Workflow

1. Capture or export the Amazon Transactions page.
2. Export QuickBooks/bank transactions as CSV.
3. Run reconciliation.
4. Accountant reviews only exceptions.

```powershell
python -m amazon_recon reconcile --amazon data/amazon_transactions.html --bank data/qbo_bank.csv --out output/current
```

For a specific period:

```powershell
python -m amazon_recon reconcile --amazon data/amazon_transactions.html --bank data/qbo_bank.csv --out output/march_april_2026 --start-date 2026-03-01 --end-date 2026-04-30
```

## Capturing Amazon Transactions

The browser capture script is intentionally semi-automated. You log in manually so the bot does not store passwords or fight MFA/CAPTCHA.

Install Playwright once:

```powershell
python -m pip install playwright
python -m playwright install chromium
```

Then capture:

```powershell
python scripts/capture_amazon_transactions.py --out data/amazon_transactions.html
```

When the browser opens, log in and make sure the Transactions page is visible. Press Enter in the terminal to save the page HTML.

Then capture linked order pages:

```powershell
python scripts/capture_amazon_order_pages.py --amazon data/amazon_transactions.html --out-dir data/amazon_orders
```

This saves one HTML file per order ID. The next parser can use those pages for ship-to/store, items, invoice links, and category suggestions.

## Outputs

The reconciliation command writes:

- `amazon_order_summary.csv`: grouped order view, including split orders.
- `amazon_charge_matches.csv`: transaction-by-transaction bank matching.
- `amazon_reconciliation_report.html`: accountant-friendly review report.

For Amazon-only exports:

- `amazon_grouped_orders.csv`: review only. Do not import this into QuickBooks because split orders are collapsed into one row.
- `amazon_charge_transactions_qbo_prep.csv`: one row per real Amazon card charge. This is the safer import/prep shape because it matches bank-feed transaction granularity.

## Next Build Step

Add order-detail extraction:

```text
transaction row -> order link -> order page -> ship-to/store/items/invoice
```

That will let the report include category suggestions and store/entity context.

## Private Review Web App

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

Import a match batch:

```powershell
python web_app\import_matches.py `
  --matches output\april_2026_chase_3255_match\amazon_charge_matches.csv `
  --orders output\april_2026_chase_3255_match\amazon_order_summary.csv `
  --batch april_2026_chase_3255 `
  --replace-batch
```

Run locally:

```powershell
$env:REVIEW_APP_PASSWORD="change-this-password"
$env:REVIEW_APP_SECRET="change-this-secret"
python web_app\app.py
```

Open:

```text
http://127.0.0.1:5000
```

For a deployed app with no local seed database, log in and open:

```text
/admin
```

Upload `chase_bank_review_by_card.csv` for the main accountant review screen. You can also upload `amazon_charge_matches.csv` plus `amazon_order_summary.csv` for the Amazon-centric view.

For remote accountant access, deploy the Flask app behind HTTPS with a real password and a persistent SQLite/Postgres database. Do not expose the local development server directly to the internet.

Remote deployment notes are in `DEPLOYMENT.md`.

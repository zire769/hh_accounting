# Remote Deployment

The review portal can run for an accountant outside your network, but do not expose the Flask development server directly to the internet.

## Option A: Hosted Private Web App

Use this when the accountant should have a stable URL from anywhere.

Recommended free shape:

```text
Render Free Web Service + external Postgres database + HTTPS + password login
```

Required environment variables:

```text
REVIEW_APP_PASSWORD
REVIEW_APP_SECRET
DATABASE_URL
```

Production command:

```text
gunicorn web_app.app:app
```

Render Blueprint:

```text
render.yaml
```

The Blueprint creates a free Python web service and sets `/health` as the health check. The app uses Postgres when `DATABASE_URL` is present, so no paid Render disk is required. Render requires web services to bind to `0.0.0.0` and the provided `$PORT`; the Blueprint start command does this.

Free database options include Supabase, Neon, or any hosted Postgres provider that gives you a normal Postgres connection string. Paste that connection string into Render as `DATABASE_URL`.

After the first deploy, log in and open:

```text
/admin
```

Upload `chase_bank_review_by_card.csv` for the accountant's main review screen. You can optionally upload `amazon_charge_matches.csv` and `amazon_order_summary.csv` for the Amazon-centric view.

For Docker hosts:

```powershell
docker build -t amazon-review .
docker run -p 8000:8000 `
  -e REVIEW_APP_PASSWORD="replace-with-a-long-password" `
  -e REVIEW_APP_SECRET="replace-with-a-random-secret" `
  amazon-review
```

## Option B: Cloudflare Tunnel To Local Machine

Use this when you want the app to keep running on your computer, but the accountant can access it through a public HTTPS URL.

Local production server on Windows:

```powershell
$env:REVIEW_APP_PASSWORD="replace-with-a-long-password"
$env:REVIEW_APP_SECRET="replace-with-a-random-secret"
waitress-serve --host 127.0.0.1 --port 8000 web_app.app:app
```

Then configure Cloudflare Tunnel to route your chosen hostname to:

```text
http://localhost:8000
```

Cloudflare Tunnel maps a public hostname to a local service and proxies HTTPS traffic to it. Keep Cloudflare Access or another login layer enabled when possible.

## Local Data

Local app data still uses SQLite when `DATABASE_URL` is not set:

```text
data/review_app.sqlite3
```

For local testing, import the batch you want the accountant to review:

```powershell
python web_app\import_matches.py `
  --matches output\april_2026_chase_all_cards_match\amazon_charge_matches.csv `
  --orders output\april_2026_chase_all_cards_match\amazon_order_summary.csv `
  --batch april_2026_chase_all_cards `
  --replace-batch

python web_app\import_bank_review.py `
  --bank-review output\april_2026_chase_all_cards_match\chase_bank_review_by_card.csv `
  --batch april_2026_chase_bank_by_card `
  --replace-batch
```

## Security Notes

- Use a long password.
- Keep HTTPS on.
- Do not commit real accounting CSVs to a public repository.
- Rotate the password if an accountant leaves.
- For multiple accountants, the next upgrade should be per-user accounts instead of one shared password.

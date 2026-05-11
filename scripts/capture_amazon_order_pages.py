from __future__ import annotations

import argparse
from pathlib import Path
from urllib.parse import urljoin
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT_URL = "https://www.amazon.com"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Visit order links found in a saved Amazon Transactions page and save each order page HTML."
    )
    parser.add_argument("--amazon", default="data/amazon_transactions.html", help="Saved Amazon Transactions HTML.")
    parser.add_argument("--out-dir", default="data/amazon_orders", help="Directory for saved order HTML files.")
    parser.add_argument("--profile-dir", default="data/browser-profile", help="Persistent browser profile directory.")
    args = parser.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright is not installed. Run: python -m pip install playwright && python -m playwright install chromium")
        return 2

    from amazon_recon.amazon_parser import group_transactions, load_amazon_transactions

    transactions = load_amazon_transactions(args.amazon)
    groups = group_transactions(transactions)
    with_links = [group for group in groups if any(tx.order_url for tx in group.transactions)]
    if not with_links:
        print("No order links found. Save the Amazon Transactions page as HTML instead of copied text.")
        return 1

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=args.profile_dir,
            headless=False,
            viewport={"width": 1440, "height": 1000},
        )
        page = context.pages[0] if context.pages else context.new_page()
        print("If Amazon asks, finish login/MFA in the opened browser.")
        input("Press Enter when the browser is ready to visit order pages...")

        for group in with_links:
            order_url = next(tx.order_url for tx in group.transactions if tx.order_url)
            full_url = urljoin(ROOT_URL, order_url)
            page.goto(full_url, wait_until="domcontentloaded")
            page.wait_for_timeout(1500)
            out_file = out_dir / f"{group.order_id}.html"
            out_file.write_text(page.content(), encoding="utf-8")
            print(f"Saved {out_file}")

        context.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())

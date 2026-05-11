from __future__ import annotations

import argparse
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


DEFAULT_URL = "https://www.amazon.com/cpe/yourpayments/transactions"
NEXT_SELECTORS = (
    "input[name*='DefaultNextPageNavigationEvent']",
    "input[name*='NextPage']",
    "span.a-button-text:has-text('Next Page')",
    "span:has-text('Next Page')",
    "a:has-text('Next')",
    "button:has-text('Next')",
    "a:has-text('Older')",
    "button:has-text('Older')",
    "a:has-text('Show more')",
    "button:has-text('Show more')",
    "input[aria-label*='Next']",
    "a[aria-label*='Next']",
    "button[aria-label*='Next']",
    ".a-pagination .a-last a",
)
MORE_SELECTORS = (
    "a:has-text('Show more')",
    "button:has-text('Show more')",
    "a:has-text('Load more')",
    "button:has-text('Load more')",
    "a:has-text('Older')",
    "button:has-text('Older')",
    "input[aria-label*='More']",
    "button[aria-label*='More']",
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Open Amazon in a real browser session and save the Transactions page HTML. "
            "You log in manually; the script only captures the page after you confirm it is loaded."
        )
    )
    parser.add_argument("--url", default=DEFAULT_URL, help="Amazon transactions URL.")
    parser.add_argument("--out", default="data/amazon_transactions.html", help="Where to save page HTML.")
    parser.add_argument("--pages-dir", default="", help="Optional directory to save each paginated page.")
    parser.add_argument("--profile-dir", default="data/browser-profile", help="Persistent browser profile directory.")
    parser.add_argument("--period", default="", help="Human-readable period to show in the login prompt.")
    parser.add_argument(
        "--signal-file",
        default="",
        help="Optional file path. If set, save the page after this file appears instead of waiting for Enter.",
    )
    parser.add_argument("--auto-pages", action="store_true", help="After login, save/click through transaction pages automatically.")
    parser.add_argument("--max-pages", type=int, default=25, help="Safety limit for auto-pagination.")
    parser.add_argument(
        "--stop-before",
        default="",
        help="Stop after a saved page includes transactions before this date, for example 2026-03-01.",
    )
    parser.add_argument(
        "--chrome-channel",
        default="",
        help="Optional Playwright browser channel, for example chrome. Leave blank for bundled Chromium.",
    )
    args = parser.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright is not installed. Run: python -m pip install playwright && python -m playwright install chromium")
        return 2

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        launch_kwargs = {
            "user_data_dir": args.profile_dir,
            "headless": False,
            "viewport": {"width": 1440, "height": 1000},
        }
        if args.chrome_channel:
            launch_kwargs["channel"] = args.chrome_channel
        context = p.chromium.launch_persistent_context(**launch_kwargs)
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(args.url, wait_until="domcontentloaded")
        print("Log in if Amazon asks. Navigate to the Transactions page.")
        if args.period:
            print(f"Set Amazon's transaction date filter/search to include: {args.period}")
        if args.signal_file:
            signal_path = Path(args.signal_file)
            signal_path.parent.mkdir(parents=True, exist_ok=True)
            if signal_path.exists():
                signal_path.unlink()
            print(f"Waiting for save signal: {signal_path.resolve()}")
            while not signal_path.exists():
                time.sleep(1)
        else:
            input("When the transactions list is visible, press Enter here to save the page HTML...")
        if args.auto_pages:
            saved = capture_paginated_pages(page, out_path, Path(args.pages_dir) if args.pages_dir else None, args.max_pages, args.stop_before)
            print(f"Saved {saved} transaction page(s). Combined HTML: {out_path.resolve()}")
        else:
            out_path.write_text(page.content(), encoding="utf-8")
            print(f"Saved {out_path.resolve()}")
        context.close()
    return 0


def capture_paginated_pages(page, combined_out: Path, pages_dir: Path | None, max_pages: int, stop_before: str) -> int:
    from amazon_recon.amazon_parser import load_amazon_transactions, parse_transactions_text, html_to_text
    from amazon_recon.date_utils import parse_date

    stop_date = parse_date(stop_before)
    combined_out.parent.mkdir(parents=True, exist_ok=True)
    if pages_dir:
        pages_dir.mkdir(parents=True, exist_ok=True)

    page_chunks: list[str] = []
    seen_urls: set[str] = set()

    last_signature = ""
    stalled_rounds = 0

    for page_number in range(1, max_pages + 1):
        page.wait_for_load_state("domcontentloaded", timeout=30000)
        page.wait_for_timeout(1200)
        html = page.content()
        page_chunks.append(f"\n<!-- AMAZON_TRANSACTION_PAGE {page_number} {page.url} -->\n{html}\n")
        if pages_dir:
            (pages_dir / f"amazon_transactions_page_{page_number:03}.html").write_text(html, encoding="utf-8")

        page_text = html_to_text(html)
        transactions = parse_transactions_text(page_text)
        dates = [tx.transaction_date for tx in transactions if tx.transaction_date]
        if dates:
            print(f"Page {page_number}: {len(transactions)} transactions, date range {min(dates)} to {max(dates)}")
            if stop_date and min(dates) < stop_date:
                print(f"Reached transactions before {stop_date}; stopping pagination.")
                break
        else:
            print(f"Page {page_number}: no transactions parsed yet.")

        signature = f"{len(html)}:{len(transactions)}:{min(dates) if dates else ''}:{max(dates) if dates else ''}"
        if signature == last_signature:
            stalled_rounds += 1
        else:
            stalled_rounds = 0
        last_signature = signature

        current_url = page.url
        if current_url in seen_urls and page_number > 1:
            pass
        seen_urls.add(current_url)

        progressed = click_more_or_scroll(page)
        if not progressed:
            stalled_rounds += 1
            print("No visible pagination/load-more progress; trying scroll fallback.")
        if stalled_rounds >= 4:
            print("Page stopped changing after several attempts; stopping pagination.")
            break

    combined_out.write_text("\n".join(page_chunks), encoding="utf-8")
    return len(page_chunks)


def click_more_or_scroll(page) -> bool:
    if click_selector_set(page, MORE_SELECTORS):
        return True
    before_height = get_scroll_height(page)
    try:
        page.mouse.wheel(0, 5000)
        page.wait_for_timeout(1800)
    except Exception:
        return False
    after_height = get_scroll_height(page)
    if after_height and before_height and after_height > before_height:
        return True
    if click_selector_set(page, NEXT_SELECTORS):
        return True
    return False


def click_selector_set(page, selectors: tuple[str, ...]) -> bool:
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if locator.count() == 0:
                continue
            if not locator.is_visible() and not selector.startswith("input"):
                continue
            locator.click(timeout=5000, force=selector.startswith("input"))
            try:
                page.wait_for_load_state("domcontentloaded", timeout=15000)
            except Exception:
                pass
            page.wait_for_timeout(2500)
            return True
        except Exception:
            continue
    return False


def get_scroll_height(page) -> int:
    try:
        return page.locator("body").evaluate("body => document.documentElement.scrollHeight || body.scrollHeight")
    except Exception:
        return 0


def click_next_page(page) -> bool:
    return click_selector_set(page, NEXT_SELECTORS)


if __name__ == "__main__":
    sys.exit(main())

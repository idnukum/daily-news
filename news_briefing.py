#!/usr/bin/env python3
"""
Morning news briefing -> ntfy push notification.

Pulls headlines from RSS feeds across three areas (Tech & AI, Business & markets,
World + South Africa), builds a compact summary with links, and POSTs it to an
ntfy topic so it lands as a push notification on your phone.

Designed to run on GitHub Actions on a daily cron, but also runs locally.

Config via environment variables:
  NTFY_TOPIC   (required)  e.g. "news-mukundi-x7k2p9"
  NTFY_SERVER  (optional)  defaults to "https://ntfy.sh"
  NTFY_TOKEN   (optional)  bearer token if your topic is protected
  MAX_PER_CAT  (optional)  headlines per category, default 4
"""

import os
import sys
import html
import datetime as dt
from urllib.parse import urlparse

import requests
import feedparser

# ---------------------------------------------------------------------------
# Feed configuration: category -> list of RSS feed URLs (tried in order).
# ---------------------------------------------------------------------------
FEEDS = {
    "💻 Tech & AI": [
        "https://techcrunch.com/feed/",
        "https://www.theverge.com/rss/index.xml",
        "https://arstechnica.com/feed/",
    ],
    "📈 Business & Markets": [
        "https://feeds.bbci.co.uk/news/business/rss.xml",  # BBC Business (reliable)
        "https://feeds.marketwatch.com/marketwatch/topstories/",
        "https://www.cnbc.com/id/10001147/device/rss/rss.html",  # CNBC Finance
    ],
    "🌍 World & South Africa": [
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://www.dailymaverick.co.za/dmrss/",
        "https://feeds.24.com/articles/news24/TopStories/rss",
    ],
}

MAX_PER_CAT = int(os.environ.get("MAX_PER_CAT", "4"))
HTTP_TIMEOUT = 20
HEADERS = {"User-Agent": "Mozilla/5.0 (news-briefing-bot)"}


def fetch_feed(url):
    """Fetch and parse a single RSS feed, returning a list of (title, link)."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=HTTP_TIMEOUT)
        resp.raise_for_status()
        parsed = feedparser.parse(resp.content)
        items = []
        for entry in parsed.entries:
            title = html.unescape((entry.get("title") or "").strip())
            link = (entry.get("link") or "").strip()
            if title and link:
                items.append((title, link))
        return items
    except Exception as e:  # noqa: BLE001 - never let one feed kill the run
        print(f"  ! feed failed ({url}): {e}", file=sys.stderr)
        return []


def gather(category, urls, want):
    """Collect up to `want` unique headlines for a category across its feeds."""
    seen_titles = set()
    out = []
    for url in urls:
        if len(out) >= want:
            break
        for title, link in fetch_feed(url):
            key = title.lower()
            if key in seen_titles:
                continue
            seen_titles.add(key)
            out.append((title, link))
            if len(out) >= want:
                break
    print(f"  {category}: {len(out)} stories", file=sys.stderr)
    return out


def source_name(link):
    """Human-friendly source label from a URL host."""
    host = urlparse(link).netloc.replace("www.", "")
    return host


def build_message():
    """Return (title, body, top_link) for the ntfy notification."""
    today = dt.datetime.now().strftime("%A, %d %B %Y")
    lines = []
    top_link = None

    for category, urls in FEEDS.items():
        stories = gather(category, urls, MAX_PER_CAT)
        if not stories:
            continue
        lines.append(f"{category}")
        for title, link in stories:
            if top_link is None:
                top_link = link
            lines.append(f"• {title}\n  {link}")
        lines.append("")  # blank line between categories

    body = "\n".join(lines).strip()
    if not body:
        body = "No stories could be fetched today - all feeds failed. Check the workflow logs."
    # HTTP header values must be Latin-1, so keep the Title ASCII (hyphen, not em dash).
    title = f"Morning Briefing - {today}"
    return title, body, top_link


def _latin1_safe(value):
    """Strip characters that can't go in an HTTP header (headers are Latin-1)."""
    return str(value).encode("latin-1", "ignore").decode("latin-1")


def send_to_ntfy(title, body, top_link):
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        print("ERROR: NTFY_TOPIC env var is not set.", file=sys.stderr)
        sys.exit(1)

    server = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
    url = f"{server}/{topic}"

    headers = {
        "Title": title,
        "Tags": "newspaper",
        "Priority": "default",
        # Render URLs/formatting nicely in the ntfy app:
        "Markdown": "yes",
    }
    if top_link:
        # Tapping the notification opens the top story.
        headers["Click"] = top_link
    token = os.environ.get("NTFY_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    # Ensure every header value is Latin-1 safe (HTTP header requirement).
    headers = {k: _latin1_safe(v) for k, v in headers.items()}

    resp = requests.post(
        url,
        data=body.encode("utf-8"),
        headers=headers,
        timeout=HTTP_TIMEOUT,
    )
    resp.raise_for_status()
    print(f"Sent briefing to {url} ({len(body)} chars)")


def main():
    print("Building morning briefing...", file=sys.stderr)
    title, body, top_link = build_message()
    print("-" * 60)
    print(title)
    print("-" * 60)
    print(body)
    print("-" * 60)
    send_to_ntfy(title, body, top_link)


if __name__ == "__main__":
    main()

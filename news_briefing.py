#!/usr/bin/env python3
# v2: NYT-style HTML page + ntfy teaser
"""
Morning news briefing -> styled HTML page (NYT-ish) + ntfy push notification.

Two modes:
  build   (default)  Fetch feeds, write public/index.html (the newspaper page)
                     and public/notification.txt (the teaser body).
  notify             Read the teaser + SITE_URL and push it to ntfy, with the
                     notification linking to the published page.

Designed for GitHub Actions + GitHub Pages, but also runs locally.

Environment variables:
  NTFY_TOPIC   (notify)   e.g. "news-mukundi-x7k2p9"
  SITE_URL     (notify)   URL of the deployed Pages site (tap target)
  NTFY_SERVER  (optional) defaults to "https://ntfy.sh"
  NTFY_TOKEN   (optional) bearer token if your topic is protected
  MAX_PER_CAT  (optional) headlines per category, default 5
"""

import os
import re
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
    "Tech & AI": [
        "https://techcrunch.com/feed/",
        "https://www.theverge.com/rss/index.xml",
        "https://arstechnica.com/feed/",
    ],
    "Business & Markets": [
        "https://feeds.bbci.co.uk/news/business/rss.xml",
        "https://feeds.marketwatch.com/marketwatch/topstories/",
        "https://www.cnbc.com/id/10001147/device/rss/rss.html",
    ],
    "World & South Africa": [
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://www.dailymaverick.co.za/dmrss/",
        "https://feeds.24.com/articles/news24/TopStories/rss",
    ],
}

MAX_PER_CAT = int(os.environ.get("MAX_PER_CAT", "5"))
HTTP_TIMEOUT = 20
HEADERS = {"User-Agent": "Mozilla/5.0 (news-briefing-bot)"}
OUT_DIR = "public"

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def clean_text(raw, limit=180):
    """Strip HTML tags/entities and collapse whitespace; truncate to `limit`."""
    if not raw:
        return ""
    text = html.unescape(_TAG_RE.sub(" ", raw))
    text = _WS_RE.sub(" ", text).strip()
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0].rstrip(",.;:") + "…"
    return text


def source_name(link):
    host = urlparse(link).netloc.replace("www.", "")
    labels = {
        "techcrunch.com": "TechCrunch",
        "theverge.com": "The Verge",
        "arstechnica.com": "Ars Technica",
        "bbc.co.uk": "BBC",
        "bbci.co.uk": "BBC",
        "marketwatch.com": "MarketWatch",
        "cnbc.com": "CNBC",
        "dailymaverick.co.za": "Daily Maverick",
        "news24.com": "News24",
    }
    for key, label in labels.items():
        if host.endswith(key):
            return label
    return host


def fetch_feed(url):
    """Return list of dicts: {title, link, dek, source} for one feed."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=HTTP_TIMEOUT)
        resp.raise_for_status()
        parsed = feedparser.parse(resp.content)
        items = []
        for entry in parsed.entries:
            title = html.unescape((entry.get("title") or "").strip())
            link = (entry.get("link") or "").strip()
            if not (title and link):
                continue
            dek = clean_text(entry.get("summary") or entry.get("description") or "")
            items.append(
                {"title": title, "link": link, "dek": dek, "source": source_name(link)}
            )
        return items
    except Exception as e:  # noqa: BLE001
        print(f"  ! feed failed ({url}): {e}", file=sys.stderr)
        return []


def gather(category, urls, want):
    seen = set()
    out = []
    for url in urls:
        if len(out) >= want:
            break
        for item in fetch_feed(url):
            key = item["title"].lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(item)
            if len(out) >= want:
                break
    print(f"  {category}: {len(out)} stories", file=sys.stderr)
    return out


def collect():
    """Return ordered dict-like list of (category, [items])."""
    data = []
    for category, urls in FEEDS.items():
        stories = gather(category, urls, MAX_PER_CAT)
        if stories:
            data.append((category, stories))
    return data


# ---------------------------------------------------------------------------
# HTML page (New York Times-ish styling)
# ---------------------------------------------------------------------------
PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>The Morning Briefing — {date}</title>
<style>
  :root {{ --ink:#121212; --muted:#666; --rule:#dcdcdc; --accent:#326891; }}
  * {{ box-sizing:border-box; }}
  body {{
    margin:0; background:#f7f7f2; color:var(--ink);
    font-family:Georgia,'Times New Roman',serif; line-height:1.5;
    -webkit-font-smoothing:antialiased;
  }}
  .wrap {{ max-width:720px; margin:0 auto; padding:28px 20px 64px; }}
  header.masthead {{ text-align:center; border-bottom:3px double var(--ink);
    padding-bottom:14px; margin-bottom:8px; }}
  .kicker {{ font-size:12px; letter-spacing:.22em; text-transform:uppercase;
    color:var(--muted); border-bottom:1px solid var(--rule); border-top:1px solid var(--rule);
    padding:6px 0; margin-bottom:14px; }}
  h1.title {{ font-size:44px; line-height:1.05; margin:6px 0 6px; font-weight:800;
    letter-spacing:-0.5px; }}
  .dateline {{ font-size:13px; color:var(--muted); font-style:italic; }}
  section.cat {{ margin-top:34px; }}
  h2.cat-name {{ font-size:13px; letter-spacing:.18em; text-transform:uppercase;
    font-weight:700; color:var(--ink); border-bottom:2px solid var(--ink);
    padding-bottom:6px; margin:0 0 4px; }}
  article {{ padding:16px 0; border-bottom:1px solid var(--rule); }}
  article:last-child {{ border-bottom:none; }}
  a.headline {{ color:var(--ink); text-decoration:none; font-size:21px;
    font-weight:700; line-height:1.25; display:block; }}
  a.headline:hover {{ color:var(--accent); text-decoration:underline; }}
  .src {{ font-size:11px; letter-spacing:.12em; text-transform:uppercase;
    color:var(--accent); margin:8px 0 4px; font-family:Georgia,serif; font-weight:700; }}
  .dek {{ font-size:15px; color:#333; margin:2px 0 0; }}
  footer {{ margin-top:44px; text-align:center; font-size:12px; color:var(--muted);
    border-top:1px solid var(--rule); padding-top:16px; }}
  @media (max-width:480px) {{
    h1.title {{ font-size:32px; }} a.headline {{ font-size:19px; }}
  }}
</style>
</head>
<body>
  <div class="wrap">
    <header class="masthead">
      <div class="kicker">Your Daily Digest &middot; Tech &middot; Markets &middot; World</div>
      <h1 class="title">The Morning Briefing</h1>
      <div class="dateline">{long_date}</div>
    </header>
    {sections}
    <footer>
      Auto-generated from public RSS feeds &middot; Updated {time} &middot;
      Sources: TechCrunch, The Verge, Ars Technica, BBC, MarketWatch, CNBC, Daily Maverick, News24
    </footer>
  </div>
</body>
</html>
"""


def render_html(data, now):
    sections = []
    for category, stories in data:
        arts = []
        for s in stories:
            dek = f'<p class="dek">{html.escape(s["dek"])}</p>' if s["dek"] else ""
            arts.append(
                f'<article>'
                f'<a class="headline" href="{html.escape(s["link"])}">{html.escape(s["title"])}</a>'
                f'<div class="src">{html.escape(s["source"])}</div>'
                f'{dek}'
                f'</article>'
            )
        sections.append(
            f'<section class="cat"><h2 class="cat-name">{html.escape(category)}</h2>'
            + "".join(arts)
            + "</section>"
        )
    if not sections:
        sections = ["<section class='cat'><p>No stories could be fetched today. "
                    "Check the workflow logs.</p></section>"]
    return PAGE_TEMPLATE.format(
        date=now.strftime("%d %b %Y"),
        long_date=now.strftime("%A, %d %B %Y"),
        time=now.strftime("%H:%M UTC"),
        sections="\n".join(sections),
    )


def build_teaser(data, now):
    """Short plain-text body for the ntfy notification."""
    lines = [now.strftime("%A, %d %B %Y"), ""]
    for category, stories in data:
        lines.append(f"{category}:")
        for s in stories[:2]:  # top 2 per section keeps the push compact
            lines.append(f"• {s['title']}")
        lines.append("")
    lines.append("Tap to read the full briefing →")
    return "\n".join(lines).strip()


def cmd_build():
    now = dt.datetime.utcnow()
    print("Building briefing page...", file=sys.stderr)
    data = collect()
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(render_html(data, now))
    with open(os.path.join(OUT_DIR, "notification.txt"), "w", encoding="utf-8") as f:
        f.write(build_teaser(data, now))
    print(f"Wrote {OUT_DIR}/index.html and {OUT_DIR}/notification.txt")


def _latin1_safe(value):
    """Strip characters that can't go in an HTTP header (headers are Latin-1)."""
    return str(value).encode("latin-1", "ignore").decode("latin-1")


def cmd_notify():
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        print("ERROR: NTFY_TOPIC env var is not set.", file=sys.stderr)
        sys.exit(1)

    teaser_path = os.path.join(OUT_DIR, "notification.txt")
    try:
        with open(teaser_path, encoding="utf-8") as f:
            body = f.read().strip()
    except FileNotFoundError:
        body = "Your morning briefing is ready. Tap to read."

    site_url = os.environ.get("SITE_URL", "").strip()
    server = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
    url = f"{server}/{topic}"

    today = dt.datetime.utcnow().strftime("%A, %d %B %Y")
    headers = {
        "Title": f"Morning Briefing - {today}",
        "Tags": "newspaper",
        "Priority": "default",
    }
    if site_url:
        headers["Click"] = site_url  # tap the notification -> open the page
    token = os.environ.get("NTFY_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    headers = {k: _latin1_safe(v) for k, v in headers.items()}

    resp = requests.post(
        url, data=body.encode("utf-8"), headers=headers, timeout=HTTP_TIMEOUT
    )
    resp.raise_for_status()
    print(f"Sent notification to {url} (links to {site_url or 'no site'})")


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "build"
    if mode == "build":
        cmd_build()
    elif mode == "notify":
        cmd_notify()
    else:
        print(f"Unknown mode: {mode} (use 'build' or 'notify')", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()

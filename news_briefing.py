#!/usr/bin/env python3
# v3: NYT-style HTML page + images + more SA sources + ntfy teaser
"""
Morning news briefing -> styled HTML page (NYT-ish, with images) + ntfy push.

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
# SOURCES: category -> list of RSS feed URLs (tried in order).
# This is the ONLY place you edit to change what the briefing pulls from.
# Add, remove, or reorder feed URLs freely. A feed that fails is skipped.
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
        "https://businesstech.co.za/news/feed/",
    ],
    "South Africa": [
        "https://www.dailymaverick.co.za/dmrss/",
        "https://feeds.24.com/articles/news24/TopStories/rss",
        "https://mg.co.za/feed/",
        "https://ewn.co.za/rss",
    ],
    "World": [
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://www.aljazeera.com/xml/rss/all.xml",
    ],
}

MAX_PER_CAT = int(os.environ.get("MAX_PER_CAT", "5"))
HTTP_TIMEOUT = 20
HEADERS = {"User-Agent": "Mozilla/5.0 (news-briefing-bot)"}
OUT_DIR = "public"

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_IMG_RE = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)


def clean_text(raw, limit=180):
    """Strip HTML tags/entities and collapse whitespace; truncate to `limit`."""
    if not raw:
        return ""
    text = html.unescape(_TAG_RE.sub(" ", raw))
    text = _WS_RE.sub(" ", text).strip()
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0].rstrip(",.;:") + "…"
    return text


def extract_image(entry):
    """Best-effort image URL from a feed entry, across the common RSS variants."""
    # 1) media:thumbnail
    for thumb in entry.get("media_thumbnail", []) or []:
        if thumb.get("url"):
            return thumb["url"]
    # 2) media:content (images only)
    for media in entry.get("media_content", []) or []:
        url = media.get("url")
        if url and (media.get("medium") == "image" or "image" in (media.get("type") or "")):
            return url
    # 3) enclosures / links marked as image
    for link in entry.get("links", []) or []:
        if link.get("rel") == "enclosure" and (link.get("type") or "").startswith("image"):
            return link.get("href")
    for enc in entry.get("enclosures", []) or []:
        if (enc.get("type") or "").startswith("image") and enc.get("href"):
            return enc["href"]
    # 4) first <img> inside the summary/content HTML
    for field in ("summary", "description"):
        m = _IMG_RE.search(entry.get(field) or "")
        if m:
            return m.group(1)
    for content in entry.get("content", []) or []:
        m = _IMG_RE.search(content.get("value") or "")
        if m:
            return m.group(1)
    return None


def source_name(link):
    host = urlparse(link).netloc.replace("www.", "")
    labels = {
        "techcrunch.com": "TechCrunch",
        "theverge.com": "The Verge",
        "arstechnica.com": "Ars Technica",
        "bbc.co.uk": "BBC",
        "bbci.co.uk": "BBC",
        "aljazeera.com": "Al Jazeera",
        "marketwatch.com": "MarketWatch",
        "cnbc.com": "CNBC",
        "dailymaverick.co.za": "Daily Maverick",
        "news24.com": "News24",
        "businesstech.co.za": "BusinessTech",
        "mg.co.za": "Mail & Guardian",
        "ewn.co.za": "EWN",
    }
    for key, label in labels.items():
        if host.endswith(key):
            return label
    return host


def fetch_feed(url):
    """Return list of dicts: {title, link, dek, source, image} for one feed."""
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
            items.append({
                "title": title,
                "link": link,
                "dek": dek,
                "source": source_name(link),
                "image": extract_image(entry),
            })
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
    data = []
    for category, urls in FEEDS.items():
        stories = gather(category, urls, MAX_PER_CAT)
        if stories:
            data.append((category, stories))
    return data


# ---------------------------------------------------------------------------
# HTML page (New York Times-ish styling, with thumbnails)
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
  article {{ display:flex; gap:16px; align-items:flex-start;
    padding:16px 0; border-bottom:1px solid var(--rule); }}
  article:last-child {{ border-bottom:none; }}
  .txt {{ flex:1; min-width:0; }}
  .thumb {{ flex:0 0 120px; width:120px; height:84px; object-fit:cover;
    border:1px solid var(--rule); background:#eee; }}
  a.headline {{ color:var(--ink); text-decoration:none; font-size:21px;
    font-weight:700; line-height:1.25; display:block; }}
  a.headline:hover {{ color:var(--accent); text-decoration:underline; }}
  .src {{ font-size:11px; letter-spacing:.12em; text-transform:uppercase;
    color:var(--accent); margin:8px 0 4px; font-weight:700; }}
  .dek {{ font-size:15px; color:#333; margin:2px 0 0; }}
  footer {{ margin-top:44px; text-align:center; font-size:12px; color:var(--muted);
    border-top:1px solid var(--rule); padding-top:16px; }}
  @media (max-width:480px) {{
    h1.title {{ font-size:32px; }} a.headline {{ font-size:18px; }}
    .thumb {{ flex-basis:96px; width:96px; height:70px; }}
  }}
</style>
</head>
<body>
  <div class="wrap">
    <header class="masthead">
      <div class="kicker">Your Daily Digest &middot; Tech &middot; Markets &middot; SA &middot; World</div>
      <h1 class="title">The Morning Briefing</h1>
      <div class="dateline">{long_date}</div>
    </header>
    {sections}
    <footer>
      Auto-generated from public RSS feeds &middot; Updated {time}
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
            img = (f'<img class="thumb" loading="lazy" src="{html.escape(s["image"])}" '
                   f'alt="">' if s.get("image") else "")
            arts.append(
                f'<article>'
                f'<div class="txt">'
                f'<a class="headline" href="{html.escape(s["link"])}">{html.escape(s["title"])}</a>'
                f'<div class="src">{html.escape(s["source"])}</div>'
                f'{dek}'
                f'</div>'
                f'{img}'
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

# Morning News Briefing → Phone (via GitHub Actions + ntfy)

A daily news briefing that runs **in the cloud on GitHub Actions** (no computer
required) and pushes a summary with links straight to your phone using
[ntfy](https://ntfy.sh). Covers three areas: **Tech & AI**, **Business &
Markets**, and **World & South Africa**.

Runs every day at **06:00 SAST** (04:00 UTC). Everything is free — no paid APIs.

---

## What's in this repo

| File | Purpose |
|------|---------|
| `news_briefing.py` | Fetches headlines from RSS feeds and posts to ntfy |
| `requirements.txt` | Python dependencies |
| `.github/workflows/news-briefing.yml` | The daily schedule (GitHub Actions) |

---

## One-time setup (about 10 minutes)

### 1. Install the ntfy app and pick a topic

1. Install **ntfy** on your phone: [Android (Play Store)](https://play.google.com/store/apps/details?id=io.heckel.ntfy) · [iOS (App Store)](https://apps.apple.com/us/app/ntfy/id1625396347).
2. Open the app → **+** → **Subscribe to topic**.
3. Enter a **hard-to-guess topic name** — this is your private channel. Anyone
   who knows the name can read your briefing, so treat it like a password.
   Example: `news-mukundi-a7x93k`. Tap **Subscribe**.

> Keep this topic name handy — you'll paste it into GitHub in step 3.

### 2. Create the GitHub repository

1. Go to <https://github.com/new>.
2. Name it e.g. `morning-briefing`, set it to **Private** (recommended), and
   click **Create repository**.
3. Add the files. Easiest way in the browser:
   - Click **uploading an existing file** on the new repo page.
   - Drag in `news_briefing.py`, `requirements.txt`, and `README.md`.
   - For the workflow, the folder matters: click **Add file → Create new file**,
     type `.github/workflows/news-briefing.yml` as the filename (GitHub creates
     the folders as you type the slashes), paste the contents of the provided
     `news-briefing.yml`, and commit.

   *(If you use Git locally instead: put `news-briefing.yml` inside a
   `.github/workflows/` folder, keep the other files at the repo root, then
   commit and push.)*

### 3. Add your ntfy topic as a secret

1. In the repo: **Settings → Secrets and variables → Actions → New repository secret**.
2. **Name:** `NTFY_TOPIC`
3. **Value:** the topic name from step 1 (e.g. `news-mukundi-a7x93k`).
4. Click **Add secret**.

> Using a secret keeps your topic name out of the public code.

### 4. Run a test

1. Go to the **Actions** tab. If prompted, click **I understand my workflows,
   enable them**.
2. Select **Morning News Briefing** on the left → **Run workflow** → **Run workflow**.
3. Within a minute you should get a push notification on your phone. Tapping it
   opens the top story; individual links inside are tappable too.

That's it. From now on it runs automatically every morning.

---

## Customizing

- **Change the time:** edit the `cron` line in `news-briefing.yml`. It's in
  **UTC**, so subtract 2 hours from your SAST time. Examples:
  - `0 4 * * *` → 06:00 SAST
  - `0 5 * * *` → 07:00 SAST
  - `30 3 * * 1-5` → 05:30 SAST, weekdays only
- **Change topics / sources:** edit the `FEEDS` dictionary at the top of
  `news_briefing.py`. Add or swap any RSS feed URL.
- **More or fewer headlines per section:** set a `MAX_PER_CAT` repository
  secret (default is 4), or edit the default in the script.
- **Protected / self-hosted ntfy:** add `NTFY_SERVER` and/or `NTFY_TOKEN`
  secrets and uncomment the matching lines in the workflow.

---

## Notes & troubleshooting

- **Scheduled runs can be a few minutes late.** GitHub queues cron jobs and may
  delay them under load — normal, not a bug.
- **No notification?** Check the **Actions** tab for a red run and open the logs.
  Most common cause is a missing/misspelled `NTFY_TOPIC` secret, or not being
  subscribed to the exact same topic name on your phone.
- **A feed occasionally fails** — the script skips it and uses the next feed in
  that category, so one bad feed never stops the briefing.
- **Privacy:** anyone who knows your ntfy topic can read the briefing. Use a
  random topic name; rotate it (update the app subscription + the GitHub secret)
  if you ever shared it.

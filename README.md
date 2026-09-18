# Today Together Rating 聚嚐

Mobile web app for rating the Together canteen menu. Ratings are stored in a Google Sheet
(via a small Apps Script web app) and every rating can be shared to WhatsApp.

## Files

| File | What it is |
|---|---|
| `index.html` | The app. One file, no build step. Open it on a phone (host it anywhere static). |
| `extract_menu.py` | Turns the weekly bilingual menu PDF into `menu.json` and injects it into `index.html`. |
| `menu.json` | This week's menu (14 – 20 Sep 2026), Chinese + English, per meal. |
| `manifest.webmanifest`, `sw.js`, `icons/` | PWA files: home-screen install, full-screen, offline menu. |
| `apps_script.gs` | Source of the Apps Script web app attached to the Google Sheet (for reference / redeploy). |

## Weekly update

```
pip install pdfplumber          # once
python extract_menu.py "F:\BackUp\Together menu on 21 - 27 Sep 2026.pdf"
```
It prints every dish it found — glance over it against the PDF — and updates `index.html`.
Then re-upload `index.html` to wherever you host it.

## The database: Google Sheet "Together Rating DB"

- Sheet: https://docs.google.com/spreadsheets/d/SHEET-ID-REDACTED/edit
  (tab `Ratings`, columns Timestamp · Date · Meal · Food · Rating · Score · Comment · Name)
- Attached Apps Script project **Together Rating API** (source in `apps_script.gs`), deployed as a
  web app (Execute as: me, Access: anyone). The app POSTs each rating to it and GETs the day's
  ratings back to show 👍/👎 counts and average score under each dish.
- Web app URL (already in `index.html` → `CONFIG.apiUrl`):
  `https://script.google.com/macros/s/AKfycby_on4s_4w1KrxNkI5-qxKlOnkPnSTTohanp3yYPeFGfTq1l_U9gLCbmMB_anpdq0Bd/exec`

If you ever change the script: Apps Script → Deploy → **Manage deployments** → ✎ → Version: *New version*
→ Deploy. That keeps the same URL. (A "New deployment" gets a new URL, which you'd then paste into `CONFIG.apiUrl`.)

Ratings that fail to send (no signal) are kept on the phone and retried automatically on the next visit.

## Hosting & installing on phones (PWA)

The app is a Progressive Web App: `manifest.webmanifest`, `sw.js` and `icons/` make it installable
with a home-screen icon, full-screen view and offline menu. It must be served over **HTTPS**.

Hosted on **GitHub Pages** (repo `SimonChan1070/TogtherRating`, branch `main`, root):

**App URL: https://simonchan1070.github.io/TogtherRating/** — share this link in WhatsApp.

To publish changes: `git add -A && git commit -m "..." && git push` — Pages redeploys in about a minute.

Install on phones:
- **Android (Chrome)**: open the link → the app shows an *Install* banner (or ⋮ → *Add to Home screen*).
- **iPhone (Safari)**: open the link → Share ⬆︎ → *Add to Home Screen*.

Weekly menu update = re-run `extract_menu.py`, commit and push; installed apps pick it up on next open
(menu is fetched network-first). If you change `sw.js`, bump `CACHE = "ttr-v2"`.

## What the app does

- Day chips (defaults to today) and Breakfast / Lunch / Dinner / Supper tabs (defaults by clock).
- Tap a dish → 👍 Good / 👎 Not Good, score 0–100 (slider + quick presets), comment, name (remembered).
- **Submit** saves to the Google Sheet and keeps a local copy under "My ratings today".
- Each dish shows everyone's 👍/👎 counts and average score for that day, live from the Sheet.
- **Share to WhatsApp** opens WhatsApp with a formatted message for one rating or the whole day.

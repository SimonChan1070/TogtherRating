# Together Rating 聚嚐

Mobile web app for rating the Together canteen menu. Ratings are stored in a Google Sheet
(via a small Apps Script web app) and every rating can be shared to WhatsApp.

## Files

| File | What it is |
|---|---|
| `index.html` | The app. One file, no build step. Open it on a phone (host it anywhere static). |
| `extract_menu.py` | Imports a weekly bilingual menu PDF into `menus/<start-date>.json`, then rebuilds `menu.json` and injects it into `index.html`. |
| `menus/` | One JSON per week (`2026-09-14.json` = the week starting that Monday), Chinese + English, per meal. Also the **inbox**: drop a PDF here and the Action imports it and deletes the PDF. |
| `menu.json` | The last 12 weeks combined (`{"weeks": [...]}`, oldest first) — what the app ships. |
| `manifest.webmanifest`, `sw.js`, `icons/` | PWA files: home-screen install, full-screen, offline menu. |
| `.github/workflows/update-menu.yml` | GitHub Action: import waiting PDFs → delete them → commit → Pages redeploy. |
| `menu_bridge.gs` | Apps Script: forwards new PDFs from a Drive folder / Gmail into `menus/`. |
| `apps_script.gs` | Source of the Apps Script web app attached to the Google Sheet (for reference / redeploy). |

## Weekly update — three ways

**A. Upload the PDF on GitHub (easiest, works from a phone)**
1. Open https://github.com/SimonChan1070/TogtherRating/tree/main/menus
2. *Add file → Upload files* → drop the new PDF (keep the canteen's name, e.g. `Together menu on 21 - 27 Sep 2026.pdf`) → *Commit changes*.
3. The **Update menu from PDF** Action (`.github/workflows/update-menu.yml`) extracts the week into
   `menus/<date>.json`, **deletes the PDF from the repo**, rebuilds `index.html` and commits; Pages redeploys
   ~1 min later. Check progress under the repo's *Actions* tab.
   Note: routes A and B commit the PDF before it is deleted, so it stays visible in the repo's git history.
   Only route C never commits it. If that matters, use C or make the repo private (GitHub Pages then needs a paid plan).

**B. Google Drive folder or Gmail (automatic)** — `menu_bridge.gs`
A standalone Apps Script checks every 15 minutes for new PDFs in a Drive folder and/or emails with subject
"Together menu" and pushes them into `menus/` on GitHub (which triggers A). Setup steps are at the top of `menu_bridge.gs`;
it needs a GitHub fine-grained token (repo → Contents: read/write) stored as a script property.

**C. On this PC**
```
pip install pdfplumber          # once
python extract_menu.py "F:\BackUp\Together menu on 21 - 27 Sep 2026.pdf"
git add -A && git commit -m "Menu 21-27 Sep" && git push
```
The extractor prints every dish it found — glance over it against the PDF. A PDF outside `menus/` is never
deleted (only ones inside the inbox folder are); the PDF itself is not committed, only `menus/2026-09-21.json`.
Fix a typo by editing that JSON file and re-running `python extract_menu.py --all menus` (rebuilds with no PDF).

## The database: Google Sheet "Together Rating DB"

- A private Google Sheet in the owner's Drive (sharing: Restricted — the link is deliberately not in this
  repo). Tab `Ratings`, columns Timestamp · Date · Meal · Food · Rating · Score · Comment · Name.
- Attached Apps Script project **Together Rating API** (source in `apps_script.gs`), deployed as a
  web app (Execute as: me, Access: anyone). The app POSTs each rating to it and GETs the day's
  ratings back to show 👍/👎 counts and average score under each dish.
- The web app URL lives in `index.html` → `CONFIG.apiUrl`. `doGet` returns rating rows without the
  Name column, so names never leave the Sheet.

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

Weekly menu update = import the PDF (see above), commit and push; installed apps pick it up on next open
(menu is fetched network-first). Next week's menu can be imported as soon as the canteen sends it — the app
keeps showing the current week by default and the new one appears under ›. If you change `sw.js`, bump `CACHE = "ttr-v2"`.

## What the app does

- Week bar ‹ 14 – 20 Sep 2026 › (tap the label for a picker): browse past weeks and their ratings, or a coming
  week once its menu is imported. Defaults to the week containing today. Up to 12 weeks are carried in the app.
- Day chips (defaults to today) and Breakfast / Lunch / Dinner / Supper tabs (defaults by clock).
- Tap a dish → 👍 Good / 👎 Not Good, score 0–100 (slider + quick presets), comment, optional name (remembered, never shown to others).
- **Submit** saves to the Google Sheet and keeps a local copy under "My ratings today".
- Each dish shows everyone's 👍/👎 counts, average score and the latest comments for that day, live from the Sheet; tapping a dish lists all of them.
- Bottom tab **All ratings 全部評價**: a feed of every rating and comment for the selected day, grouped by meal and dish, with a day summary (count, average, % good). Each meal and dish collapses/expands (tap the chevron), plus Collapse all / Expand all and Refresh.
- Neither the Sheet link nor the rating service URL is shown anywhere in the app.
- **Share to WhatsApp as image** draws a rating card (meal, dish, comment, 👍/👎, score) as a PNG and opens the phone's share sheet so it can be sent to WhatsApp as a picture; on desktop it offers "Save image" instead.

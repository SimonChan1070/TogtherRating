"""
Extract the weekly Together canteen menu (bilingual PDF) into menu.json.

Usage:
    python extract_menu.py "F:\\BackUp\\Together menu on 14 - 20 Sep 2026.pdf"
        import one PDF (from anywhere) into menus/<start-date>.json and rebuild the app
    python extract_menu.py --all menus
        import every PDF waiting in the folder, then rebuild (what the GitHub Action runs)

Each imported week is stored as menus/YYYY-MM-DD.json (its Monday). A PDF that sits inside
menus/ is deleted once imported, so the repo keeps only the food lists, not the canteen's PDFs
(pass --keep-pdf to skip that). menu.json and the <script id="menu-data"> block in index.html
are then rebuilt from the newest KEEP_WEEKS JSON files (oldest first):
{
  "weeks": [
    {"week": "14 - 20 Sep 2026",
     "days": [
       {"date": "2026-09-14", "weekday": "Mon", "theme": "Green Monday",
        "meals": {"Breakfast": [{"en": "...", "zh": "..."}], "Lunch": [...], "Dinner": [...], "Supper": [...]}}
     ]}
  ]
}

The PDF has 2 pages with the same grid: page 1 Chinese, page 2 English.
Columns: Date | Breakfast | Lunch | Dinner | Supper.
"""
import json
import os
import re
import sys
import warnings
from collections import Counter
from datetime import date

warnings.filterwarnings("ignore")
import pdfplumber  # noqa: E402

MEALS = ["Breakfast", "Lunch", "Dinner", "Supper"]
KEEP_WEEKS = 12  # how many weeks the app carries (each week is ~10 KB inside index.html)
WEEKS_DIR = "menus"  # per-week JSON files (and the inbox for new PDFs), next to this script
EN_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
ZH_DAYS = ["一", "二", "三", "四", "五", "六", "日"]
MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}


def column_bounds(page):
    """Vertical grid lines are drawn as thin rects; the 4 most frequent x0 values are the column borders."""
    c = Counter(round(r["x0"]) for r in page.rects if r["width"] < 2)
    xs = sorted(x for x, n in c.most_common(4))
    return [0] + xs + [page.width]


def row_bounds(page, day_names, first_col_right):
    words = page.extract_words()
    # the weekday column is "Mon".."Sun" or "一".."日" - the English page has used both over time
    for names in (day_names, ZH_DAYS, EN_DAYS):
        anchors = [w for w in words if w["text"] in names and w["x0"] < first_col_right]
        if len(anchors) == 7:
            break
    else:
        raise SystemExit(f"expected 7 day anchors, found {len(anchors)}: {[a['text'] for a in anchors]}")
    anchors.sort(key=lambda w: w["top"])
    centers = [(a["top"] + a["bottom"]) / 2 for a in anchors]
    header_bottom = max((w["bottom"] for w in words if w["top"] < centers[0] - 60), default=0) + 2
    # the grid's vertical border rects end where the table ends; the disclaimer footer sits below that
    footer_top = max((r["bottom"] for r in page.rects if r["width"] < 2), default=page.height)
    # rows are separated by drawn horizontal grid lines; rows differ in height, so prefer those
    # over the midpoints between weekday anchors (a tall row would otherwise swallow its neighbour)
    hlines = sorted({round(r["top"]) for r in page.rects if r["height"] < 2 and r["width"] > 100
                     and header_bottom < r["top"] < footer_top - 4})
    if len(hlines) == 6 and all(hlines[i] < centers[i + 1] and hlines[i] > centers[i] for i in range(6)):
        edges = [header_bottom] + hlines + [footer_top - 2]
    else:
        edges = [header_bottom] + [(centers[i] + centers[i + 1]) / 2 for i in range(6)] + [footer_top - 2]
    return anchors, list(zip(edges, edges[1:]))


def cell_lines(words, x0, x1, y0, y1):
    """Words inside a cell, grouped into visual lines. Returns list of (text, pixel_width, [word texts])."""
    ws = [w for w in words if x0 <= (w["x0"] + w["x1"]) / 2 < x1 and y0 <= (w["top"] + w["bottom"]) / 2 < y1]
    ws.sort(key=lambda w: (round(w["top"] / 4), w["x0"]))
    lines = []
    for w in ws:
        if lines and abs(w["top"] - lines[-1]["top"]) < 4:
            lines[-1]["words"].append(w)
        else:
            lines.append({"top": w["top"], "words": [w]})
    out = []
    for ln in lines:
        ln["words"].sort(key=lambda w: w["x0"])
        text = " ".join(w["text"] for w in ln["words"])
        out.append((text.strip(), ln["words"][-1]["x1"] - ln["words"][0]["x0"], [w["text"] for w in ln["words"]]))
    return out


def group_zh(lines):
    """Chinese dishes are one per line. Two wrap shapes occur: a 1-char line is the tail of the
    previous dish, and a short (<=2 char) word separated by a gap at the end of a line is the head
    of the next dish, which continues on the following line ("...豬骨湯 草" / "菇蒜子浸菜心")."""
    dishes = []
    pending = None  # head fragment waiting for the next line
    for text, width, words in lines:
        words = [w for w in words if w.strip()]
        if not words:
            continue
        head = None
        if len(words) > 1 and len(words[-1]) <= 2:
            head = words.pop()
        text = "".join(words)
        if pending is not None:
            dishes.append((pending + text, width))
            pending = None
        elif dishes and len(text) <= 1:
            dishes[-1] = (dishes[-1][0] + text, dishes[-1][1])
        else:
            dishes.append((text, width))
        pending = head
    if pending is not None:
        dishes.append((pending, 0))
    return dishes


# an English line ending in one of these almost certainly wrapped ("...with Dried" / "Small Shrimps")
CONNECTIVES = {"with", "and", "in", "of", "&", "w", "chinese", "preserved", "dried", "fresh", "style", "sweet",
               "salted", "black", "red", "small", "mixed", "minced", "bean", "fried", "braised", "steamed", "thai",
               "japanese", "sea", "hong", "kong-style", "diced", "sliced", "coconut", "lotus"}
GENERIC_TAILS = {"soup", "sauce", "noodle", "noodles", "rice", "vegetable", "vegetables"}
TYPO_FIX = {"Marcaroni": "Macaroni", "Blamck": "Black", "Balck": "Black", "Prok": "Pork", "vegetbles": "vegetables",
            "Potatos": "Potatoes"}
THEME_DEFAULT = {"Mon": "Green Monday"}  # printed as a logo image, not text


def merge_by_width(items, need, sep=" "):
    """items: list of (text, width_of_last_line). Merge `need` times where the previous
    dish's last line is widest, i.e. the line most likely to have wrapped."""
    items = list(items)
    for _ in range(need):
        if len(items) < 2:
            break
        i = max(range(1, len(items)), key=lambda i: items[i - 1][1])
        items[i - 1:i + 1] = [(items[i - 1][0] + sep + items[i][0], items[i][1])]
    return items


def wrap_score(prev, cur, last):
    """How likely it is that visual line `cur` is a continuation of `prev` (higher = more likely)."""
    tail, head = prev.split()[-1].lower(), cur.split()[0].lower()
    # always joined: "Hard Boiled Egg &" / "Macaroni Soup" (the caller splits "&" again if the
    # Chinese column has two dishes) and a line starting "with"/"and"/"in" ("Instant Noodle Soup" / "with Spicy Pork")
    if tail == "&" or head in ("with", "and", "in", "of", "&", "(") or head.startswith("("):
        return 4
    if tail in CONNECTIVES or tail.endswith(","):
        return 3
    if last and head in GENERIC_TAILS:  # "...Udon with Pork" / "Soup": "Soup" alone is never a dish
        return 3
    if cur[0].islower():
        return 2
    if len(cur.split()) == 1 and not last:  # a lone word mid-cell ("Shrimps") is usually a spill-over
        return 1
    return 0  # a lone LAST word is more often a fruit/dessert dish ("Banana") than a spill-over


def group_en(lines, k):
    """Merge N visual lines into the k dishes the Chinese column says there are.
    Each line break gets a wrap likelihood. Near-certain wraps (score >= 3) are always merged; if
    that still leaves more than k dishes, the next most likely breaks go too (ties: wider previous
    line first). Ending up below k is fine - the caller splits "A & B" or merges Chinese lines."""
    lines = [(t, w) for t, w, _ in lines if t]
    n = len(lines)
    if n == 0:
        return []
    breaks = [(wrap_score(lines[i - 1][0], lines[i][0], i == n - 1), lines[i - 1][1], i) for i in range(1, n)]
    chosen = {i for sc, _, i in breaks if sc >= 3}
    rest = [b for b in breaks if b[0] < 3]
    need = n - len(chosen) - k
    if k > 0 and need > 0:
        chosen |= {i for _, _, i in sorted(rest, reverse=True)[:need]}
    elif not k:
        chosen |= {i for sc, _, i in rest if sc >= 2}
    dishes = []
    for i, (t, w) in enumerate(lines):
        if i in chosen and dishes:
            dishes[-1] = (dishes[-1][0] + " " + t, w)
        else:
            dishes.append((t, w))
    return dishes


def parse_page(page, day_names):
    cols = column_bounds(page)
    anchors, rows = row_bounds(page, day_names, cols[1])
    words = page.extract_words()
    days = []
    for (y0, y1) in rows:
        date_lines = [t for t, _, _ in cell_lines(words, cols[0], cols[1], y0, y1)]
        cells = {}
        for mi, meal in enumerate(MEALS):
            cells[meal] = cell_lines(words, cols[mi + 1], cols[mi + 2], y0, y1)
        days.append({"date_lines": date_lines, "cells": cells})
    return days


def inject_into_app(data, html_path):
    """Replace the <script id="menu-data"> block in index.html so the app ships the new week."""
    if not os.path.exists(html_path):
        return
    html = open(html_path, encoding="utf-8").read()
    block = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    new, n = re.subn(r'(<script id="menu-data" type="application/json">\s*)(.*?)(\s*</script>)',
                     lambda m: m.group(1) + block + m.group(3), html, count=1, flags=re.S)
    if n:
        open(html_path, "w", encoding="utf-8").write(new)
        print(f"updated {html_path}")


WEEK_RE = r"(\d{1,2})\s*-\s*(\d{1,2})\s+([A-Za-z]{3})[a-z]*\s+(\d{4})"


def week_start(path):
    """Sort key for a menu PDF: the week's start date parsed from its filename, else its mtime."""
    m = re.search(WEEK_RE, os.path.basename(path))
    if m and m.group(3).lower() in MONTHS:
        return (1, date(int(m.group(4)), MONTHS[m.group(3).lower()], int(m.group(1))).toordinal())
    return (0, int(os.path.getmtime(path)))


def parse_pdf(pdf_path):
    """One PDF -> {"week": "14 - 20 Sep 2026", "days": [...]}."""
    m = re.search(WEEK_RE, os.path.basename(pdf_path))
    year = int(m.group(4)) if m else date.today().year
    week_label = f"{m.group(1)} - {m.group(2)} {m.group(3)} {year}" if m else ""
    default_month = MONTHS.get(m.group(3).lower()) if m else date.today().month

    with pdfplumber.open(pdf_path) as pdf:
        zh = parse_page(pdf.pages[0], ZH_DAYS)
        en = parse_page(pdf.pages[1], EN_DAYS)

    days = []
    last_month = default_month
    for i in range(7):
        joined = " ".join(en[i]["date_lines"])
        dm = re.search(r"(\d{1,2})/(\d{0,2})", joined)
        day = int(dm.group(1))
        month = int(dm.group(2)) if dm and dm.group(2) else last_month
        last_month = month
        theme = " ".join(t for t in en[i]["date_lines"]
                         if not re.search(r"\d", t) and "self serve" not in t.lower()
                         and t not in EN_DAYS and t not in ZH_DAYS).strip() or THEME_DEFAULT.get(EN_DAYS[i], "")
        meals = {}
        for meal in MEALS:
            zh_d = group_zh(zh[i]["cells"][meal])
            en_d = group_en(en[i]["cells"][meal], len(zh_d))
            # fewer English dishes than Chinese: "A & B" is two items in Chinese, else Chinese wrapped
            while len(en_d) < len(zh_d) and any(" & " in t for t, _ in en_d):
                j = next(j for j, (t, _) in enumerate(en_d) if " & " in t)
                a, b = en_d[j][0].split(" & ", 1)
                en_d[j:j + 1] = [(a, 0), (b, 0)]
            if len(en_d) < len(zh_d):
                zh_d = merge_by_width(zh_d, len(zh_d) - len(en_d), sep="")
            items = []
            for j in range(max(len(zh_d), len(en_d))):
                en_t = en_d[j][0] if j < len(en_d) else ""
                for bad, good in TYPO_FIX.items():
                    en_t = en_t.replace(bad, good)
                items.append({"en": en_t, "zh": zh_d[j][0] if j < len(zh_d) else ""})
            meals[meal] = items
        days.append({"date": date(year, month, day).isoformat(), "weekday": EN_DAYS[i],
                     "theme": theme, "meals": meals})
    return {"week": week_label, "days": days}


def week_file(folder, w):
    return os.path.join(folder, w["days"][0]["date"] + ".json")


def load_weeks(folder):
    """All menus/YYYY-MM-DD.json -> list of weeks, oldest first, newest KEEP_WEEKS only."""
    weeks = []
    for f in os.listdir(folder) if os.path.isdir(folder) else []:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}\.json", f):
            with open(os.path.join(folder, f), encoding="utf-8") as fh:
                w = json.load(fh)
            if isinstance(w, dict) and w.get("days"):
                weeks.append(w)
    weeks.sort(key=lambda w: w["days"][0]["date"])
    return weeks[-KEEP_WEEKS:]


def print_week(w):
    print(f"\n=== {w['week']} ===")
    for d in w["days"]:
        print(f"\n{d['weekday']} {d['date']} [{d['theme']}]")
        for meal in MEALS:
            for it in d["meals"][meal]:
                print(f"  {meal:9s} {it['en']}  |  {it['zh']}")


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    args = [a for a in sys.argv[1:] if a != "--keep-pdf"]
    keep_pdf = "--keep-pdf" in sys.argv
    here = os.path.dirname(os.path.abspath(__file__))
    folder = os.path.join(here, WEEKS_DIR)
    os.makedirs(folder, exist_ok=True)

    if args[0] == "--all":
        inbox = args[1] if len(args) > 1 else folder
        pdfs = sorted((os.path.join(inbox, f) for f in os.listdir(inbox) if f.lower().endswith(".pdf")), key=week_start)
        if not pdfs:
            print(f"no PDF files in {inbox} - rebuilding from the stored weeks")
    else:
        pdfs = [args[0]]

    for pdf_path in pdfs:
        print(f"parsing {pdf_path}")
        w = parse_pdf(pdf_path)
        with open(week_file(folder, w), "w", encoding="utf-8") as f:
            json.dump(w, f, ensure_ascii=False, indent=2)
        print(f"stored {week_file(folder, w)}")
        print_week(w)
        # the PDF is only an inbox item once it is inside menus/; never touch files elsewhere (e.g. a backup drive)
        if not keep_pdf and os.path.dirname(os.path.abspath(pdf_path)) == os.path.abspath(folder):
            os.remove(pdf_path)
            print(f"deleted {pdf_path}")

    weeks = load_weeks(folder)
    if not weeks:
        raise SystemExit("no weeks stored - nothing to build")
    data = {"weeks": weeks}
    out_path = os.path.join(here, "menu.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\nwrote {out_path} ({len(weeks)} week{'s' if len(weeks) != 1 else ''}: "
          f"{weeks[0]['week']} .. {weeks[-1]['week']})")
    inject_into_app(data, os.path.join(here, "index.html"))


if __name__ == "__main__":
    main()

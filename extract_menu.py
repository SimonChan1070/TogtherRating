"""
Extract the weekly Together canteen menu (bilingual PDF) into menu.json.

Usage:
    python extract_menu.py "F:\\BackUp\\Together menu on 14 - 20 Sep 2026.pdf" [menu.json]

The PDF has 2 pages with the same grid: page 1 Chinese, page 2 English.
Columns: Date | Breakfast | Lunch | Dinner | Supper.
Output shape:
{
  "week": "14 - 20 Sep 2026",
  "days": [
    {"date": "2026-09-14", "weekday": "Mon", "theme": "Green Monday",
     "meals": {"Breakfast": [{"en": "...", "zh": "..."}], "Lunch": [...], "Dinner": [...], "Supper": [...]}}
  ]
}
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
    anchors = [w for w in words if w["text"] in day_names and w["x0"] < first_col_right]
    anchors.sort(key=lambda w: w["top"])
    if len(anchors) != 7:
        raise SystemExit(f"expected 7 day anchors, found {len(anchors)}: {[a['text'] for a in anchors]}")
    centers = [(a["top"] + a["bottom"]) / 2 for a in anchors]
    header_bottom = max((w["bottom"] for w in words if w["top"] < centers[0] - 60), default=0) + 2
    # the grid's vertical border rects end where the table ends; the disclaimer footer sits below that
    footer_top = max((r["bottom"] for r in page.rects if r["width"] < 2), default=page.height)
    bounds = []
    for i, c in enumerate(centers):
        top = header_bottom if i == 0 else (centers[i - 1] + c) / 2
        bot = footer_top - 2 if i == 6 else (c + centers[i + 1]) / 2
        bounds.append((top, bot))
    return anchors, bounds


def cell_lines(words, x0, x1, y0, y1):
    """Words inside a cell, grouped into visual lines. Returns list of (text, pixel_width)."""
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
        out.append((text.strip(), ln["words"][-1]["x1"] - ln["words"][0]["x0"]))
    return out


def group_zh(lines):
    """Chinese dishes are one per line; a 1-char line is a wrapped tail of the previous line."""
    dishes = []
    for text, width in lines:
        text = text.replace(" ", "")
        if not text:
            continue
        if dishes and len(text) <= 1:
            dishes[-1] = (dishes[-1][0] + text, dishes[-1][1])
        else:
            dishes.append((text, width))
    return dishes


CONNECTIVES = ("with", "and", "in", "of", "&")
TYPO_FIX = {"Marcaroni": "Macaroni", "Blamck": "Black"}
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


def group_en(lines, k):
    """Merge N visual lines into k dishes.
    A line starting lowercase is certainly a wrap; remaining merges go where the previous line is widest."""
    lines = [(t, w) for t, w in lines if t]
    n = len(lines)
    # certain wraps: next line starts lowercase, previous line ends with a connective,
    # or the line is a lone word that is not the cell's last line (e.g. "Shrimps", "Kudzu")
    merges = set()
    for i in range(1, n):
        prev, cur = lines[i - 1][0], lines[i][0]
        if cur[0].islower() or prev.split()[-1].lower() in CONNECTIVES \
                or (len(cur.split()) == 1 and i < n - 1):
            merges.add(i)
    dishes = []
    for i, (t, w) in enumerate(lines):
        if i in merges and dishes:
            dishes[-1] = (dishes[-1][0] + " " + t, w)
        else:
            dishes.append((t, w))
    if len(dishes) > k > 0:
        dishes = merge_by_width(dishes, len(dishes) - k)
    return dishes


def parse_page(page, day_names):
    cols = column_bounds(page)
    anchors, rows = row_bounds(page, day_names, cols[1])
    words = page.extract_words()
    days = []
    for (y0, y1) in rows:
        date_lines = [t for t, _ in cell_lines(words, cols[0], cols[1], y0, y1)]
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
    block = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\/")
    new, n = re.subn(r'(<script id="menu-data" type="application/json">\s*)(.*?)(\s*</script>)',
                     lambda m: m.group(1) + block + m.group(3), html, count=1, flags=re.S)
    if n:
        open(html_path, "w", encoding="utf-8").write(new)
        print(f"updated {html_path}")


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    pdf_path = sys.argv[1]
    out_path = sys.argv[2] if len(sys.argv) > 2 else "menu.json"

    m = re.search(r"(\d{1,2})\s*-\s*(\d{1,2})\s+([A-Za-z]{3})[a-z]*\s+(\d{4})", pdf_path)
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
                         and t not in EN_DAYS).strip() or THEME_DEFAULT.get(EN_DAYS[i], "")
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

    data = {"week": week_label, "days": days}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"wrote {out_path}")
    inject_into_app(data, os.path.join(os.path.dirname(os.path.abspath(out_path)), "index.html"))
    for d in days:
        print(f"\n{d['weekday']} {d['date']} [{d['theme']}]")
        for meal in MEALS:
            for it in d["meals"][meal]:
                print(f"  {meal:9s} {it['en']}  |  {it['zh']}")


if __name__ == "__main__":
    main()

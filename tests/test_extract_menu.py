import unittest
from types import SimpleNamespace
from unittest.mock import patch

import extract_menu


class WeekdayRegressionTests(unittest.TestCase):
    def test_row_detection_accepts_weekday_casing_and_chinese(self):
        for labels in (
            extract_menu.EN_DAYS,
            [day.upper() for day in extract_menu.EN_DAYS],
            [day.lower() for day in extract_menu.EN_DAYS],
            extract_menu.ZH_DAYS,
        ):
            with self.subTest(labels=labels):
                words = [
                    {"text": day, "x0": 20, "top": 100 + i * 100, "bottom": 120 + i * 100}
                    for i, day in enumerate(labels)
                ]
                # A weekday mentioned in a meal must not become a date-column anchor.
                words.append({"text": "MON", "x0": 200, "top": 100, "bottom": 120})
                page = SimpleNamespace(extract_words=lambda: list(reversed(words)), rects=[], height=800)
                anchors, rows = extract_menu.row_bounds(page, extract_menu.EN_DAYS, 150)
                self.assertEqual([word["text"] for word in anchors], list(labels))
                self.assertEqual(len(rows), 7)

    def test_incomplete_week_is_rejected(self):
        words = [
            {"text": day, "x0": 20, "top": 100 + i * 100, "bottom": 120 + i * 100}
            for i, day in enumerate(extract_menu.EN_DAYS[:-1])
        ]
        page = SimpleNamespace(extract_words=lambda: words, rects=[], height=800)
        with self.assertRaisesRegex(SystemExit, "expected 7 day anchors"):
            extract_menu.row_bounds(page, extract_menu.EN_DAYS, 150)

    def test_weekday_labels_are_excluded_from_themes(self):
        for labels in (
            extract_menu.EN_DAYS,
            [day.upper() for day in extract_menu.EN_DAYS],
            [day.lower() for day in extract_menu.EN_DAYS],
            extract_menu.ZH_DAYS,
        ):
            with self.subTest(labels=labels):
                days = [
                    {"date_lines": [day, f"{12 + i}/10", "*self serve"],
                     "cells": {meal: [] for meal in extract_menu.MEALS}}
                    for i, day in enumerate(labels)
                ]
                days[1]["date_lines"].append("Electronic show")
                with patch.object(extract_menu.pdfplumber, "open") as open_pdf:
                    open_pdf.return_value.__enter__.return_value.pages = [object(), object()]
                    with patch.object(extract_menu, "parse_page", side_effect=[days, days]):
                        week = extract_menu.parse_pdf("Together menu on 12 - 18 Oct 2026.pdf")
                self.assertEqual([day["theme"] for day in week["days"]],
                                 ["Green Monday", "Electronic show", "", "", "", "", ""])
                self.assertEqual([day["date"] for day in week["days"]],
                                 [f"2026-10-{day}" for day in range(12, 19)])


if __name__ == "__main__":
    unittest.main()

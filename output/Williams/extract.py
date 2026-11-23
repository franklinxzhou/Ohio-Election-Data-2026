#!/usr/bin/env python3
"""Extract Williams's unofficial countywide totals with Python 3 and pypdf."""

import csv
import re
from pathlib import Path

from pypdf import PdfReader

SOURCE = "Raw/Williams.pdf"
# PDF page and printed candidate labels, in D/R order.
RACES = {
    "us_senate": (3, "Sherrod Brown", "Jon Husted"),
    "governor": (1, "Amy Acton and David Pepper", "Vivek Ramaswamy and Robert A. McColley"),
    "attorney_general": (1, "John J. Kulewicz", "Keith Faber"),
    "auditor_of_state": (1, "Annette Blackwell", "Frank LaRose"),
    "secretary_of_state": (2, "Allison Russo", "Robert Sprague"),
    "treasurer_of_state": (2, "Seth Walsh", "Jay Edwards"),
    "supreme_court_2027_01_01": (2, "Marilyn Zayas", "Daniel R. Hawkins"),
    "supreme_court_2027_01_02": (3, "Jennifer Brunner", "Colleen O'Donnell"),
}


def extract(root, output):
    report = PdfReader(root / SOURCE)
    pages = {page: report.pages[page - 1].extract_text(extraction_mode="layout")
             for page in range(1, 4)}
    fields = ["county", "canvass_type", "source_file", "source_pages"]
    values = ["Williams", "unofficial", SOURCE, "1-3"]
    for race, (page, dem, rep) in RACES.items():
        for party, label in (("dem", dem), ("rep", rep)):
            pattern = (
                rf"^ *{re.escape(label)} +{party.upper()}"
                rf"(?: +[\d,]+ +[\d.]+%){{5}} +([\d,]+) +[\d.]+% *$"
            )
            total, = re.findall(pattern, pages[page], re.MULTILINE)
            fields.append(f"{race}_{party}")
            values.append(int(total.replace(",", "")))

    with output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(fields)
        writer.writerow(values)


if __name__ == "__main__":
    folder = Path(__file__).resolve().parent
    extract(folder.parents[1], folder / "county_votes.csv")

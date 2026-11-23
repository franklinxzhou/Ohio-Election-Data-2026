#!/usr/bin/env python3
"""Extract Sandusky's official countywide totals with Python 3 and pypdf."""

import csv
import re
from pathlib import Path

from pypdf import PdfReader

SOURCE = "Raw/Sandusky.PDF"
# Source page and displayed candidate labels, in D/R order.
RACES = {
    "us_senate": (5, "Sherrod Brown", "Jon Husted"),
    "governor": (2, "Amy Acton and David Pepper", "Vivek Ramaswamy and Robert A. McColley"),
    "attorney_general": (2, "John J. Kulewicz", "Keith Faber"),
    "auditor_of_state": (3, "Annette Blackwell", "Frank LaRose"),
    "secretary_of_state": (3, "Allison Russo", "Robert Sprague"),
    "treasurer_of_state": (3, "Seth Walsh", "Jay Edwards"),
    "supreme_court_2027_01_01": (4, "Marilyn Zayas", "Daniel R. Hawkins"),
    "supreme_court_2027_01_02": (4, "Jennifer Brunner", "Colleen O'Donnell"),
}


def extract(root, output):
    report = PdfReader(root / SOURCE)
    tables = {page: report.pages[page - 1].extract_text(extraction_mode="layout") for page in range(2, 6)}
    fields = ["county", "canvass_type", "source_file", "source_pages"]
    values = ["Sandusky", "official", SOURCE, "2-5"]
    for race, (page, dem, rep) in RACES.items():
        for party, label in (("dem", dem), ("rep", rep)):
            pattern = rf"^ *{party.title()} {re.escape(label)} {{2,}}([\d,]+) +\d+\.\d+%"
            total, = re.findall(pattern, tables[page], re.MULTILINE)
            fields.append(f"{race}_{party}")
            values.append(int(total.replace(",", "")))

    with output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(fields)
        writer.writerow(values)


if __name__ == "__main__":
    folder = Path(__file__).resolve().parent
    extract(folder.parents[1], folder / "county_votes.csv")

#!/usr/bin/env python3
"""Extract Mahoning's unofficial countywide totals with Python 3 and pypdf."""

import csv
import re
from pathlib import Path

from pypdf import PdfReader

SOURCE = "Raw/Mahoning.pdf"
# Source page and displayed candidate labels, in D/R order.
RACES = {
    "us_senate": (2, "Sherrod Brown", "Jon Husted"),
    "governor": (1, "Amy Acton and David Pepper", "Vivek Ramaswamy and Robert A."),
    "attorney_general": (1, "John J. Kulewicz", "Keith Faber"),
    "auditor_of_state": (1, "Annette Blackwell", "Frank LaRose"),
    "secretary_of_state": (1, "Allison Russo", "Robert Sprague"),
    "treasurer_of_state": (1, "Seth Walsh", "Jay Edwards"),
    "supreme_court_2027_01_01": (1, "Marilyn Zayas", "Daniel R. Hawkins"),
    "supreme_court_2027_01_02": (2, "Jennifer Brunner", "Colleen O'Donnell"),
}


def extract(root, output):
    report = PdfReader(root / SOURCE)
    tables = {page: report.pages[page - 1].extract_text(extraction_mode="layout") for page in (1, 2)}
    fields = ["county", "canvass_type", "source_file", "source_pages"]
    values = ["Mahoning", "unofficial", SOURCE, "1-2"]
    for race, (page, dem, rep) in RACES.items():
        for party, label in (("dem", dem), ("rep", rep)):
            pattern = rf"^ *{party.upper()} {re.escape(label)} {{2,}}([\d,]+) +\d+\.\d+% *$"
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

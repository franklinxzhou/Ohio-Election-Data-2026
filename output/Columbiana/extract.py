#!/usr/bin/env python3
"""Extract Columbiana's unofficial countywide totals with Python 3 and pypdf."""

import csv
import re
from pathlib import Path

from pypdf import PdfReader

SOURCE = "Raw/Columbiana.pdf"
# Source page and displayed candidate labels, in D/R order.
RACES = {
    "us_senate": (2, "Dem Sherrod Brown", "Rep Jon Husted"),
    "governor": (1, "Dem Amy Acton and David Pepper", "Rep Vivek Ramaswamy and Robert A."),
    "attorney_general": (1, "Dem John J. Kulewicz", "Rep Keith Faber"),
    "auditor_of_state": (1, "Dem Annette Blackwell", "Rep Frank LaRose"),
    "secretary_of_state": (1, "Dem Allison Russo", "Rep Robert Sprague"),
    "treasurer_of_state": (2, "Dem Seth Walsh", "Rep Jay Edwards"),
    "supreme_court_2027_01_01": (2, "Dem Marilyn Zayas", "Rep Daniel R. Hawkins"),
    "supreme_court_2027_01_02": (2, "Dem Jennifer Brunner", "Rep Colleen O’Donnell"),
}


def extract(root, output):
    report = PdfReader(root / SOURCE)
    tables = {page: report.pages[page - 1].extract_text(extraction_mode="layout") for page in (1, 2)}
    fields = ["county", "canvass_type", "source_file", "source_pages"]
    values = ["Columbiana", "unofficial", SOURCE, "1-2"]
    for race, (page, dem, rep) in RACES.items():
        for party, label in (("dem", dem), ("rep", rep)):
            pattern = rf"^ *{re.escape(label)} {{2,}}([\d,]+) +[\d.]+%"
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

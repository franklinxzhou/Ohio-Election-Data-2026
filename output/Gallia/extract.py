#!/usr/bin/env python3
"""Extract Gallia's countywide row from the Ohio SOS workbook with openpyxl."""

import csv
from pathlib import Path

from openpyxl import load_workbook

SOURCE = "output/Gallia/unofficial_state_canvass.xlsx"
RACES = {
    "us_senate": ("U.S. Congress", "Sherrod Brown", "Jon Husted"),
    "governor": ("Statewide Offices", "Amy Acton and David Pepper", "Vivek Ramaswamy and Robert A. McColley"),
    "attorney_general": ("Statewide Offices", "John J. Kulewicz", "Keith Faber"),
    "auditor_of_state": ("Statewide Offices", "Annette Blackwell", "Frank LaRose"),
    "secretary_of_state": ("Statewide Offices", "Allison Russo", "Robert Sprague"),
    "treasurer_of_state": ("Statewide Offices", "Seth Walsh", "Jay Edwards"),
    "supreme_court_2027_01_01": ("Supreme Court", "Marilyn Zayas", "Daniel R. Hawkins"),
    "supreme_court_2027_01_02": ("Supreme Court", "Jennifer Brunner", "Colleen O'Donnell"),
}


def extract(root, output):
    book = load_workbook(root / SOURCE, read_only=True, data_only=True)
    fields = ["county", "canvass_type", "source_file", "source_pages"]
    values = ["Gallia", "unofficial", SOURCE, ""]
    try:
        county = {}
        for title in dict.fromkeys(sheet for sheet, _, _ in RACES.values()):
            rows = iter(book[title].values)
            next(rows)
            headers = [" ".join(cell.split()) if isinstance(cell, str) else "" for cell in next(rows)]
            row, = [row for row in rows if row[0] == "Gallia"]
            county[title] = dict(zip(headers, row))
        for race, (sheet, dem, rep) in RACES.items():
            for party, symbol, name in (("dem", "D", dem), ("rep", "R", rep)):
                fields.append(f"{race}_{party}")
                values.append(int(county[sheet][f"{name} ({symbol})"]))
    finally:
        book.close()

    with output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(fields)
        writer.writerow(values)


if __name__ == "__main__":
    folder = Path(__file__).resolve().parent
    extract(folder.parents[1], folder / "county_votes.csv")

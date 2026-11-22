#!/usr/bin/env python3
"""Extract Pickaway's unofficial workbook totals by contest and party."""

import csv
from pathlib import Path

from openpyxl import load_workbook

SOURCE = "Raw/Pickaway.xlsx"
RACES = [
    ("us_senate", 8),
    ("governor", 1),
    ("attorney_general", 2),
    ("auditor_of_state", 3),
    ("secretary_of_state", 4),
    ("treasurer_of_state", 5),
    ("supreme_court_2027_01_01", 6),
    ("supreme_court_2027_01_02", 7),
]


def extract(root, folder):
    workbook = load_workbook(root / SOURCE, read_only=True, data_only=True)
    precincts = [row[0] for row in workbook["Totals"].iter_rows(
        min_row=2, min_col=2, max_col=2, values_only=True
    )]
    votes = {precinct: {} for precinct in precincts}
    sheets = []
    for race, number in RACES:
        sheet, = (s for s in workbook if s.title.startswith(f"{number} - "))
        sheets.append(sheet.title.rstrip())
        rows = sheet.values
        header = next(rows)
        parties = {}
        for party in ("Dem", "Rep"):
            index, = (i for i, label in enumerate(header) if label and label.endswith(f"_({party})"))
            parties[f"{race}_{party.lower()}"] = index
        for row in rows:
            votes[row[1]].update({field: row[index] for field, index in parties.items()})
    workbook.close()

    links = {}
    notes = (folder / "precinct_merges_splits.txt").read_text()
    for line in notes.split("\nCrosswalk rows\n", 1)[1].splitlines():
        name, status, ids, _ = line.split(" | ")
        links[name] = ids, status

    fields = [f"{race}_{party}" for race, _ in RACES for party in ("dem", "rep")]
    with (folder / "precinct_votes.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow([
            "county", "precinct_code", "precinct_name", "canvass_type", "source_file",
            "source_pages", "graph_node_ids", "graph_match_status", *fields,
        ])
        for precinct, counts in votes.items():
            code, name = precinct.split(" ", 1)
            ids, status = links[name]
            writer.writerow([
                "Pickaway", code, name, "unofficial", SOURCE, "; ".join(sheets),
                ids, status, *(counts[field] for field in fields),
            ])


if __name__ == "__main__":
    folder = Path(__file__).resolve().parent
    extract(folder.parents[1], folder)

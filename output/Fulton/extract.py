#!/usr/bin/env python3
"""Extract Fulton's unofficial precinct workbook with Python 3 and openpyxl."""

import csv
import json
from pathlib import Path
from warnings import filterwarnings

from openpyxl import load_workbook

SOURCE = "Raw/Fulton.xlsx"
# Sheet name and candidate labels in D/R order.
RACES = {
    "us_senate": ("9", "Sherrod Brown", "Jon Husted"),
    "governor": ("2", "Amy Acton and David Pepper", "Vivek Ramaswamy and Robert A. McColley"),
    "attorney_general": ("3", "John J. Kulewicz", "Keith Faber"),
    "auditor_of_state": ("4", "Annette Blackwell", "Frank LaRose"),
    "secretary_of_state": ("5", "Allison Russo", "Robert Sprague"),
    "treasurer_of_state": ("6", "Seth Walsh", "Jay Edwards"),
    "supreme_court_2027_01_01": ("7", "Marilyn Zayas", "Daniel R. Hawkins"),
    "supreme_court_2027_01_02": ("8", "Jennifer Brunner", "Colleen O'Donnell"),
}
FIELDS = ["county", "precinct_code", "precinct_name", "canvass_type", "source_file",
          "source_pages", "graph_node_ids", "graph_match_status"]
FIELDS += [f"{race}_{party}" for race in RACES for party in ("dem", "rep")]


def read_table(sheet, names):
    rows = iter(sheet.values)
    next(rows)  # Contest title.
    choices, headers = next(rows), next(rows)
    columns = [choices.index(name) + 3 for name in names]
    if any(headers[index] != "Total Votes" for index in columns):
        raise ValueError(f"Unexpected candidate columns in sheet {sheet.title}")
    return {row[0]: tuple(int(row[index]) for index in columns)
            for row in rows if row[0] and row[0] != "Total:"}


def extract(root, output):
    filterwarnings("ignore", message="Workbook contains no default style", module="openpyxl")
    book = load_workbook(root / SOURCE, read_only=True, data_only=True)
    try:
        tables = [read_table(book[sheet], (dem, rep)) for sheet, dem, rep in RACES.values()]
    finally:
        book.close()

    graph = json.loads((root / "OH_pct20.json").read_text(encoding="utf-8"))
    by_name = {}
    for node in graph["nodes"]:
        if node["COUNTY"] == "FULTON":
            members = node["ORIG_NAME"].split(",")
            status = "combined_node" if len(members) > 1 else "exact"
            for member in members:
                by_name[member.removesuffix("_FULTON")] = (node["id"], status)

    with output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(FIELDS)
        for name in tables[1]:
            node_id, status = by_name[name]
            writer.writerow(["Fulton", "", name, "unofficial", SOURCE, "", node_id, status,
                             *(count for table in tables for count in table[name])])


if __name__ == "__main__":
    folder = Path(__file__).resolve().parent
    extract(folder.parents[1], folder / "precinct_votes.csv")

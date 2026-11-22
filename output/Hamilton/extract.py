#!/usr/bin/env python3
"""Extract Hamilton's unofficial precinct workbook with Python 3 and openpyxl."""

import csv
import json
from collections import defaultdict
from pathlib import Path
from warnings import filterwarnings

from openpyxl import load_workbook

SOURCE = "Raw/Hamilton.xlsx"
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


BOUNDARY_HEADER = "Code and precinct | Status | Graph IDs | Historical precincts and area shares"
PREFIXES = {
    "ADDY": "ADDYSTON", "AMBER": "AMBERLEY", "AND": "ANDERSON", "ARLN": "ARLINGTON HGTS",
    "BLUE": "BLUE ASH", "CHEV": "CHEVIOT", "CIN": "CINCINNATI", "COLE": "COLERAIN",
    "COLUM": "COLUMBIA", "CROSB": "CROSBY", "DR PK": "DEER PARK", "ELMW": "ELMWOOD",
    "EVEN": "EVENDALE", "FAIRFX": "FAIRFAX", "FR PK": "FOREST PARK", "GLEN": "GLENDALE",
    "GOLF": "GOLF MANOR", "GR HL": "GREENHILLS", "IND HLL": "INDIAN HILL",
    "LIN HT": "LINCOLN HGTS", "LOCK": "LOCKLAND", "LOVE": "LOVELAND", "MADRA": "MADEIRA",
    "MARMT": "MARIEMONT", "MIAMI": "MIAMI TWP", "MONT": "MONTGOMERY", "MTHY": "MT HEALTHY",
    "NCH": "NO COLL HILL", "NEWT": "NEWTOWN", "NO BEND": "NORTH BEND", "NORW": "NORWOOD",
    "READ": "READING", "SHAR": "SHARONVILLE", "SILVT": "SILVERTON", "SPDALE": "SPRINGDALE",
    "SPFLD": "SPRINGFIELD", "ST BN": "ST BERNARD", "SYCAM": "SYCAMORE", "SYMM": "SYMMES",
    "TER PK": "TERRACE PARK", "WHWTR": "WHITEWATER", "WOOD": "WOODLAWN", "WYOM": "WYOMING",
}


def graph_key(code, name):
    place, suffix = name.rsplit(" ", 1)
    if place == "HARR":
        place = "HARR TWP" if code.startswith("76") else "HARRISON"
    return f"{PREFIXES.get(place, place)} {suffix}"


def graph_members(root):
    graph = json.loads((root / "OH_pct20.json").read_text(encoding="utf-8"))
    for node in graph["nodes"]:
        if node["COUNTY"] == "HAMILTON":
            members = tuple(member.removesuffix("_HAMILTON") for member in node["ORIG_NAME"].split(","))
            yield node["id"], members, node["ENACTED_LOWER"]


def read_table(sheet, names):
    rows = iter(sheet.values)
    next(rows)  # Contest title.
    choices, headers = next(rows), next(rows)
    columns = [choices.index(name) + 2 for name in names]
    if any(headers[index] != "Total Votes" for index in columns):
        raise ValueError(f"Unexpected candidate columns in sheet {sheet.title}")
    return {row[0]: tuple(int(row[index]) for index in columns)
            for row in rows if row[0] and row[0] != "Total:"}


def read_votes(source):
    filterwarnings("ignore", message="Workbook contains no default style", module="openpyxl")
    book = load_workbook(source, read_only=True, data_only=True)
    try:
        return [read_table(book[sheet], (dem, rep)) for sheet, dem, rep in RACES.values()]
    finally:
        book.close()

def extract(root, output):
    tables = read_votes(root / SOURCE)
    by_name = defaultdict(list)
    for node_id, members, _ in graph_members(root):
        for label in members:
            by_name[label].append((node_id, len(members)))
    notes = (output.parent / "precinct_merges_splits.txt").read_text(encoding="utf-8")
    _, _, records = notes.partition(BOUNDARY_HEADER + "\n")
    overrides = {}
    for line in records.splitlines():
        precinct, status, nodes, _ = line.split(" | ", 3)
        overrides[precinct] = (nodes, status)

    with output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(FIELDS)
        for precinct in tables[1]:
            code, name = precinct.split(" ", 1)
            if precinct in overrides:
                nodes, status = overrides[precinct]
            else:
                key = graph_key(code, name)
                matches = sorted(by_name[key])
                nodes = ";".join(str(node_id) for node_id, _ in matches)
                if len(matches) > 1:
                    status = "split_nodes"
                elif matches[0][1] > 1:
                    status = "combined_node"
                else:
                    status = "exact" if key == name else "normalized"
            writer.writerow(["Hamilton", code, name, "unofficial", SOURCE, "", nodes, status,
                             *(count for table in tables for count in table[precinct])])


if __name__ == "__main__":
    folder = Path(__file__).resolve().parent
    extract(folder.parents[1], folder / "precinct_votes.csv")

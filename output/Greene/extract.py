#!/usr/bin/env python3
"""Extract Greene's unofficial precinct workbook with Python 3 and openpyxl."""

import csv
import json
from collections import defaultdict
from pathlib import Path

from openpyxl import load_workbook

SOURCE = "Raw/Greene.xlsx"
RACES = {
    "us_senate": 8,
    "governor": 1,
    "attorney_general": 2,
    "auditor_of_state": 3,
    "secretary_of_state": 4,
    "treasurer_of_state": 5,
    "supreme_court_2027_01_01": 6,
    "supreme_court_2027_01_02": 7,
}
FIELDS = ["county", "precinct_code", "precinct_name", "canvass_type", "source_file",
          "source_pages", "graph_node_ids", "graph_match_status"]
FIELDS += [f"{race}_{party}" for race in RACES for party in ("dem", "rep")]
BOUNDARY_HEADER = "Code and precinct | Status | Graph IDs | Historical precincts and area shares"


def graph_members(root):
    graph = json.loads((root / "OH_pct20.json").read_text(encoding="utf-8"))
    for node in graph["nodes"]:
        if node["COUNTY"] == "GREENE":
            names = tuple(member.removesuffix("_GREENE") for member in node["ORIG_NAME"].split(","))
            yield node["id"], names, node["ENACTED_LOWER"]


def read_votes(source):
    book = load_workbook(source, read_only=True, data_only=True)
    try:
        tables = []
        for number in RACES.values():
            sheet, = (sheet for sheet in book if sheet.title.startswith(f"{number} - "))
            rows = iter(sheet.values)
            headers = next(rows)
            columns = []
            for party in ("DEM", "REP"):
                column, = (i for i, label in enumerate(headers) if label and label.endswith(f"({party})"))
                columns.append(column)
            tables.append({tuple(row[1].split(" ", 1)): tuple(int(row[i]) for i in columns)
                           for row in rows if row[1]})
        return tables
    finally:
        book.close()


def extract(root, output):
    tables = read_votes(root / SOURCE)
    by_code = defaultdict(list)
    for node_id, members, _ in graph_members(root):
        for member in members:
            _, code = member.rsplit(" ", 1)
            by_code[code].append((node_id, len(members)))
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
            code, name = precinct
            label = f"{code} {name}"
            if label in overrides:
                nodes, status = overrides[label]
            else:
                matches = sorted(by_code[code])
                nodes = ";".join(str(node_id) for node_id, _ in matches)
                status = "split_nodes" if len(matches) > 1 else "combined_node" if matches[0][1] > 1 else "normalized"
            writer.writerow(["Greene", code, name, "unofficial", SOURCE, "", nodes, status,
                             *(count for table in tables for count in table[precinct])])


if __name__ == "__main__":
    folder = Path(__file__).resolve().parent
    extract(folder.parents[1], folder / "precinct_votes.csv")

#!/usr/bin/env python3
"""Extract Franklin's official precinct workbook with Python 3 and openpyxl."""

import csv
import json
import re
from collections import defaultdict
from pathlib import Path

from openpyxl import load_workbook

SOURCE = "Raw/Franklin.xlsx"
SHEET = "25ElectionResultsCSV"
RACES = {
    "us_senate": "For U.S. Senator (UTE 1-3-29) -",
    "governor": "For Governor and Lieutenant Governor -",
    "attorney_general": "For Attorney General -",
    "auditor_of_state": "For Auditor of State -",
    "secretary_of_state": "For Secretary of State -",
    "treasurer_of_state": "For Treasurer of State -",
    "supreme_court_2027_01_01": "For Justice of the Supreme Court (1-1-27) -",
    "supreme_court_2027_01_02": "For Justice of the Supreme Court (1-2-27) -",
}
PARTIES = ("Dem", "Rep")
FIELDS = ["county", "precinct_code", "precinct_name", "canvass_type", "source_file",
          "source_pages", "graph_node_ids", "graph_match_status"]
FIELDS += [f"{race}_{party.lower()}" for race in RACES for party in PARTIES]
BOUNDARY_HEADER = "Code and precinct | Status | Graph IDs | Historical precincts and area shares"
PREFIXES = {
    "COLUMBUS": "COLS", "CANAL WINCHESTER": "CANAL WIN", "DUBLIN": "DUB",
    "GAHANNA": "GAH", "HILLIARD": "HILL", "REYNOLDSBURG": "REYNS",
    "UPPER ARLINGTON": "UA", "WORTHINGTON": "WORTH",
}


def graph_key(name):
    prefix, suffix = re.fullmatch(r"(.+?)( \d+-[A-Z]+|-[A-Z]+)", name).groups()
    return PREFIXES.get(prefix, prefix) + suffix


def graph_members(root):
    graph = json.loads((root / "OH_pct20.json").read_text(encoding="utf-8"))
    for node in graph["nodes"]:
        if node["COUNTY"] == "FRANKLIN":
            members = tuple(member.removesuffix("_FRANKLIN") for member in node["ORIG_NAME"].split(","))
            yield node["id"], members, node["ENACTED_LOWER"]


def read_precincts(source):
    book = load_workbook(source, read_only=True, data_only=True)
    try:
        rows = iter(book[SHEET].values)
        contests, parties = next(rows), next(rows)
        next(rows)  # Candidate display labels.
        lookup = {(contest, party): index for index, (contest, party) in enumerate(zip(contests, parties))
                  if contest in RACES.values() and party in PARTIES}
        columns = [lookup[contest, party] for contest in RACES.values() for party in PARTIES]
        return [(row[1], row[2], tuple(int(row[i]) for i in columns))
                for row in rows if row[1] not in (None, "ZZZ")]
    finally:
        book.close()


def extract(root, output):
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
        for code, name, votes in read_precincts(root / SOURCE):
            label = f"{code} {name}"
            if label in overrides:
                nodes, status = overrides[label]
            else:
                key = graph_key(name)
                matches = sorted(by_name[key])
                nodes = ";".join(str(node_id) for node_id, _ in matches)
                if len(matches) > 1:
                    status = "split_nodes"
                elif matches[0][1] > 1:
                    status = "combined_node"
                else:
                    status = "exact" if name == key else "normalized"
            writer.writerow(["Franklin", code, name, "official", SOURCE, "", nodes, status, *votes])


if __name__ == "__main__":
    folder = Path(__file__).resolve().parent
    extract(folder.parents[1], folder / "precinct_votes.csv")

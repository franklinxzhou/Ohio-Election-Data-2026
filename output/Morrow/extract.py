#!/usr/bin/env python3
"""Extract Democratic and Republican precinct totals from Morrow's SOVC."""

import csv
import json
import re
from collections import defaultdict
from pathlib import Path

from pypdf import PdfReader

SOURCE = "Raw/Morrow.pdf"
# Physical pages, numeric row width, then zero-based D and R columns.
RACES = [
    ("us_senate", 12, 13, 11, 0, 1),
    ("governor", 2, 3, 12, 0, 2),
    ("attorney_general", 4, 5, 12, 1, 0),
    ("auditor_of_state", 4, 5, 12, 6, 7),
    ("secretary_of_state", 6, 7, 7, 1, 2),
    ("treasurer_of_state", 8, 9, 12, 1, 0),
    ("supreme_court_2027_01_01", 8, 9, 12, 7, 6),
    ("supreme_court_2027_01_02", 10, 11, 6, 0, 1),
]
ROW = re.compile(r"^\s*(\S(?:.*?\S)?) {2,}([\d,]+(?: +[\d,]+)*)\s*$")


def graph_name(name):
    name = name.upper().replace(" VLG", " VILLAGE")
    if name.startswith(("BENNINGTON ", "CHESTER ", "CONGRESS ")):
        directions = {" E": " EAST", " W": " WEST"}
        name = name[:-2] + directions[name[-2:]]
    return name


def extract(root, output):
    pdf = PdfReader(root / SOURCE)
    pages = {
        i: pdf.pages[i - 1].extract_text(extraction_mode="layout").splitlines()
        for i in range(2, 14)
    }
    votes, source_pages = defaultdict(dict), defaultdict(set)
    for race, first, last, width, dem, rep in RACES:
        for page in range(first, last + 1):
            for line in pages[page]:
                if not (match := ROW.fullmatch(line)):
                    continue
                name, numbers = match.groups()
                values = numbers.replace(",", "").split()
                if name == "Totals" or len(values) != width:
                    continue
                votes[name][f"{race}_dem"] = int(values[dem])
                votes[name][f"{race}_rep"] = int(values[rep])
                source_pages[name].add(page)

    graph = json.loads((root / "OH_pct20.json").read_text(encoding="utf-8"))
    matches = {}
    for node in graph["nodes"]:
        if node["COUNTY"] == "MORROW":
            members = node["ORIG_NAME"].split(",")
            for member in members:
                matches[member.removesuffix("_MORROW")] = node["id"], len(members) > 1

    fields = [f"{race}_{party}" for race, *_ in RACES for party in ("dem", "rep")]
    with output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow([
            "county", "precinct_code", "precinct_name", "canvass_type", "source_file",
            "source_pages", "graph_node_ids", "graph_match_status", *fields,
        ])
        for name, counts in votes.items():
            key = graph_name(name)
            node, combined = matches[key]
            status = "combined_node" if combined else ("exact" if key == name.upper() else "normalized")
            writer.writerow([
                "Morrow", "", name, "official", SOURCE, ",".join(map(str, sorted(source_pages[name]))),
                node, status, *(counts[field] for field in fields),
            ])


if __name__ == "__main__":
    folder = Path(__file__).resolve().parent
    extract(folder.parents[1], folder / "precinct_votes.csv")

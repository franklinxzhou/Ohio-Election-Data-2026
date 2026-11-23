#!/usr/bin/env python3
"""Extract Washington official D/R precinct totals using pypdf."""

import csv
import json
import re
from collections import defaultdict
from pathlib import Path

from pypdf import PdfReader

SOURCE = "Raw/Washington.pdf"
RACES = [
    ("us_senate", "Sherrod Brown", "Jon Husted"),
    ("governor", "Amy Acton and David Pepper", "Vivek Ramaswamy and Robert A."),
    ("attorney_general", "John J. Kulewicz", "Keith Faber"),
    ("auditor_of_state", "Annette Blackwell", "Frank LaRose"),
    ("secretary_of_state", "Allison Russo", "Robert Sprague"),
    ("treasurer_of_state", "Seth Walsh", "Jay Edwards"),
    ("supreme_court_2027_01_01", "Marilyn Zayas", "Daniel R. Hawkins"),
    ("supreme_court_2027_01_02", "Jennifer Brunner", "Colleen O'Donnell"),
]
FIELDS = {
    candidate: f"{race}_{party}"
    for race, dem, rep in RACES for party, candidate in (("dem", dem), ("rep", rep))
}
PRECINCT = re.compile(r"^\s*(\d{4}) ([^\n]+)$", re.MULTILINE)
CANDIDATE = re.compile(
    r"(?<!\S)(" + "|".join(map(re.escape, FIELDS)) + r") +(?:\([DR]\) +)?([\d,]+) +[\d.]+%",
)

ALIASES = {
    "BEVERLY/WATERFORD": "BEV / WATERFORD",
    "LOWELL/ADAMS": "LOWELL / ADAMS",
    "MATAMORAS/GRANDVIEW": "MATAMORAS / GRANDVIEW",
    "WARREN NORTH EAST": "WARREN NE",
    "WARREN NORTH WEST": "WARREN NW",
}


def graph_name(name):
    name = name.upper()
    if name in ALIASES:
        return ALIASES[name]
    for full, short in (("MARIETTA", "MTTA"), ("MUSKINGUM", "MUSK")):
        if name.startswith((f"{full} EAST", f"{full} WEST")):
            return name.replace(full, short, 1)
    return name


def read_votes(source):
    votes, pages = defaultdict(dict), defaultdict(set)
    for number, page in enumerate(PdfReader(source).pages, 1):
        layout = page.extract_text(extraction_mode="layout")
        code, name = PRECINCT.search(layout).groups()
        precinct = code, name.strip()
        for candidate, count in CANDIDATE.findall(layout):
            field = FIELDS[candidate]
            if field in votes[precinct]:
                raise ValueError(f"Duplicate {field} for precinct {code}")
            votes[precinct][field] = int(count.replace(",", ""))
            pages[precinct].add(number)
    return votes, pages


def write_csv(folder, votes, pages):
    graph = json.loads((folder.parents[1] / "OH_pct20.json").read_text())
    crosswalk = {}
    for node in graph["nodes"]:
        if node["COUNTY"] == "WASHINGTON":
            members = node["ORIG_NAME"].split(",")
            for member in members:
                crosswalk[member.removesuffix("_WASHINGTON")] = node["id"], len(members) > 1

    with (folder / "precinct_votes.csv").open("w", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow([
            "county", "precinct_code", "precinct_name", "canvass_type", "source_file",
            "source_pages", "graph_node_ids", "graph_match_status", *FIELDS.values(),
        ])
        for code, name in sorted(votes):
            precinct = code, name
            source_pages = ",".join(map(str, sorted(pages[precinct])))
            key = graph_name(name)
            node_id, combined = crosswalk[key]
            status = "combined_node" if combined else "exact" if key == name.upper() else "normalized"
            writer.writerow([
                "Washington", code, name, "official", SOURCE, source_pages, node_id, status,
                *(votes[precinct][field] for field in FIELDS.values()),
            ])


if __name__ == "__main__":
    folder = Path(__file__).resolve().parent
    write_csv(folder, *read_votes(folder.parents[1] / SOURCE))

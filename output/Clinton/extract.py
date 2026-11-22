#!/usr/bin/env python3
"""Extract Clinton's official precinct returns with Python 3 and pypdf."""

import csv
import json
import re
from collections import defaultdict
from pathlib import Path

from pypdf import PdfReader

SOURCE = "Raw/Clinton.pdf"
RACES = {
    "us_senate": ("Sherrod Brown", "Jon Husted"),
    "governor": ("Amy Acton and David Pepper", "Vivek Ramaswamy and Robert A. McColley"),
    "attorney_general": ("John J. Kulewicz", "Keith Faber"),
    "auditor_of_state": ("Annette Blackwell", "Frank LaRose"),
    "secretary_of_state": ("Allison Russo", "Robert Sprague"),
    "treasurer_of_state": ("Seth Walsh", "Jay Edwards"),
    "supreme_court_2027_01_01": ("Marilyn Zayas", "Daniel R. Hawkins"),
    "supreme_court_2027_01_02": ("Jennifer Brunner", "Colleen O'Donnell"),
}
FIELDS = ["county", "precinct_code", "precinct_name", "canvass_type", "source_file",
          "source_pages", "graph_node_ids", "graph_match_status"]
FIELDS += [f"{race}_{party}" for race in RACES for party in ("dem", "rep")]
CANDIDATES = [name for pair in RACES.values() for name in pair]
PRECINCT = re.compile(r"Precinct (\d+) (.+)")
VOTE = re.compile(r"(" + "|".join(map(re.escape, CANDIDATES)) + r") {2,}([\d,]+) +\d")


def read_precincts(source):
    votes = {}
    pages = defaultdict(set)
    precinct = None
    for page, contents in enumerate(PdfReader(source).pages, 1):
        for line in contents.extract_text(extraction_mode="layout").splitlines():
            line = line.strip()
            if line == "All Precincts":
                return votes, pages
            if match := PRECINCT.fullmatch(line):
                precinct = match.groups()
                votes[precinct] = {}
            elif precinct and (match := VOTE.match(line)):
                candidate, count = match.groups()
                if candidate in votes[precinct]:
                    raise ValueError(f"Duplicate {candidate} count for {precinct}")
                votes[precinct][candidate] = int(count.replace(",", ""))
                pages[precinct].add(page)
    raise ValueError("Missing All Precincts heading")


def extract(root, output):
    votes, pages = read_precincts(root / SOURCE)
    graph = json.loads((root / "OH_pct20.json").read_text(encoding="utf-8"))
    by_name = {}
    for node in graph["nodes"]:
        if node["COUNTY"] != "CLINTON":
            continue
        members = node["ORIG_NAME"].split(",")
        status = "combined_node" if len(members) > 1 else "exact"
        for member in members:
            by_name[member.removesuffix("_CLINTON")] = (node["id"], status)

    with output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(FIELDS)
        for precinct, counts in votes.items():
            code, name = precinct
            node_id, status = by_name[name]
            writer.writerow(["Clinton", code, name, "official", SOURCE,
                             ",".join(map(str, sorted(pages[precinct]))), node_id, status,
                             *(counts[candidate] for candidate in CANDIDATES)])


if __name__ == "__main__":
    folder = Path(__file__).resolve().parent
    extract(folder.parents[1], folder / "precinct_votes.csv")

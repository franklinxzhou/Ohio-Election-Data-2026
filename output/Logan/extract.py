#!/usr/bin/env python3
"""Extract Logan's official statewide precinct vote totals with pypdf."""

import csv
import json
import re
from collections import defaultdict
from pathlib import Path

from pypdf import PdfReader

SOURCE = "Raw/Logan.pdf"
RACES = [
    ("us_senate", "Sherrod Brown", "Jon Husted"),
    ("governor", "Amy Acton and David Pepper", "Vivek Ramaswamy and Robert A. McColley"),
    ("attorney_general", "John J. Kulewicz", "Keith Faber"),
    ("auditor_of_state", "Annette Blackwell", "Frank LaRose"),
    ("secretary_of_state", "Allison Russo", "Robert Sprague"),
    ("treasurer_of_state", "Seth Walsh", "Jay Edwards"),
    ("supreme_court_2027_01_01", "Marilyn Zayas", "Daniel R. Hawkins"),
    ("supreme_court_2027_01_02", "Jennifer Brunner", "Colleen O'Donnell"),
]
FIELDS = {
    f"{party.upper()} {candidate}": f"{race}_{party}"
    for race, dem, rep in RACES for party, candidate in (("dem", dem), ("rep", rep))
}
PRECINCT = re.compile(r"^November 3, 2026 +Logan County\s+([^\n]+)", re.MULTILINE)
CANDIDATE = re.compile(r"^((?:DEM|REP) .+?) {2,}([\d,]+) +\d", re.MULTILINE)
DIRECTIONS = {"NORTH": "N", "SOUTH": "S", "WEST": "W", "SOUTHEAST": "SE"}


def historical_name(name):
    key = name.upper()
    if key == "MIAMI/QUINCY":
        return "MIAMI"
    prefix, suffix = key.rsplit(" ", 1) if " " in key else ("", key)
    if prefix in {"JEFFERSON", "STOKES", "WASHINGTON"}:
        return f"{prefix} {DIRECTIONS[suffix]}"
    return key


def extract(root, output):
    votes, pages = defaultdict(dict), defaultdict(set)
    for number, page in enumerate(PdfReader(root / SOURCE).pages, 1):
        text = page.extract_text(extraction_mode="layout")
        name = PRECINCT.search(text)[1].strip()
        for label, count in CANDIDATE.findall(text):
            if field := FIELDS.get(label):
                if field in votes[name]:
                    raise ValueError(f"Duplicate {field} for {name}")
                votes[name][field] = int(count.replace(",", ""))
                pages[name].add(number)

    graph = json.loads((root / "OH_pct20.json").read_text(encoding="utf-8"))
    matches = {}
    for node in graph["nodes"]:
        if node["COUNTY"] == "LOGAN":
            members = node["ORIG_NAME"].split(",")
            for member in members:
                matches[member.removesuffix("_LOGAN")] = node["id"], len(members) > 1

    with output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow([
            "county", "precinct_code", "precinct_name", "canvass_type", "source_file",
            "source_pages", "graph_node_ids", "graph_match_status", *FIELDS.values(),
        ])
        for name, counts in votes.items():
            key = historical_name(name)
            node, combined = matches[key]
            status = "combined_node" if combined else ("exact" if key == name.upper() else "normalized")
            writer.writerow([
                "Logan", "", name, "official", SOURCE, ",".join(map(str, sorted(pages[name]))),
                node, status, *(counts[field] for field in FIELDS.values()),
            ])


if __name__ == "__main__":
    folder = Path(__file__).resolve().parent
    extract(folder.parents[1], folder / "precinct_votes.csv")

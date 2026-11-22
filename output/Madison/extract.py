#!/usr/bin/env python3
"""Extract Madison County's official statewide precinct candidate totals."""

import csv
import json
import re
from collections import defaultdict
from pathlib import Path

from pypdf import PdfReader

SOURCE = "Raw/Madison.pdf"
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
    (candidate if race == "governor" else f"{party.title()} {candidate}"): f"{race}_{party}"
    for race, dem, rep in RACES for party, candidate in (("dem", dem), ("rep", rep))
}
PRECINCT = re.compile(r"^November 3, 2026 +Madison County\s+(\d{4}) - ([^\n]+)", re.MULTILINE)
CANDIDATE = re.compile(r"^([^\n]+?) {2,}([\d,]+) +\d+\.\d+%", re.MULTILINE)


ALIASES = {
    "MONROE/PIKE": "MONROE / PIKE",
    "W JEFFERSON A": "WEST JEFFERSON A",
    "JEFFERSON TOWNSHIP B": "JEFFERSON TWP B",
    "PAINT/RANGE/STOKES": "PAINT / RANGE / STOKES",
    "MT. STERLING": "MT STERLING",
}


def extract(root, output):
    votes, pages = defaultdict(dict), defaultdict(set)
    for number, page in enumerate(PdfReader(root / SOURCE).pages, 1):
        layout = page.extract_text(extraction_mode="layout")
        code, name = PRECINCT.search(layout).groups()
        key = code, name.strip()
        for label, count in CANDIDATE.findall(layout):
            if field := FIELDS.get(label):
                if field in votes[key]:
                    raise ValueError(f"Duplicate {field} for {key}")
                votes[key][field] = int(count.replace(",", ""))
                pages[key].add(number)

    graph = json.loads((root / "OH_pct20.json").read_text(encoding="utf-8"))
    matches = {}
    for node in graph["nodes"]:
        if node["COUNTY"] == "MADISON":
            members = node["ORIG_NAME"].split(",")
            for member in members:
                matches[member.removesuffix("_MADISON")] = node["id"], len(members) > 1

    with output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow([
            "county", "precinct_code", "precinct_name", "canvass_type", "source_file",
            "source_pages", "graph_node_ids", "graph_match_status", *FIELDS.values(),
        ])
        for code, name in sorted(votes):
            key = code, name
            historical = ALIASES.get(name.upper(), name.upper())
            node_id, combined = matches[historical]
            status = "combined_node" if combined else ("exact" if name.upper() == historical else "normalized")
            writer.writerow([
                "Madison", code, name, "official", SOURCE, ",".join(map(str, sorted(pages[key]))),
                node_id, status, *(votes[key][field] for field in FIELDS.values()),
            ])


if __name__ == "__main__":
    folder = Path(__file__).resolve().parent
    extract(folder.parents[1], folder / "precinct_votes.csv")

#!/usr/bin/env python3
"""Extract Noble's official statewide precinct vote totals with pypdf."""

import csv
import json
import re
from collections import defaultdict
from pathlib import Path

from pypdf import PdfReader

SOURCE = "Raw/Noble.pdf"
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
    f"{party.title()} {candidate}": f"{race}_{party}"
    for race, dem, rep in RACES for party, candidate in (("dem", dem), ("rep", rep))
}
PRECINCT = re.compile(r"^November 3, 2026 +Noble County\n(\d{1,2}) ([^\n]+)", re.MULTILINE)
CANDIDATE = re.compile(r"^((?:Dem|Rep) .+?) {2,}([\d,]+) +[\d.]+%", re.MULTILINE)


def extract(root, output):
    votes, pages = defaultdict(dict), defaultdict(set)
    for number, page in enumerate(PdfReader(root / SOURCE).pages, 1):
        text = page.extract_text(extraction_mode="layout")
        code, name = PRECINCT.search(text).groups()
        precinct = code, name.strip()
        for label, count in CANDIDATE.findall(text):
            if field := FIELDS.get(label):
                if field in votes[precinct]:
                    raise ValueError(f"Duplicate {field} for {name}")
                votes[precinct][field] = int(count.replace(",", ""))
                pages[precinct].add(number)

    graph = json.loads((root / "OH_pct20.json").read_text(encoding="utf-8"))
    matches = {}
    for node in graph["nodes"]:
        if node["COUNTY"] == "NOBLE":
            members = node["ORIG_NAME"].split(",")
            for member in members:
                matches[member.removesuffix("_NOBLE")] = node["id"], len(members) > 1

    with output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow([
            "county", "precinct_code", "precinct_name", "canvass_type", "source_file",
            "source_pages", "graph_node_ids", "graph_match_status", *FIELDS.values(),
        ])
        for precinct, counts in votes.items():
            code, name = precinct
            node, combined = matches[name.upper()]
            status = "combined_node" if combined else "exact"
            writer.writerow([
                "Noble", code, name, "official", SOURCE, ",".join(map(str, sorted(pages[precinct]))),
                node, status, *(counts[field] for field in FIELDS.values()),
            ])


if __name__ == "__main__":
    folder = Path(__file__).resolve().parent
    extract(folder.parents[1], folder / "precinct_votes.csv")

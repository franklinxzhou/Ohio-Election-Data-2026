#!/usr/bin/env python3
"""Extract Ottawa's official statewide precinct vote totals with pypdf."""

import csv
import json
import re
from collections import defaultdict
from pathlib import Path

from pypdf import PdfReader

SOURCE = "Raw/Ottawa.pdf"
RACES = [
    ("us_senate", "Sherrod Brown", "Jon Husted"),
    ("governor", "Amy Acton and David Pepper", "Vivek Ramaswamy and Robert A."),
    ("attorney_general", "John J. Kulewicz", "Keith Faber"),
    ("auditor_of_state", "Annette Blackwell", "Frank LaRose"),
    ("secretary_of_state", "Allison Russo", "Robert Sprague"),
    ("treasurer_of_state", "Seth Walsh", "Jay Edwards"),
    ("supreme_court_2027_01_01", "Marilyn Zayas", "Daniel R. Hawkins"),
    ("supreme_court_2027_01_02", "Jennifer Brunner", "Colleen O’Donnell"),
]
FIELDS = {
    f"{party.title()} {candidate}": f"{race}_{party}"
    for race, dem, rep in RACES for party, candidate in (("dem", dem), ("rep", rep))
}
PRECINCT = re.compile(r"^November 3, 2026 +Ottawa County\n([^\n]+)", re.MULTILINE)
CANDIDATE = re.compile(r"^((?:Dem|Rep) .+?) {2,}([\d,]+) +[\d.]+%", re.MULTILINE)


def extract(root, output):
    votes, pages = defaultdict(dict), defaultdict(set)
    for number, page in enumerate(PdfReader(root / SOURCE).pages, 1):
        text = page.extract_text(extraction_mode="layout")
        precinct = PRECINCT.search(text)[1].strip()
        for label, count in CANDIDATE.findall(text):
            if field := FIELDS.get(label):
                if field in votes[precinct]:
                    raise ValueError(f"Duplicate {field} for {precinct}")
                votes[precinct][field] = int(count.replace(",", ""))
                pages[precinct].add(number)

    graph = json.loads((root / "OH_pct20.json").read_text(encoding="utf-8"))
    matches = {}
    for node in graph["nodes"]:
        if node["COUNTY"] == "OTTAWA":
            members = node["ORIG_NAME"].split(",")
            for member in members:
                name = member.removesuffix("_OTTAWA")
                key = re.sub(r" \([^)]*\)$", "", name)
                matches[key] = node["id"], len(members) > 1, name

    with output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow([
            "county", "precinct_code", "precinct_name", "canvass_type", "source_file",
            "source_pages", "graph_node_ids", "graph_match_status", *FIELDS.values(),
        ])
        for name, counts in votes.items():
            node, combined, graph_label = matches[name.upper()]
            status = "combined_node" if combined else ("exact" if name.upper() == graph_label else "normalized")
            writer.writerow([
                "Ottawa", "", name, "official", SOURCE, ",".join(map(str, sorted(pages[name]))),
                node, status, *(counts[field] for field in FIELDS.values()),
            ])


if __name__ == "__main__":
    folder = Path(__file__).resolve().parent
    extract(folder.parents[1], folder / "precinct_votes.csv")

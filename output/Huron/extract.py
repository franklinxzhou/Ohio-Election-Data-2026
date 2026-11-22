#!/usr/bin/env python3
"""Extract statewide precinct vote totals from the Huron official canvass."""

import csv
import json
import re
from collections import defaultdict
from pathlib import Path

from pypdf import PdfReader

SOURCE = "Raw/Huron.pdf"
# First PDF page and zero-based D/R candidate columns within each contest.
RACES = [
    ("us_senate", 64, 0, 1),
    ("governor", 1, 0, 2),
    ("attorney_general", 10, 1, 0),
    ("auditor_of_state", 19, 0, 1),
    ("secretary_of_state", 28, 1, 2),
    ("treasurer_of_state", 37, 1, 0),
    ("supreme_court_2027_01_01", 46, 1, 0),
    ("supreme_court_2027_01_02", 55, 0, 1),
]
NAME_VARIANTS = {"FAIRFIELD": "FAIRFIELD TWP", "NORWALK-MILAN": "NORWALK-MILAN TWP"}


def extract(root, output):
    pdf = PdfReader(root / SOURCE)
    votes, source_pages = defaultdict(dict), defaultdict(set)
    for race, first, dem, rep in RACES:
        precinct = None
        for page in range(first, first + 9):
            for line in pdf.pages[page - 1].extract_text(extraction_mode="layout").splitlines():
                if line.startswith("Precinct "):
                    name, code = line.removeprefix("Precinct ").strip().rsplit(" ", 1)
                    precinct, heading_page = (code, name), page
                elif precinct and re.match(r"^\s*Total\s+\d", line):
                    counts = line.split()[4::2]
                    for party, index in (("dem", dem), ("rep", rep)):
                        votes[precinct][f"{race}_{party}"] = int(counts[index].replace(",", ""))
                    source_pages[precinct].update((heading_page, page))
                    precinct = None

    graph = json.loads((root / "OH_pct20.json").read_text(encoding="utf-8"))
    matches = {}
    for node in graph["nodes"]:
        if node["COUNTY"] == "HURON":
            members = node["ORIG_NAME"].split(",")
            for member in members:
                matches[member.removesuffix("_HURON")] = node["id"], len(members) > 1

    fields = [f"{race}_{party}" for race, *_ in RACES for party in ("dem", "rep")]
    with output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow([
            "county", "precinct_code", "precinct_name", "canvass_type", "source_file",
            "source_pages", "graph_node_ids", "graph_match_status", *fields,
        ])
        for code, name in sorted(votes):
            graph_name = NAME_VARIANTS.get(name, name.replace(" #", " "))
            node_id, combined = matches[graph_name]
            status = "combined_node" if combined else ("exact" if name == graph_name else "normalized")
            pages = ",".join(map(str, sorted(source_pages[code, name])))
            writer.writerow([
                "Huron", code, name, "official", SOURCE, pages, node_id, status,
                *(votes[code, name][field] for field in fields),
            ])


if __name__ == "__main__":
    folder = Path(__file__).resolve().parent
    extract(folder.parents[1], folder / "precinct_votes.csv")

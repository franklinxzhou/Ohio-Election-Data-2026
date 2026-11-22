#!/usr/bin/env python3
"""Extract statewide precinct vote totals from the Miami official canvass."""

import csv
import json
import re
from collections import defaultdict
from pathlib import Path

from pypdf import PdfReader

SOURCE = "Raw/Miami.pdf"
# First PDF page and zero-based D/R candidate columns within each contest.
RACES = [
    ("us_senate", 78, 0, 1),
    ("governor", 1, 0, 2),
    ("attorney_general", 12, 1, 0),
    ("auditor_of_state", 23, 0, 1),
    ("secretary_of_state", 34, 1, 2),
    ("treasurer_of_state", 45, 1, 0),
    ("supreme_court_2027_01_01", 56, 1, 0),
    ("supreme_court_2027_01_02", 67, 0, 1),
]
HEADING = "Mapped crosswalk exceptions"


def graph_name(name):
    return re.sub(r"\s*/\s*", " / ", name)


def graph_matches(root):
    graph = json.loads((root / "OH_pct20.json").read_text(encoding="utf-8"))
    matches = {}
    for node in graph["nodes"]:
        if node["COUNTY"] == "MIAMI":
            members = node["ORIG_NAME"].split(",")
            for member in members:
                matches[member.removesuffix("_MIAMI")] = node["id"], len(members) > 1
    return matches


def extract(root, output):
    pdf = PdfReader(root / SOURCE)
    votes, source_pages = defaultdict(dict), defaultdict(set)
    for race, first, dem, rep in RACES:
        precinct = None
        for page in range(first, first + 11):
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

    matches = graph_matches(root)
    notes = Path(__file__).with_name("precinct_merges_splits.txt").read_text()
    exceptions = {}
    for line in notes.split(HEADING + "\n", 1)[1].strip().splitlines():
        label, status, ids, _ = line.split(" | ")
        exceptions[label.split()[0]] = (ids, status)

    fields = [f"{race}_{party}" for race, *_ in RACES for party in ("dem", "rep")]
    with output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow([
            "county", "precinct_code", "precinct_name", "canvass_type", "source_file",
            "source_pages", "graph_node_ids", "graph_match_status", *fields,
        ])
        for code, name in sorted(votes):
            key = graph_name(name)
            if code in exceptions:
                node_id, status = exceptions[code]
            else:
                node_id, combined = matches[key]
                status = "combined_node" if combined else ("exact" if name == key else "normalized")
            pages = ",".join(map(str, sorted(source_pages[code, name])))
            writer.writerow([
                "Miami", code, name, "official", SOURCE, pages, node_id, status,
                *(votes[code, name][field] for field in fields),
            ])


if __name__ == "__main__":
    folder = Path(__file__).resolve().parent
    extract(folder.parents[1], folder / "precinct_votes.csv")

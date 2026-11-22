#!/usr/bin/env python3
"""Sum Marion's voting modes in the official precinct canvass."""

import csv
import re
from collections import defaultdict
from pathlib import Path

from pypdf import PdfReader

SOURCE = "Raw/Marion.pdf"
HEADING = "Precinct crosswalk"
# First page, number of turnout columns, and D/R candidate indices.
RACES = [
    ("us_senate", 49, 0, 0, 1),
    ("governor", 1, 3, 0, 2),
    ("attorney_general", 7, 3, 1, 0),
    ("auditor_of_state", 13, 3, 0, 1),
    ("secretary_of_state", 19, 3, 1, 2),
    ("treasurer_of_state", 25, 3, 1, 0),
    ("supreme_court_2027_01_01", 31, 3, 1, 0),
    ("supreme_court_2027_01_02", 37, 3, 0, 1),
]
PRECINCT = re.compile(r"^(\d{3}) (.+)$")
MODE = re.compile(r"^(?:Election Day|Absentee|Early Vote|Provisional)\s+(\d.+)$")


def read_votes(source):
    votes, pages = defaultdict(dict), defaultdict(set)
    pdf = PdfReader(source)
    for race, first, turnout, dem, rep in RACES:
        key = None
        for page in range(first, first + 6):
            for line in pdf.pages[page - 1].extract_text(extraction_mode="layout").splitlines():
                line = line.strip()
                if match := PRECINCT.fullmatch(line):
                    key = match.groups()
                    pages[key].add(page)
                elif line == "Total":
                    key = None
                elif key and (match := MODE.fullmatch(line)):
                    columns = match[1].split()
                    for party, index in (("dem", dem), ("rep", rep)):
                        field = f"{race}_{party}"
                        count = int(columns[turnout + 2 + 2 * index].replace(",", ""))
                        votes[key][field] = votes[key].get(field, 0) + count
                    pages[key].add(page)
    return votes, pages


def extract(root, output):
    votes, pages = read_votes(root / SOURCE)
    notes = Path(__file__).with_name("precinct_merges_splits.txt").read_text()
    links = {}
    for line in notes.split(HEADING + "\n", 1)[1].strip().splitlines():
        label, status, nodes, _ = line.split(" | ")
        links[tuple(label.split(" ", 1))] = nodes, status
    fields = [f"{race}_{party}" for race, *_ in RACES for party in ("dem", "rep")]
    with output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow([
            "county", "precinct_code", "precinct_name", "canvass_type", "source_file",
            "source_pages", "graph_node_ids", "graph_match_status", *fields,
        ])
        for key, counts in sorted(votes.items()):
            writer.writerow([
                "Marion", *key, "official", SOURCE, ",".join(map(str, sorted(pages[key]))),
                *links[key], *(counts[field] for field in fields),
            ])


if __name__ == "__main__":
    folder = Path(__file__).resolve().parent
    extract(folder.parents[1], folder / "precinct_votes.csv")

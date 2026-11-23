#!/usr/bin/env python3
"""Extract D/R precinct totals from Summit's final unofficial canvass."""

import csv
import re
from collections import defaultdict
from pathlib import Path

from pypdf import PdfReader

SOURCE = "Raw/Summit.pdf"
# Inclusive PDF page range and zero-based D/R candidate indexes.
RACES = [
    ("us_senate", 374, 426, 0, 1),
    ("governor", 1, 55, 0, 2),
    ("attorney_general", 56, 108, 1, 0),
    ("auditor_of_state", 109, 161, 0, 1),
    ("secretary_of_state", 162, 214, 1, 2),
    ("treasurer_of_state", 215, 267, 1, 0),
    ("supreme_court_2027_01_01", 268, 320, 1, 0),
    ("supreme_court_2027_01_02", 321, 373, 0, 1),
]
HEADING = "Crosswalk rows"
TOTAL = re.compile(r"^\s*Total\s+\d")


def precinct_headings(source):
    pdf = PdfReader(source)
    for page in pdf.pages[:55]:
        for line in page.extract_text(extraction_mode="layout").splitlines():
            if line.startswith("Precinct "):
                yield tuple(line.split(maxsplit=2)[1:])


def read_votes(source):
    pdf = PdfReader(source)
    votes, pages = defaultdict(dict), defaultdict(set)
    for race, first, last, dem, rep in RACES:
        precinct = None
        for page_number in range(first, last + 1):
            page = pdf.pages[page_number - 1].extract_text(extraction_mode="layout")
            for line in page.splitlines():
                if line.startswith("Precinct "):
                    precinct = tuple(line.split(maxsplit=2)[1:])
                    heading_page = page_number
                elif precinct and TOTAL.match(line):
                    counts = line.split()[4::2]
                    votes[precinct][race] = (int(counts[dem]), int(counts[rep]))
                    pages[precinct].update((heading_page, page_number))
                    precinct = None
    return votes, pages


def write_csv(folder, votes, pages):
    notes = (folder / "precinct_merges_splits.txt").read_text()
    crosswalk = {}
    for line in notes.split(f"\n{HEADING}\n", 1)[1].strip().splitlines():
        code, _, status, ids, _ = line.split(" | ")
        crosswalk[code] = ids, status

    with (folder / "precinct_votes.csv").open("w", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow([
            "county", "precinct_code", "precinct_name", "canvass_type", "source_file",
            "source_pages", "graph_node_ids", "graph_match_status",
            *(f"{race}_{party}" for race, *_ in RACES for party in ("dem", "rep")),
        ])
        for code, name in sorted(votes):
            source_pages = ",".join(map(str, sorted(pages[code, name])))
            writer.writerow([
                "Summit", code, name, "unofficial", SOURCE, source_pages, *crosswalk[code],
                *(count for race, *_ in RACES for count in votes[code, name][race]),
            ])


if __name__ == "__main__":
    folder = Path(__file__).resolve().parent
    write_csv(folder, *read_votes(folder.parents[1] / SOURCE))

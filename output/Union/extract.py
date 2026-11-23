#!/usr/bin/env python3
"""Sum the three voting modes for Union's official D/R precinct results."""

import csv
import re
from collections import defaultdict
from pathlib import Path

from pypdf import PdfReader

SOURCE = "Raw/Union.pdf"
HEADING = "Crosswalk rows"
# First PDF page, number of fields before vote columns, D/R candidate indexes.
RACES = [
    ("us_senate", 55, 2, 0, 1),
    ("governor", 7, 2, 0, 2),
    ("attorney_general", 13, 5, 1, 0),
    ("auditor_of_state", 19, 5, 0, 1),
    ("secretary_of_state", 25, 5, 1, 2),
    ("treasurer_of_state", 31, 5, 1, 0),
    ("supreme_court_2027_01_01", 37, 5, 1, 0),
    ("supreme_court_2027_01_02", 43, 5, 0, 1),
]
PRECINCT = re.compile(r"^(\d{2}) ([A-Z].+)$")
MODES = {"Normal", "Absentee", "Provisional"}


def read_votes(source):
    pdf = PdfReader(source)
    votes, pages = defaultdict(dict), defaultdict(set)
    for race, first, offset, dem, rep in RACES:
        precinct = None
        for number in range(first, first + 6):
            layout = pdf.pages[number - 1].extract_text(extraction_mode="layout")
            for line in map(str.strip, layout.splitlines()):
                if heading := PRECINCT.fullmatch(line):
                    precinct = heading.groups()
                    votes[precinct][race] = [0, 0]
                elif line == "Total":
                    precinct = None
                elif precinct and (columns := line.split()) and columns[0] in MODES:
                    counts = columns[1 + offset::2]
                    for party, index in enumerate((dem, rep)):
                        votes[precinct][race][party] += int(counts[index].replace(",", ""))
                    pages[precinct].add(number)
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
            precinct = code, name
            writer.writerow([
                "Union", code, name, "official", SOURCE,
                ",".join(map(str, sorted(pages[precinct]))), *crosswalk[code],
                *(count for race, *_ in RACES for count in votes[precinct][race]),
            ])


if __name__ == "__main__":
    folder = Path(__file__).resolve().parent
    write_csv(folder, *read_votes(folder.parents[1] / SOURCE))

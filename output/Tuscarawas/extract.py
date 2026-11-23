#!/usr/bin/env python3
"""Extract Tuscarawas official D/R precinct totals using pypdf."""

import csv
import re
from collections import defaultdict
from pathlib import Path

from pypdf import PdfReader

SOURCE = "Raw/Tuscarawas.pdf"
HEADING = "Crosswalk rows"
RACES = [
    ("us_senate", "Sherrod Brown", "Jon Husted"),
    ("governor", "Amy Acton", "Vivek Ramaswamy"),
    ("attorney_general", "John J. Kulewicz", "Keith Faber"),
    ("auditor_of_state", "Annette Blackwell", "Frank LaRose"),
    ("secretary_of_state", "Allison Russo", "Robert Sprague"),
    ("treasurer_of_state", "Seth Walsh", "Jay Edwards"),
    ("supreme_court_2027_01_01", "Marilyn Zayas", "Daniel R. Hawkins"),
    ("supreme_court_2027_01_02", "Jennifer Brunner", "Colleen O'Donnell"),
]
FIELDS = {
    candidate: f"{race}_{party}"
    for race, dem, rep in RACES for party, candidate in (("dem", dem), ("rep", rep))
}
PRECINCT = re.compile(r"November 16, 2026 +Tuscarawas County\n(\d{3}) ([^\n]+)")
CANDIDATE = re.compile(
    r"^(" + "|".join(map(re.escape, FIELDS)) + r") {2,}([\d,]+) +\d", re.MULTILINE,
)


def read_votes(source):
    votes, pages = defaultdict(dict), defaultdict(set)
    for number, page in enumerate(PdfReader(source).pages, 1):
        layout = page.extract_text(extraction_mode="layout")
        code, name = PRECINCT.search(layout).groups()
        precinct = code, name.strip()
        for candidate, count in CANDIDATE.findall(layout):
            votes[precinct][FIELDS[candidate]] = int(count.replace(",", ""))
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
            "source_pages", "graph_node_ids", "graph_match_status", *FIELDS.values(),
        ])
        for code, name in sorted(votes):
            precinct = code, name
            source_pages = ",".join(map(str, sorted(pages[precinct])))
            writer.writerow([
                "Tuscarawas", code, name, "official", SOURCE, source_pages, *crosswalk[code],
                *(votes[precinct][field] for field in FIELDS.values()),
            ])


if __name__ == "__main__":
    folder = Path(__file__).resolve().parent
    write_csv(folder, *read_votes(folder.parents[1] / SOURCE))

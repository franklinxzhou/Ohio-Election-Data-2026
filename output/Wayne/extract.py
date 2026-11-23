#!/usr/bin/env python3
"""Extract Wayne's unofficial statewide precinct totals and attach graph links."""

import csv
import re
from collections import defaultdict
from pathlib import Path

from pypdf import PdfReader

SOURCE = "Raw/Wayne.pdf"
# First page of each interleaved table. Candidate columns are in D/R order.
RACES = [
    ("us_senate", 46),
    ("governor", 4),
    ("attorney_general", 10),
    ("auditor_of_state", 16),
    ("secretary_of_state", 22),
    ("treasurer_of_state", 28),
    ("supreme_court_2027_01_01", 34),
    ("supreme_court_2027_01_02", 40),
]
ROW = re.compile(r"(\d{2}-\d{2})-(.+?) {2,}([\d,]+(?: +[\d,]+)*)")


def extract(folder):
    pdf = PdfReader(folder.parents[1] / SOURCE)
    votes, pages = defaultdict(dict), defaultdict(set)

    def rows(number):
        layout = pdf.pages[number - 1].extract_text(extraction_mode="layout")
        for line in layout.splitlines():
            found = [match.groups() for panel in re.split(r"(?=\d{2}-\d{2}-)", line)
                     if (match := ROW.match(panel))]
            if found:
                code, name, values = found[-1]
                yield (code, name), [int(n.replace(",", "")) for n in values.split()]

    for race, first in RACES:
        for number in range(first, first + 6, 2):
            for precinct, values in rows(number):
                votes[precinct][race] = (values[0], values[1])
                pages[precinct].add(number)
            if race in ("governor", "secretary_of_state"):
                for precinct, values in rows(number + 1):
                    votes[precinct][race] = (votes[precinct][race][0], values[0])
                    pages[precinct].add(number + 1)

    notes = (folder / "precinct_merges_splits.txt").read_text()
    links = {}
    for line in notes.split("\nCrosswalk rows\n", 1)[1].strip().splitlines():
        code, _, status, ids, _ = line.split(" | ")
        links[code] = ids, status

    with (folder / "precinct_votes.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow([
            "county", "precinct_code", "precinct_name", "canvass_type", "source_file",
            "source_pages", "graph_node_ids", "graph_match_status",
            *(f"{race}_{party}" for race, _ in RACES for party in ("dem", "rep")),
        ])
        for (code, name), counts in sorted(votes.items()):
            writer.writerow([
                "Wayne", code, name, "unofficial", SOURCE,
                ",".join(map(str, sorted(pages[code, name]))), *links[code],
                *(n for race, _ in RACES for n in counts[race]),
            ])


if __name__ == "__main__":
    extract(Path(__file__).resolve().parent)

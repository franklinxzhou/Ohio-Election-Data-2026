#!/usr/bin/env python3
"""Extract Wood's official statewide precinct totals using pypdf."""

import csv
import logging
import re
from collections import defaultdict
from pathlib import Path

from pypdf import PdfReader

SOURCE = "Raw/Wood.pdf"
HEADING = "Crosswalk rows"
# Each party's columns specify (PDF pages, panel, vote-column index).
RACES = {
    "us_senate": ((range(41, 48, 2), 1, 0), (range(41, 48, 2), 1, 1)),
    "governor": ((range(5, 12, 2), 1, 0), (range(6, 13, 2), 0, 0)),
    "attorney_general": ((range(13, 17), 1, 1), (range(13, 17), 1, 0)),
    "auditor_of_state": ((range(17, 21), 1, 0), (range(17, 21), 1, 1)),
    "secretary_of_state": ((range(21, 28, 2), 1, 1), (range(22, 29, 2), 0, 0)),
    "treasurer_of_state": ((range(29, 33), 1, 1), (range(29, 33), 1, 0)),
    "supreme_court_2027_01_01": ((range(33, 37), 1, 1), (range(33, 37), 1, 0)),
    "supreme_court_2027_01_02": ((range(37, 41), 1, 0), (range(37, 41), 1, 1)),
}
CODE = re.compile(r"(?<!\S)\d{3} [A-Z]")
ROSTER = re.compile(r"^(\d{3}) (.+?) {2,}[\d,]+")
CONTINUATION = re.compile(r"^[A-Z][A-Z\-/ .]+$")
COUNTS = re.compile(r" {2,}([\d,]+(?: +[\d,]+)*)")


def read_votes(source):
    pdf = PdfReader(source)
    # Rotated text is confined to column labels in the vote tables.
    logging.getLogger("pypdf._text_extraction._layout_mode._fixed_width_page").setLevel(logging.ERROR)
    layouts = {number: pdf.pages[number - 1].extract_text(extraction_mode="layout").splitlines()
               for number in range(1, 48)}

    names = {}
    for number in range(1, 5):
        for line in layouts[number]:
            if row := ROSTER.match(line):
                code, names[row[1]] = row.groups()
            elif CONTINUATION.fullmatch(line) and names:
                names[code] += " " + line

    votes, pages = defaultdict(dict), defaultdict(set)
    for race, specs in RACES.items():
        for party, (source_pages, panel, index) in zip(("dem", "rep"), specs):
            field = f"{race}_{party}"
            for number in source_pages:
                for line in layouts[number]:
                    anchors = list(CODE.finditer(line))
                    if not anchors:
                        continue
                    left = anchors[panel].start()
                    right = anchors[panel + 1].start() if panel + 1 < len(anchors) else len(line)
                    code = line[left:left + 3]
                    counts = COUNTS.search(line[left + 4:right])[1].split()
                    if field in votes[code]:
                        raise ValueError(f"Duplicate {field} for {code}")
                    votes[code][field] = int(counts[index].replace(",", ""))
                    pages[code].add(number)
    return names, votes, pages


def write_csv(folder, names, votes, pages):
    links = {}
    notes = (folder / "precinct_merges_splits.txt").read_text()
    for line in notes.split(f"\n{HEADING}\n", 1)[1].strip().splitlines():
        code, _, status, ids, _ = line.split(" | ")
        links[code] = ids, status

    fields = [f"{race}_{party}" for race in RACES for party in ("dem", "rep")]
    with (folder / "precinct_votes.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow([
            "county", "precinct_code", "precinct_name", "canvass_type", "source_file",
            "source_pages", "graph_node_ids", "graph_match_status", *fields,
        ])
        for code, name in sorted(names.items()):
            writer.writerow([
                "Wood", code, name, "official", SOURCE,
                ",".join(map(str, sorted(pages[code]))), *links[code],
                *(votes[code][field] for field in fields),
            ])


if __name__ == "__main__":
    folder = Path(__file__).resolve().parent
    write_csv(folder, *read_votes(folder.parents[1] / SOURCE))

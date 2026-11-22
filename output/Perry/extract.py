#!/usr/bin/env python3
"""Extract Perry's statewide precinct totals and join the county precinct key."""

import csv
import json
import re
from pathlib import Path

from pypdf import PdfReader

SOURCE = "Raw/Perry.pdf"
# First page and numeric token offset for each party. The next group of
# precincts starts two pages later. Offsets include the precinct code(s).
RACES = {
    "us_senate": ((31, 4), (31, 5)),
    "governor": ((3, 4), (4, 1)),
    "attorney_general": ((7, 5), (7, 4)),
    "auditor_of_state": ((11, 4), (11, 5)),
    "secretary_of_state": ((15, 5), (16, 1)),
    "treasurer_of_state": ((19, 5), (19, 4)),
    "supreme_court_2027_01_01": ((23, 5), (23, 4)),
    "supreme_court_2027_01_02": ((27, 4), (27, 5)),
}
CODES = [f"{number:02d}" for number in range(1, 34)]
# Board of Elections May 2026 ballot notice, pp. 6–9. See notes for aliases.
NAMES = [
    "New Lexington A/B", "New Lexington C/E/F", "New Lexington D",
    "New Lexington G/H/I", "Bearfield", "Clayton", "Coal",
    "Crooksville A/B/C/D", "Crooksville E/F", "Roseville",
    "Harrison S", "Harrison N", "Hopewell E/Glenford", "Hopewell W",
    "Junction City", "Jackson E", "Jackson W", "Madison", "Monday Creek",
    "Monroe", "Pike S", "Pike W", "Pleasant", "Somerset", "Reading E",
    "Reading N", "Reading S", "Saltlick", "Thornville", "Thorn W",
    "Thorn E", "Thorn S", "Buckeye Lake",
]
ALIASES = {
    "Bearfield": "BEARFIELD EAST/WEST",
    "Clayton": "REDFIELD/REHOBOTH",
    "Coal": "NEW STRAITSVILLE/COAL",
    "Harrison S": "MCLUNEY",
    "Harrison N": "HARRISON",
    "Hopewell E/Glenford": "HOPEWELL EAST/GLENFORD",
    "Hopewell W": "HOPEWELL WEST",
    "Monroe": "CORNING/RENDVILLE/MONROE",
    "Somerset": "SOMERSET NORTH/SOUTH",
    "Saltlick": "HEMLOCK/SHAWNEE/SALTLICK",
}
DIRECTIONS = {"E": "EAST", "W": "WEST", "N": "NORTH", "S": "SOUTH"}


def precinct_key(name):
    head, _, tail = name.upper().rpartition(" ")
    return ALIASES.get(name, f"{head} {DIRECTIONS[tail]}" if tail in DIRECTIONS else name.upper())


def read_page(page):
    layout = page.extract_text(extraction_mode="layout", layout_mode_strip_rotated=True)
    for line in layout.splitlines():
        tokens = line.split()
        if tokens and re.fullmatch(r"\d{2}(?:\s+[\d,]+)+", line.strip()):
            yield tokens


def extract(root, output):
    pdf = PdfReader(root / SOURCE)
    votes = {code: {} for code in CODES}
    pages = {code: set() for code in CODES}
    requested = sorted({page for specs in RACES.values() for first, _ in specs for page in (first, first + 2)})
    tables = {page: list(read_page(pdf.pages[page - 1])) for page in requested}
    for race, columns in RACES.items():
        for party, (first, offset) in zip(("dem", "rep"), columns):
            field = f"{race}_{party}"
            for page in (first, first + 2):
                for tokens in tables[page]:
                    code = tokens[0]
                    if offset > 1 and code != tokens[3]:
                        raise ValueError(f"Misaligned precinct columns on page {page}")
                    if field in votes[code]:
                        raise ValueError(f"Duplicate {field} for {code}")
                    votes[code][field] = int(tokens[offset].replace(",", ""))
                    pages[code].add(page)

    graph = json.loads((root / "OH_pct20.json").read_text())
    matches = {}
    for node in graph["nodes"]:
        if node["COUNTY"] == "PERRY":
            members = node["ORIG_NAME"].split(",")
            for member in members:
                matches[member.removesuffix("_PERRY")] = node["id"], len(members) > 1

    fields = [f"{race}_{party}" for race in RACES for party in ("dem", "rep")]
    with output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow([
            "county", "precinct_code", "precinct_name", "canvass_type", "source_file",
            "source_pages", "graph_node_ids", "graph_match_status", *fields,
        ])
        for code, name in zip(CODES, NAMES, strict=True):
            key = precinct_key(name)
            node, combined = matches[key]
            status = "combined_node" if combined else ("exact" if key == name.upper() else "normalized")
            writer.writerow([
                "Perry", code, name, "official", SOURCE, ",".join(map(str, sorted(pages[code]))),
                node, status, *(votes[code][field] for field in fields),
            ])


if __name__ == "__main__":
    folder = Path(__file__).resolve().parent
    extract(folder.parents[1], folder / "precinct_votes.csv")

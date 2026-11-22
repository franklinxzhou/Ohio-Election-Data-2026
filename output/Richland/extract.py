#!/usr/bin/env python3
"""Extract Richland's official statewide votes and match the graph by name."""

import csv
import json
import logging
import re
from pathlib import Path

from pypdf import PdfReader

SOURCE = "Raw/Richland.pdf"
# For each candidate: physical pages and column index after the precinct label.
RACES = [
    ("us_senate", ((31, 33, 35), 0), ((31, 33, 35), 2)),
    ("governor", ((4, 6, 8), 0), ((5, 7, 9), 0)),
    ("attorney_general", ((10, 11, 12), 2), ((10, 11, 12), 0)),
    ("auditor_of_state", ((13, 14, 15), 0), ((13, 14, 15), 2)),
    ("secretary_of_state", ((16, 18, 20), 2), ((17, 19, 21), 0)),
    ("treasurer_of_state", ((22, 23, 24), 2), ((22, 23, 24), 0)),
    ("supreme_court_2027_01_01", ((25, 26, 27), 2), ((25, 26, 27), 0)),
    ("supreme_court_2027_01_02", ((28, 29, 30), 0), ((28, 29, 30), 2)),
]
CITIES = {"MAN": "MANSFIELD", "SHL": "SHELBY", "ONT": "ONTARIO"}
TOWNSHIPS = {
    "BLMG": "BLOOMINGGROVE", "BUTLER": "BUTLER", "FRANK": "FRANKLIN",
    "JACK": "JACKSON", "JEFF": "JEFFERSON", "MAD": "MADISON",
    "MIFF": "MIFFLIN", "MON": "MONROE", "PERRY": "PERRY", "PLY": "PLYMOUTH",
    "SAND": "SANDUSKY", "SHARON": "SHARON", "SPFLD": "SPRINGFIELD",
    "TROY": "TROY", "WASH": "WASHINGTON", "WELLER": "WELLER",
    "WORTH": "WORTHINGTON",
}


def graph_name(label):
    prefix, *suffix = label.split()
    if prefix in CITIES:
        ward, _, letter = suffix
        return f"{CITIES[prefix]} WARD {ward} PREC {letter}"
    if prefix == "LEX":
        return f"LEXINGTON VILLAGE {suffix[0]}"
    if prefix == "CASS":
        return "CASS A"
    suffix = {"FRANK": ["A"], "PLY": ["A"], "WELLER": ["A"]}.get(prefix, suffix)
    return " ".join([TOWNSHIPS[prefix], "TOWNSHIP", *suffix])


def page_rows(page):
    layout = page.extract_text(extraction_mode="layout")
    for line in layout.splitlines():
        cells = re.split(r" {2,}", line.strip())
        if re.fullmatch(r".+ \d{4}", cells[0]):
            label, code = cells[0].rsplit(" ", 1)
            offset = 4 if len(cells) > 3 and cells[0] == cells[3] else 1
            yield code, label, cells[offset:]


def extract(root, output):
    pdf = PdfReader(root / SOURCE)
    numbers = {n for _, dem, rep in RACES for pages, _ in (dem, rep) for n in pages}
    tables = {n: list(page_rows(pdf.pages[n - 1])) for n in numbers}
    precincts = {}
    fields = []
    for race, dem, rep in RACES:
        for party, (pages, column) in zip(("dem", "rep"), (dem, rep)):
            field = f"{race}_{party}"
            fields.append(field)
            for n in pages:
                for code, label, cells in tables[n]:
                    _, votes, sources = precincts.setdefault(code, (label, {}, set()))
                    if field in votes:
                        raise ValueError(f"Duplicate {field} for {code}")
                    votes[field] = int(cells[column].replace(",", ""))
                    sources.add(n)

    graph = json.loads((root / "OH_pct20.json").read_text())
    members = {}
    for node in graph["nodes"]:
        if node["COUNTY"] == "RICHLAND":
            names = node["ORIG_NAME"].split(",")
            for name in names:
                members[name.removesuffix("_RICHLAND")] = node["id"], len(names) > 1

    with output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(["county", "precinct_code", "precinct_name", "canvass_type", "source_file",
                         "source_pages", "graph_node_ids", "graph_match_status", *fields])
        for code, (label, votes, sources) in sorted(precincts.items()):
            node, combined = members[graph_name(label)]
            writer.writerow([
                "Richland", code, label, "official", SOURCE, ",".join(map(str, sorted(sources))),
                node, "combined_node" if combined else "normalized",
                *(votes[field] for field in fields),
            ])


if __name__ == "__main__":
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    folder = Path(__file__).resolve().parent
    extract(folder.parents[1], folder / "precinct_votes.csv")

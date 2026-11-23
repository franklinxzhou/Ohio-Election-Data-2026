#!/usr/bin/env python3
"""Extract Scioto's unofficial statewide votes and match the graph by name."""

import csv
import json
import logging
import re
from pathlib import Path

from pypdf import PdfReader

SOURCE = "Raw/Scioto.pdf"
# For each candidate: physical pages and column index after the precinct label.
RACES = [
    ("us_senate", ((46, 48, 50), 0), ((46, 48, 50), 1)),
    ("governor", ((4, 6, 8), 0), ((5, 7, 9), 0)),
    ("attorney_general", ((10, 12, 14), 1), ((10, 12, 14), 0)),
    ("auditor_of_state", ((16, 18, 20), 0), ((16, 18, 20), 1)),
    ("secretary_of_state", ((22, 24, 26), 1), ((23, 25, 27), 0)),
    ("treasurer_of_state", ((28, 30, 32), 1), ((28, 30, 32), 0)),
    ("supreme_court_2027_01_01", ((34, 36, 38), 1), ((34, 36, 38), 0)),
    ("supreme_court_2027_01_02", ((40, 42, 44), 0), ((40, 42, 44), 1)),
]


def page_rows(page):
    layout = page.extract_text(extraction_mode="layout")
    for line in layout.splitlines():
        line = re.sub(r"(?<=[A-Z]) {2}(?=[A-Z] \d{4} )", " ", line)
        line = line.replace("SOUTH WEBSTER VILLAGE ", "SOUTH WEBSTER VILLAGE 0024 ")
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
        if node["COUNTY"] == "SCIOTO":
            names = node["ORIG_NAME"].split(",")
            for name in names:
                members[name.removesuffix("_SCIOTO")] = node["id"], len(names) > 1

    with output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(["county", "precinct_code", "precinct_name", "canvass_type", "source_file",
                         "source_pages", "graph_node_ids", "graph_match_status", *fields])
        for code, (label, votes, sources) in sorted(precincts.items()):
            node, combined = members[label]
            writer.writerow([
                "Scioto", code, label, "unofficial", SOURCE, ",".join(map(str, sorted(sources))),
                node, "combined_node" if combined else "exact",
                *(votes[field] for field in fields),
            ])


if __name__ == "__main__":
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    folder = Path(__file__).resolve().parent
    extract(folder.parents[1], folder / "precinct_votes.csv")

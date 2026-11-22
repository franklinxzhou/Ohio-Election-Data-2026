#!/usr/bin/env python3
"""Extract the eight statewide contests from Holmes County's official PDF."""

import csv
import json
import re
from pathlib import Path

from pypdf import PdfReader

SOURCE = "Raw/Holmes.pdf"
# PDF page and zero-based Democratic and Republican indices in the numeric block.
RACES = [
    ("us_senate", 10, 2, 4),
    ("governor", 2, 2, 6),
    ("attorney_general", 3, 7, 5),
    ("auditor_of_state", 4, 5, 7),
    ("secretary_of_state", 5, 7, 9),
    ("treasurer_of_state", 6, 7, 5),
    ("supreme_court_2027_01_01", 7, 7, 5),
    ("supreme_court_2027_01_02", 8, 5, 7),
]
ROW = re.compile(r"^\s*(\d{3}) ([^\n]+?) {2,}(\d[^\n]*)$", re.MULTILINE)


def extract(root, output):
    pdf = PdfReader(root / SOURCE)
    graph = json.loads((root / "OH_pct20.json").read_text(encoding="utf-8"))
    nodes = {
        node["ORIG_NAME"].removesuffix("_HOLMES"): node["id"]
        for node in graph["nodes"] if node["COUNTY"] == "HOLMES"
    }
    tables = []
    for _, page, dem, rep in RACES:
        rows = ROW.findall(pdf.pages[page - 1].extract_text(extraction_mode="layout"))
        tables.append({
            (code, name): tuple(int(columns.split()[i].replace(",", "")) for i in (dem, rep))
            for code, name, columns in rows
        })
    fields = [f"{race}_{party}" for race, *_ in RACES for party in ("dem", "rep")]
    pages = ",".join(str(page) for page in sorted({page for _, page, *_ in RACES}))
    with output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow([
            "county", "precinct_code", "precinct_name", "canvass_type", "source_file",
            "source_pages", "graph_node_ids", "graph_match_status", *fields,
        ])
        for code, name in sorted(tables[0]):
            votes = [count for table in tables for count in table[code, name]]
            writer.writerow([
                "Holmes", code, name, "official", SOURCE, pages, nodes[name.upper()],
                "exact", *votes,
            ])


if __name__ == "__main__":
    folder = Path(__file__).resolve().parent
    extract(folder.parents[1], folder / "precinct_votes.csv")

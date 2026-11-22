#!/usr/bin/env python3
"""Extract Coshocton's official precinct tables with Python 3 and pypdf."""

import csv
import json
import re
from pathlib import Path

from pypdf import PdfReader

SOURCE = "Raw/Coshocton.pdf"
# PDF page and zero-based numeric columns, in D/R order.
CONTESTS = {
    "us_senate": (7, 0, 1),
    "governor": (2, 0, 2),
    "attorney_general": (3, 1, 0),
    "auditor_of_state": (3, 6, 7),
    "secretary_of_state": (4, 1, 2),
    "treasurer_of_state": (5, 1, 0),
    "supreme_court_2027_01_01": (5, 7, 6),
    "supreme_court_2027_01_02": (6, 0, 1),
}
ALIASES = {
    "FRANKLIN / VIRGINIA": "FRANKLIN / CONESVILLE / VIRGINIA",
    "JEFFERSON / NELLIE / NEW CASTLE /": "JEFFERSON / NELLIE / NEW CASTLE / WARSAW",
    "LINTON": "LINTON / PLAINFIELD",
    "WEST LAFAYETTE": "W LAFAYETTE",
}
FIELDS = ["county", "precinct_code", "precinct_name", "canvass_type", "source_file",
          "source_pages", "graph_node_ids", "graph_match_status"]
FIELDS += [f"{contest}_{party}" for contest in CONTESTS for party in ("dem", "rep")]


def read_table(page):
    table = {}
    for line in page.extract_text(extraction_mode="layout").splitlines():
        name, *cells = re.split(r" {2,}", line.strip())
        if name != "Totals" and cells and all(re.fullmatch(r"[\d,]+", cell) for cell in cells):
            table[name] = [int(cell.replace(",", "")) for cell in cells]
    return table


def extract(root, output):
    pdf = PdfReader(root / SOURCE)
    tables = {page: read_table(pdf.pages[page - 1]) for page in range(2, 8)}
    graph = json.loads((root / "OH_pct20.json").read_text(encoding="utf-8"))
    by_name = {}
    for node in graph["nodes"]:
        if node["COUNTY"] == "COSHOCTON":
            members = node["ORIG_NAME"].split(",")
            for member in members:
                by_name[member.removesuffix("_COSHOCTON")] = (node["id"], len(members))

    with output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(FIELDS)
        for name in tables[2]:
            label = name.upper()
            lookup = f"COSHOCTON {label}" if re.fullmatch(r"[1-4]-[AB]", label) else ALIASES.get(label, label)
            node_id, size = by_name[lookup]
            status = "combined_node" if size > 1 else "exact" if label == lookup else "normalized"
            counts = [tables[page][name][column]
                      for page, dem, rep in CONTESTS.values() for column in (dem, rep)]
            writer.writerow(["Coshocton", "", name, "official", SOURCE, "2-7", node_id, status, *counts])


if __name__ == "__main__":
    folder = Path(__file__).resolve().parent
    extract(folder.parents[1], folder / "precinct_votes.csv")

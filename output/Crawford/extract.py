#!/usr/bin/env python3
"""Extract Crawford's official November precinct tables with Python 3 and pypdf."""

import csv
import json
import re
from pathlib import Path

from pypdf import PdfReader

SOURCE = "output/Crawford/official_canvass.pdf"
# First PDF page in each two-page table, numeric width, and D/R columns.
CONTESTS = {
    "us_senate": (12, 12, 0, 1),
    "governor": (2, 11, 0, 2),
    "attorney_general": (4, 12, 1, 0),
    "auditor_of_state": (4, 12, 6, 7),
    "secretary_of_state": (6, 7, 1, 2),
    "treasurer_of_state": (8, 12, 1, 0),
    "supreme_court_2027_01_01": (8, 12, 7, 6),
    "supreme_court_2027_01_02": (10, 6, 0, 1),
}
FIELDS = ["county", "precinct_code", "precinct_name", "canvass_type", "source_file",
          "source_pages", "graph_node_ids", "graph_match_status"]
FIELDS += [f"{contest}_{party}" for contest in CONTESTS for party in ("dem", "rep")]


def read_table(layouts, first, width):
    table = {}
    for page in (first, first + 1):
        for line in layouts[page].splitlines():
            name, *cells = re.split(r" {2,}", line.strip())
            if name != "Totals" and len(cells) == width and all(re.fullmatch(r"[\d,]+", x) for x in cells):
                table[name] = (page, [int(cell.replace(",", "")) for cell in cells])
    return table


def extract(root, output):
    pdf = PdfReader(root / SOURCE)
    layouts = {page: pdf.pages[page - 1].extract_text(extraction_mode="layout") for page in range(2, 14)}
    tables = {first: read_table(layouts, first, width) for first, width, _, _ in CONTESTS.values()}
    graph = json.loads((root / "OH_pct20.json").read_text(encoding="utf-8"))
    by_name = {}
    for node in graph["nodes"]:
        if node["COUNTY"] == "CRAWFORD":
            members = node["ORIG_NAME"].split(",")
            status = "combined_node" if len(members) > 1 else "exact"
            for member in members:
                by_name[member.removesuffix("_CRAWFORD")] = (node["id"], status)

    with output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(FIELDS)
        for name in tables[2]:
            node_id, status = by_name[name]
            pages, votes = set(), []
            for first, _, dem, rep in CONTESTS.values():
                page, counts = tables[first][name]
                pages.add(page)
                votes.extend((counts[dem], counts[rep]))
            writer.writerow(["Crawford", "", name, "official", SOURCE,
                             ",".join(map(str, sorted(pages))), node_id, status, *votes])


if __name__ == "__main__":
    folder = Path(__file__).resolve().parent
    extract(folder.parents[1], folder / "precinct_votes.csv")

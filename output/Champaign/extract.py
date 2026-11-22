#!/usr/bin/env python3
"""Extract Champaign's official precinct tables with Python 3 and pypdf."""

import csv
import json
import re
from pathlib import Path

from pypdf import PdfReader

SOURCE = "Raw/Champaign.pdf"
# PDF pages and zero-based candidate column indices in D/R order.
CONTESTS = {
    "us_senate": (9, 0, 1),
    "governor": (1, 0, 2),
    "attorney_general": (3, 1, 0),
    "auditor_of_state": (4, 0, 1),
    "secretary_of_state": (5, 1, 2),
    "treasurer_of_state": (6, 1, 0),
    "supreme_court_2027_01_01": (7, 1, 0),
    "supreme_court_2027_01_02": (8, 0, 1),
}
FIELDS = ["county", "precinct_code", "precinct_name", "canvass_type", "source_file",
          "source_pages", "graph_node_ids", "graph_match_status"]
FIELDS += [f"{contest}_{party}" for contest in CONTESTS for party in ("dem", "rep")]
ROW = re.compile(r"^Precinct (\d{4}) (.+?)\s{2,}\d+\s+\d+\s+\d+\s+(.+)$", re.MULTILINE)
VOTES = re.compile(r"(\d+)\s+\d+(?:\.\d+)?%")
SPLITS = {
    "GOSHEN NORTH": "GOSHEN",
    "GOSHEN SOUTH": "GOSHEN",
    "WAYNE NORTH": "WAYNE",
    "WAYNE SOUTH": "WAYNE",
}


def extract(root, output):
    pdf = PdfReader(root / SOURCE)
    tables = []
    for page, dem, rep in CONTESTS.values():
        layout = pdf.pages[page - 1].extract_text(extraction_mode="layout")
        table = {}
        for code, name, cells in ROW.findall(layout):
            counts = VOTES.findall(cells)
            table[code, name] = (int(counts[dem]), int(counts[rep]))
        tables.append(table)

    graph = json.loads((root / "OH_pct20.json").read_text(encoding="utf-8"))
    by_name = {}
    for node in graph["nodes"]:
        if node["COUNTY"] == "CHAMPAIGN":
            members = node["ORIG_NAME"].split(",")
            for member in members:
                label = member.removesuffix("_CHAMPAIGN")
                status = "exact" if label == label.removesuffix(" PRECINCT") else "normalized"
                if len(members) > 1:
                    status = "combined_node"
                by_name[label.removesuffix(" PRECINCT")] = (node["id"], status)

    rows = []
    for code, name in tables[0]:
        node_id, status = by_name.get(SPLITS.get(name, name), ("", "unmatched"))
        if name in SPLITS:
            status = "split_precinct"
        rows.append(["Champaign", code, name, "official", SOURCE, "1,3-9", node_id, status,
                     *(count for table in tables for count in table[code, name])])

    with output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(FIELDS)
        writer.writerows(rows)


if __name__ == "__main__":
    folder = Path(__file__).resolve().parent
    extract(folder.parents[1], folder / "precinct_votes.csv")

#!/usr/bin/env python3
"""Extract Guernsey's official paired-page precinct tables with pypdf."""

import csv
import json
import logging
import re
from collections import defaultdict
from pathlib import Path

from pypdf import PdfReader

SOURCE = "Raw/Guernsey.pdf"
# First page of each contest and (panel offset, candidate column) in D/R order.
RACES = {
    "us_senate": (105, (0, 0), (0, 1)),
    "governor": (7, (0, 0), (1, 0)),
    "attorney_general": (21, (0, 1), (0, 0)),
    "auditor_of_state": (35, (0, 0), (0, 1)),
    "secretary_of_state": (49, (0, 1), (1, 0)),
    "treasurer_of_state": (63, (0, 1), (0, 0)),
    "supreme_court_2027_01_01": (77, (0, 1), (0, 0)),
    "supreme_court_2027_01_02": (91, (0, 0), (0, 1)),
}
FIELDS = ["county", "precinct_code", "precinct_name", "canvass_type", "source_file",
          "source_pages", "graph_node_ids", "graph_match_status"]
FIELDS += [f"{race}_{party}" for race in RACES for party in ("dem", "rep")]
HEADING = re.compile(r"^(\d{3,4})(?: +(.+))?$")
WRAPPED = {
    "023": "LONDONDERRY/WASHINGTON",
    "024": "QUAKER CITY/MILLWOOD",
    "032": "PLEASANT CITY/VALLEY B",
    "035": "OLD WASHINGTON/WILLS",
}


def read_panel(layouts, first, offset):
    totals = {}
    for page in range(first + offset, first + 14, 2):
        code = None
        for line in layouts[page].splitlines():
            label, *cells = re.split(r" {2,}", line.strip())
            if match := HEADING.fullmatch(label):
                code = match[1]
            elif label == "Total" and code:
                values = cells[3:] if cells[2:3] == ["Total"] else cells
                totals[code] = (page, tuple(int(cell.replace(",", "")) for cell in values))
                code = None
    return totals


def extract(root, output):
    # Vertical headers are used to establish the column mapping above.
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    pdf = PdfReader(root / SOURCE)
    layouts = {i: pdf.pages[i - 1].extract_text(extraction_mode="layout") for i in range(1, 119)}
    names = {}
    for page in range(1, 7):
        for line in layouts[page].splitlines():
            if match := HEADING.fullmatch(line.strip()):
                code, label = match.groups()
                names[code] = WRAPPED.get(code, label)
    tables = [(read_panel(layouts, first, offset), column)
              for first, dem, rep in RACES.values() for offset, column in (dem, rep)]

    graph = json.loads((root / "OH_pct20.json").read_text(encoding="utf-8"))
    by_name = defaultdict(list)
    for node in graph["nodes"]:
        if node["COUNTY"] == "GUERNSEY":
            members = node["ORIG_NAME"].split(",")
            status = "combined_node" if len(members) > 1 else "exact"
            for name in members:
                by_name[name.removesuffix("_GUERNSEY")].append((node["id"], status))

    with output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(FIELDS)
        for code, name in names.items():
            matches = sorted(by_name[name])
            if not matches:
                raise ValueError(f"No graph match for {name}")
            node_ids = ";".join(str(node_id) for node_id, _ in matches)
            status = "split_nodes" if len(matches) > 1 else matches[0][1]
            pages, counts = set(), []
            for table, column in tables:
                page, votes = table[code]
                pages.add(page)
                counts.append(votes[column])
            writer.writerow(["Guernsey", code, name, "official", SOURCE,
                             ",".join(map(str, sorted(pages))), node_ids, status, *counts])


if __name__ == "__main__":
    folder = Path(__file__).resolve().parent
    extract(folder.parents[1], folder / "precinct_votes.csv")

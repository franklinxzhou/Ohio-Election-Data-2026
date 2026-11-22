#!/usr/bin/env python3
"""Extract Hardin's official paired-page precinct tables with pypdf."""

import csv
import json
import logging
import re
from collections import defaultdict
from pathlib import Path

from pypdf import PdfReader

SOURCE = "Raw/Hardin.pdf"
# First page of each contest and (panel offset, candidate column) in D/R order.
RACES = {
    "us_senate": (76, (0, 0), (0, 1)),
    "governor": (6, (0, 0), (1, 0)),
    "attorney_general": (16, (0, 1), (0, 0)),
    "auditor_of_state": (26, (0, 0), (0, 1)),
    "secretary_of_state": (36, (0, 1), (1, 0)),
    "treasurer_of_state": (46, (0, 1), (0, 0)),
    "supreme_court_2027_01_01": (56, (0, 1), (0, 0)),
    "supreme_court_2027_01_02": (66, (0, 0), (0, 1)),
}
FIELDS = ["county", "precinct_code", "precinct_name", "canvass_type", "source_file",
          "source_pages", "graph_node_ids", "graph_match_status"]
FIELDS += [f"{race}_{party}" for race in RACES for party in ("dem", "rep")]
HEADING = re.compile(r"[A-Z][A-Z0-9 /-]+")
ALIASES = {
    "ALGER/MCGUFFEY/MARION": "ALGER / MCGUFFY / MARION",
    "DUDLEY": "DUDLEY TWP",
    "DUNKIRK/BLANCHARD": "DUNKIRK / BLANCHARD",
    "FOREST/JACKSON": "FOREST / JACKSON",
    "MT VICTORY/RIDGEWAY/HALE": "MOUNT VICTORY / RIDGEWAY / HALE",
}


def read_panel(layouts, first, offset):
    totals = {}
    for page in range(first + offset, first + 10, 2):
        name = None
        for line in layouts[page].splitlines():
            label, *cells = re.split(r" {2,}", line.strip())
            if HEADING.fullmatch(label):
                name = f"MT {label}" if label == "VICTORY/RIDGEWAY/HALE" else label
            elif label == "Total" and name:
                values = cells[3:] if offset == 0 else cells
                totals[name] = (page, tuple(int(cell.replace(",", "")) for cell in values
                                            if re.fullmatch(r"[\d,]+", cell)))
                name = None
    return totals


def extract(root, output):
    # Vertical headers are used to establish the column mapping above.
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    pdf = PdfReader(root / SOURCE)
    layouts = {i: pdf.pages[i - 1].extract_text(extraction_mode="layout") for i in range(6, 86)}
    tables = [(read_panel(layouts, first, offset), column)
              for first, dem, rep in RACES.values() for offset, column in (dem, rep)]

    graph = json.loads((root / "OH_pct20.json").read_text(encoding="utf-8"))
    by_name = defaultdict(list)
    for node in graph["nodes"]:
        if node["COUNTY"] == "HARDIN":
            members = node["ORIG_NAME"].split(",")
            status = "combined_node" if len(members) > 1 else "exact"
            for name in members:
                by_name[name.removesuffix("_HARDIN")].append((node["id"], status))

    with output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(FIELDS)
        for name in tables[2][0]:
            lookup = ALIASES.get(name, name)
            matches = sorted(by_name[lookup])
            if not matches:
                raise ValueError(f"No graph match for {name}")
            node_ids = ";".join(str(node_id) for node_id, _ in matches)
            status = "split_nodes" if len(matches) > 1 else matches[0][1]
            if status == "exact" and lookup != name:
                status = "normalized"
            pages, counts = set(), []
            for table, column in tables:
                page, votes = table[name]
                pages.add(page)
                counts.append(votes[column])
            writer.writerow(["Hardin", "", name, "official", SOURCE,
                             ",".join(map(str, sorted(pages))), node_ids, status, *counts])


if __name__ == "__main__":
    folder = Path(__file__).resolve().parent
    extract(folder.parents[1], folder / "precinct_votes.csv")

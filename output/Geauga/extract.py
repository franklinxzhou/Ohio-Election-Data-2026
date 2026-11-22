#!/usr/bin/env python3
"""Extract Geauga's official precinct tables with Python 3 and pypdf."""

import csv
import json
import re
from collections import defaultdict
from pathlib import Path

from pypdf import PdfReader

SOURCE = "Raw/Geauga.pdf"
# Table's first page and zero-based candidate columns, in D/R order.
CONTESTS = {
    "us_senate": (16, 4, 5),
    "governor": (5, 0, 2),
    "attorney_general": (11, 1, 0),
    "auditor_of_state": (11, 2, 3),
    "secretary_of_state": (11, 5, 6),
    "treasurer_of_state": (11, 8, 7),
    "supreme_court_2027_01_01": (16, 1, 0),
    "supreme_court_2027_01_02": (16, 2, 3),
}
BLOCKS = {5: (10, 7), 11: (15, 9), 16: (20, 11)}
# Documented predecessor links in precinct_merges_splits.txt.
CHANGES = {
    "BAINBRIDGE TOWNSHIP B": ("split_precinct", ("BAINBRIDGE TWP B",)),
    "BAINBRIDGE TOWNSHIP D": ("split_precinct", ("BAINBRIDGE TWP D",)),
    "BAINBRIDGE TOWNSHIP F": ("split_precinct", ("BAINBRIDGE TWP F",)),
    "BAINBRIDGE TOWNSHIP J": ("boundary_overlap", ("BAINBRIDGE TWP B", "BAINBRIDGE TWP D", "BAINBRIDGE TWP F")),
    "CHARDON CITY C": ("boundary_overlap", ("CHARDON CITY C", "CHARDON CITY D")),
    "CHARDON CITY D": ("split_precinct", ("CHARDON CITY D",)),
    "CLARIDON TOWNSHIP D": ("renamed", ("AQUILLA VILLAGE",)),
}
FIELDS = ["county", "precinct_code", "precinct_name", "canvass_type", "source_file",
          "source_pages", "graph_node_ids", "graph_match_status"]
FIELDS += [f"{race}_{party}" for race in CONTESTS for party in ("dem", "rep")]


def graph_key(label):
    label = label.replace(" TOWNSHIP ", " TWP ")
    return re.sub(r" VILLAGE(?= [A-Z]$|$)", " VILL", label)


def read_tables(pdf):
    tables = {}
    for first, (last, width) in BLOCKS.items():
        table = {}
        for page in range(first, last + 1):
            for line in pdf.pages[page - 1].extract_text(extraction_mode="layout").splitlines():
                name, *cells = re.split(r" {2,}", line.strip())
                if name != "Totals" and len(cells) == width and all(re.fullmatch(r"[\d,]+", x) for x in cells):
                    table[name] = (page, tuple(int(cell.replace(",", "")) for cell in cells))
        tables[first] = table
    return tables


def extract(root, output):
    tables = read_tables(PdfReader(root / SOURCE))
    graph = json.loads((root / "OH_pct20.json").read_text(encoding="utf-8"))
    by_name = defaultdict(list)
    for node in graph["nodes"]:
        if node["COUNTY"] == "GEAUGA":
            members = node["ORIG_NAME"].split(",")
            for member in members:
                _, label = member.removesuffix("_GEAUGA").split(" ", 1)
                by_name[graph_key(label)].append((node["id"], len(members), label))

    with output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(FIELDS)
        for name in tables[5]:
            if name in CHANGES:
                status, predecessors = CHANGES[name]
                ids = {node for label in predecessors for node, _, _ in by_name[graph_key(label)]}
                node_id = ";".join(map(str, sorted(ids)))
            else:
                matches = by_name[graph_key(name)]
                node_id, members, original = matches[0]
                status = "combined_node" if members > 1 else "exact" if name == original else "normalized"
            pages, votes = set(), []
            for first, dem, rep in CONTESTS.values():
                page, counts = tables[first][name]
                pages.add(page)
                votes.extend((counts[dem], counts[rep]))
            writer.writerow(["Geauga", "", name, "official", SOURCE,
                             ",".join(map(str, sorted(pages))), node_id, status, *votes])


if __name__ == "__main__":
    folder = Path(__file__).resolve().parent
    extract(folder.parents[1], folder / "precinct_votes.csv")

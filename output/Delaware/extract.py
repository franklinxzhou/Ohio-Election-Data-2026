#!/usr/bin/env python3
"""Extract Delaware's unofficial numbered key canvass with Python 3."""

import csv
import json
import re
from collections import defaultdict
from pathlib import Path

SOURCE = "Raw/Delaware.txt"
# First page of each five-page table and zero-based D/R columns.
CONTESTS = {
    "us_senate": (41, 0, 1),
    "governor": (6, 0, 2),
    "attorney_general": (11, 1, 0),
    "auditor_of_state": (16, 0, 1),
    "secretary_of_state": (21, 1, 2),
    "treasurer_of_state": (26, 1, 0),
    "supreme_court_2027_01_01": (31, 1, 0),
    "supreme_court_2027_01_02": (36, 0, 1),
}
FIELDS = ["county", "precinct_code", "precinct_name", "canvass_type", "source_file",
          "source_pages", "graph_node_ids", "graph_match_status"]
FIELDS += [f"{race}_{party}" for race in CONTESTS for party in ("dem", "rep")]
ROW = re.compile(r"(\d{5}) (\d{3}) (.+?) {2,}(\d+(?: +\d+)*) *")
PAGE = re.compile(r"\bPAGE +(\d+)/\d+")
BOUNDARY_HEADER = "Code and precinct | Status | Graph IDs | Historical precincts and area shares"


def graph_key(name):
    label = name.upper().replace(" CITY ", " ")
    if label in {"DELAWARE A", "DELAWARE B"}:
        return label.replace("DELAWARE ", "DELAWARE TWP ")
    return label


def graph_members(root):
    graph = json.loads((root / "OH_pct20.json").read_text(encoding="utf-8"))
    for node in graph["nodes"]:
        if node["COUNTY"] == "DELAWARE":
            names = tuple(member.removesuffix("_DELAWARE") for member in node["ORIG_NAME"].split(","))
            yield node["id"], names, node["ENACTED_LOWER"]


def read_votes(source):
    by_page = {page: first for first, _, _ in CONTESTS.values() for page in range(first, first + 5)}
    tables = defaultdict(dict)
    first = None
    for line in source.read_text(encoding="utf-8-sig").splitlines():
        if match := PAGE.search(line):
            page = int(match[1])
            first = by_page.get(page)
        elif first is not None and (match := ROW.fullmatch(line)):
            gis_id, code, name, cells = match.groups()
            precinct = (gis_id, code, name)
            if precinct in tables[first]:
                raise ValueError(f"Duplicate precinct {code} in the table beginning on page {first}")
            tables[first][precinct] = (page, tuple(map(int, cells.split())))
    return tables


def extract(root, output):
    tables = read_votes(root / SOURCE)
    by_name = defaultdict(list)
    for node_id, names, _ in graph_members(root):
        for name in names:
            by_name[name].append((node_id, len(names)))

    notes = (output.parent / "precinct_merges_splits.txt").read_text(encoding="utf-8")
    _, _, records = notes.partition(BOUNDARY_HEADER + "\n")
    overrides = {}
    for line in records.splitlines():
        precinct, status, nodes, _ = line.split(" | ", 3)
        overrides[precinct] = (nodes, status)

    with output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(FIELDS)
        for precinct in tables[6]:
            _, code, name = precinct
            label = f"{code} {name}"
            if label in overrides:
                nodes, status = overrides[label]
            else:
                matches = sorted(by_name[graph_key(name)])
                nodes = ";".join(str(node_id) for node_id, _ in matches)
                if len(matches) > 1:
                    status = "split_nodes"
                elif matches[0][1] > 1:
                    status = "combined_node"
                else:
                    status = "exact" if name.upper() == graph_key(name) else "normalized"
            pages, counts = [], []
            for first, dem, rep in CONTESTS.values():
                page, votes = tables[first][precinct]
                pages.append(page)
                counts.extend((votes[dem], votes[rep]))
            writer.writerow(["Delaware", code, name, "unofficial", SOURCE,
                             ",".join(map(str, sorted(pages))), nodes, status, *counts])


if __name__ == "__main__":
    folder = Path(__file__).resolve().parent
    extract(folder.parents[1], folder / "precinct_votes.csv")

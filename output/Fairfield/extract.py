#!/usr/bin/env python3
"""Extract Fairfield's official precinct vote tables with Python 3 and pypdf."""

import csv
import json
import logging
import re
from collections import defaultdict
from pathlib import Path

from pypdf import PdfReader

SOURCE = "Raw/Fairfield.pdf"
# First page, pages per precinct group, and (page offset, column) in D/R order.
CONTESTS = {
    "us_senate": (41, 2, (0, 0), (0, 1)),
    "governor": (5, 2, (0, 0), (1, 0)),
    "attorney_general": (13, 1, (0, 1), (0, 0)),
    "auditor_of_state": (17, 1, (0, 0), (0, 1)),
    "secretary_of_state": (21, 2, (0, 1), (1, 0)),
    "treasurer_of_state": (29, 1, (0, 1), (0, 0)),
    "supreme_court_2027_01_01": (33, 1, (0, 1), (0, 0)),
    "supreme_court_2027_01_02": (37, 1, (0, 0), (0, 1)),
}
FIELDS = ["county", "precinct_code", "precinct_name", "canvass_type", "source_file",
          "source_pages", "graph_node_ids", "graph_match_status"]
FIELDS += [f"{contest}_{party}" for contest in CONTESTS for party in ("dem", "rep")]
CODE = re.compile(r"[A-Z]+-[A-Z0-9]+")
BOUNDARY_HEADER = "Precinct | Status | Graph IDs | Historical precincts and area shares"
PREFIXES = {
    "AM": "AMANDA", "BA": "BALTIMORE VILLAGE", "BE": "BERNE", "BL": "BLOOM",
    "CL": "CLEARCREEK", "COL": "COLUMBUS CITY", "GR": "GREENFIELD", "HO": "HOCKING",
    "LAN": "LANCASTER CITY", "LI": "LIBERTY", "LIV": "LITHOPOLIS VILLAGE",
    "MA": "MADISON", "PIC": "PICKERINGTON CITY", "PL": "PLEASANT",
    "RU": "RUSHCREEK", "VI": "VIOLET", "WA": "WALNUT",
}


def graph_key(code):
    aliases = {"BR-V": "BREMEN VILLAGE", "RI-E": "RICHLAND EAST", "RI-W": "RICHLAND WEST"}
    if code in aliases:
        return aliases[code]
    prefix, suffix = code.split("-", 1)
    if prefix == "LAN":
        suffix = f"{suffix[0]}-{suffix[1]}"
    return f"{PREFIXES[prefix]} {suffix}"


def graph_members(root):
    graph = json.loads((root / "OH_pct20.json").read_text(encoding="utf-8"))
    for node in graph["nodes"]:
        if node["COUNTY"] == "FAIRFIELD":
            members = tuple(member.removesuffix("_FAIRFIELD") for member in node["ORIG_NAME"].split(","))
            yield node["id"], members, node["ENACTED_LOWER"]


def read_panels(source):
    # The vertical candidate labels are skipped by layout extraction.
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    panels = {}
    for number, page in enumerate(PdfReader(source).pages[:48], 1):
        rows = {}
        for line in page.extract_text(extraction_mode="layout").splitlines():
            code, *cells = re.split(r" {2,}", line.strip())
            if CODE.fullmatch(code) and cells:
                if len(cells) > 2 and cells[2] == code:
                    cells = cells[3:]
                rows[code] = tuple(int(cell.replace(",", "")) for cell in cells
                                   if re.fullmatch(r"[\d,]+", cell))
        panels[number] = rows
    return panels


def extract(root, output):
    panels = read_panels(root / SOURCE)
    codes = [code for page in range(1, 5) for code in panels[page]]
    by_name = defaultdict(list)
    for node_id, members, _ in graph_members(root):
        for name in members:
            by_name[name].append((node_id, len(members)))
    notes = (output.parent / "precinct_merges_splits.txt").read_text(encoding="utf-8")
    _, _, records = notes.partition(BOUNDARY_HEADER + "\n")
    overrides = {}
    for line in records.splitlines():
        code, status, nodes, _ = line.split(" | ", 3)
        overrides[code] = (nodes, status)

    with output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(FIELDS)
        for code in codes:
            if code in overrides:
                nodes, status = overrides[code]
            else:
                matches = sorted(by_name[graph_key(code)])
                nodes = ";".join(str(node_id) for node_id, _ in matches)
                status = "split_nodes" if len(matches) > 1 else "combined_node" if matches[0][1] > 1 else "normalized"
            pages, votes = set(), []
            for first, stride, dem, rep in CONTESTS.values():
                start, = (page for page in range(first, first + 4 * stride, stride) if code in panels[page])
                for offset, column in (dem, rep):
                    page = start + offset
                    pages.add(page)
                    votes.append(panels[page][code][column])
            writer.writerow(["Fairfield", code, code, "official", SOURCE,
                             ",".join(map(str, sorted(pages))), nodes, status, *votes])


if __name__ == "__main__":
    folder = Path(__file__).resolve().parent
    extract(folder.parents[1], folder / "precinct_votes.csv")

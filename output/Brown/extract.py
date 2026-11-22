#!/usr/bin/env python3
"""Extract Brown's Official Canvass with Python 3 and pypdf."""

import csv
import json
import re
from collections import defaultdict
from pathlib import Path

from pypdf import PdfReader

SOURCE = "Raw/Brown.pdf"
# Columns are in D/R order. Page offsets are relative to each precinct.
CONTESTS = {
    "us_senate": (1, "Sherrod Brown", "Jon Husted"),
    "governor": (0, "Amy Acton", "Vivek Ramaswamy"),
    "attorney_general": (0, "John J. Kulewicz", "Keith Faber"),
    "auditor_of_state": (0, "Annette Blackwell", "Frank LaRose"),
    "secretary_of_state": (0, "Allison Russo", "Robert Sprague"),
    "treasurer_of_state": (0, "Seth Walsh", "Jay Edwards"),
    "supreme_court_2027_01_01": (0, "Marilyn Zayas", "Daniel R. Hawkins"),
    "supreme_court_2027_01_02": (0, "Jennifer Brunner", "Colleen O'Donnell"),
}
COLUMNS = ["county", "precinct_code", "precinct_name", "canvass_type", "source_file",
           "source_pages", "graph_node_ids", "graph_match_status"]
COLUMNS += [f"{contest}_{party}" for contest in CONTESTS for party in ("dem", "rep")]
PRECINCT = re.compile(r"^\s*(\d{4}) ([^\n]+)$", re.MULTILINE)


def votes_on_page(text, candidate):
    pattern = re.escape(candidate) + r"[^\n]*? {2,}([\d,]+) +[\d.]+%"
    count, = re.findall(pattern, text)
    return int(count.replace(",", ""))


def extract(root, output):
    graph = json.loads((root / "OH_pct20.json").read_text(encoding="utf-8"))
    by_name = defaultdict(list)
    for node in graph["nodes"]:
        if node["COUNTY"] == "BROWN":
            members = node["ORIG_NAME"].split(",")
            for member in members:
                by_name[member.removesuffix("_BROWN")].append((node["id"], len(members)))

    pdf = PdfReader(root / SOURCE)
    rows = []
    for first in range(0, len(pdf.pages), 3):
        pages = [pdf.pages[first + offset].extract_text(extraction_mode="layout") for offset in (0, 1)]
        code, name = PRECINCT.search(pages[0]).groups()
        name = name.strip()
        key = name.upper()
        lookup = {"SARDINIA VILL": "SARDINIA VILLAGE"}.get(key, key)
        if code == "0081":
            # County GIS and 2020 Census overlay documented in the TXT record.
            lookup = "MT ORAB NORTH"
        matches = by_name[lookup]
        if code == "0081":
            status = "split_precinct"
        elif len(matches) == 1:
            status = "combined_node" if matches[0][1] > 1 else "exact" if lookup == key else "normalized"
        else:
            status = "split_nodes" if matches else "unmatched"
        votes = [votes_on_page(pages[offset], candidate)
                 for offset, dem, rep in CONTESTS.values() for candidate in (dem, rep)]
        rows.append(["Brown", code, name, "official", SOURCE, f"{first + 1}-{first + 2}",
                     ";".join(str(node_id) for node_id, _ in matches), status, *votes])

    with output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(COLUMNS)
        writer.writerows(rows)


if __name__ == "__main__":
    folder = Path(__file__).resolve().parent
    extract(folder.parents[1], folder / "precinct_votes.csv")

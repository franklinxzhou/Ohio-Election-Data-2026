#!/usr/bin/env python3
"""Extract Clark's official statewide precinct returns with Python 3 and pypdf."""

import csv
import json
import re
from collections import defaultdict
from pathlib import Path

from pypdf import PdfReader

SOURCE = "Raw/Clark.pdf"
# First PDF page of each two-page table, then zero-based D/R candidate columns.
CONTESTS = {
    "us_senate": (17, 0, 1),
    "governor": (1, 0, 2),
    "attorney_general": (5, 1, 0),
    "auditor_of_state": (7, 0, 1),
    "secretary_of_state": (9, 1, 2),
    "treasurer_of_state": (11, 1, 0),
    "supreme_court_2027_01_01": (13, 1, 0),
    "supreme_court_2027_01_02": (15, 0, 1),
}
FIELDS = ["county", "precinct_code", "precinct_name", "canvass_type", "source_file",
          "source_pages", "graph_node_ids", "graph_match_status"]
FIELDS += [f"{race}_{party}" for race in CONTESTS for party in ("dem", "rep")]
ROW = re.compile(r"^Precinct (\d{3}) (.+?) {2,}\d+ +\d+ +\d+ +(.+)$", re.MULTILINE)
VOTES = re.compile(r"(\d+) +\d+(?:\.\d+)?%")


# County GIS overlaps with 2020 Census voting districts, as sourced in the TXT.
HISTORICAL = {
    "CITY 1": ("CITY 1", "CITY 21"),
    "CITY 3": ("CITY 3", "CITY 2"),
    "CITY 4": ("CITY 4", "CITY 3"),
    "CITY 5": ("CITY 5", "CITY 18", "CITY 9", "CITY 6"),
    "CITY 6": ("CITY 7", "CITY 6"),
    "CITY 7": ("CITY 7", "CITY 12", "CITY 8", "T-4", "T-3"),
    "CITY 8": ("CITY 10", "CITY 8", "CITY 12", "CITY 9"),
    "CITY 9": ("CITY 9", "CITY 10", "CITY 13", "CITY 18"),
    "CITY 10": ("CITY 13", "CITY 12", "CITY 16", "CITY 15"),
    "CITY 11": ("CITY 15", "CITY 16", "CITY 17", "CITY 13"),
    "CITY 12": ("CITY 15", "CITY 25", "CITY 16", "CITY 17"),
    "CITY 13": ("CITY 18", "CITY 24", "CITY 25"),
    "CITY 14": ("CITY 29", "CITY 30", "CITY 25", "CITY 24"),
    "CITY 15": ("CITY 26", "CITY 27", "CITY 28"),
    "CITY 16": ("CITY 28", "CITY 31"),
    "CITY 17": ("CITY 26", "CITY 31", "CITY 27"),
    "CITY 18": ("CITY 32", "MFLD 1", "CITY 31", "CITY 26", "CITY 35"),
    "CITY 19": ("CITY 33", "CITY 32"),
    "CITY 20": ("CITY 34", "CITY 35", "CITY 36"),
    "CITY 21": ("CITY 11",),
    "CITY 22": ("CITY 37", "CITY 11", "CITY 36"),
    "CITY 23": ("CITY 30", "CITY 34", "CITY 18", "CITY 37", "CITY 36"),
    "CITY 24": ("CITY 23", "CITY 18", "CITY 22", "CITY 30"),
    "CITY 25": ("CITY 20", "CITY 19", "CITY 21", "CITY 18", "CITY 22"),
    "CITY 26": ("CITY 1", "CITY 21", "CITY 22"),
    "CITY 27": ("CITY 14",),
    "CARL 1": ("CARL 1", "CARL 2"),
    "CARL 4": ("CARL 1", "BETH 7"),
    "CARL 5": ("CARL 1",),
    "BETH 1": ("BETH 1", "BETH 3", "MR-1", "BETH 9"),
    "BETH 2": ("BETH 2", "BETH 9"),
    "BETH 3": ("BETH 8", "BETH 9", "BETH 2"),
    "BETH 4": ("BETH 7", "BETH 8", "BETH 4", "BETH 3"),
    "BETH 5": ("BETH 4", "BETH 6", "BETH 5"),
    "BETH 6": ("BETH 5", "BETH 7", "BETH 6"),
    "GERM 1": ("GERM 1", "GERM 2"),
    "GERM 3": ("GERM 3", "GERM 4"),
    "GERM 5": ("GERM 5", "GERM 4"),
    "HARM 1": ("HARM 1", "HARM 2"),
    "HARM 2": ("HARM 2", "HARM 1"),
    "MR - 1": ("MR-1", "MR-2"),
    "MR - 4": ("MR-4", "MR-6", "MR-5"),
    "MFLD 1": ("MFLD 6", "MFLD 1", "MFLD 2", "GERM 2"),
    "MFLD 2": ("MFLD 4", "MFLD 2", "MFLD 8"),
    "MFLD 4": ("MFLD 4", "MFLD 2", "MFLD 8"),
    "MFLD 5": ("MFLD 5", "MFLD 4"),
    "MFLD 6": ("MFLD 9", "MFLD 6"),
    "MFLD 7": ("MFLD 10", "MFLD 9"),
    "MFLD 8": ("MFLD 7", "MFLD 8", "MFLD 10", "MFLD 6"),
    "MFLD 9": ("MFLD 1",),
    "PIKE 1": ("PIKE 1", "PIKE 2"),
    "T - 2": ("T-2", "GERM 2"),
    "T - 3": ("T-3", "T-4"),
    "T - 4": ("T-4", "GREE 1"),
    "T - 5": ("T-6", "T-5"),
    "T - 6": ("T-6", "T-7", "HARM 1"),
    "T - 8": ("T-8", "T-6", "HARM 1", "T-7"),
}
SINGLE_PREDECESSOR_STATUS = {
    "CITY 21": "split_precinct",
    "CITY 27": "renamed",
    "CARL 5": "split_precinct",
    "MFLD 9": "split_precinct",
}


def extract(root, output):
    pdf = PdfReader(root / SOURCE)
    tables = []
    for first_page, dem, rep in CONTESTS.values():
        table = {}
        for page in (first_page, first_page + 1):
            layout = pdf.pages[page - 1].extract_text(extraction_mode="layout")
            for code, name, cells in ROW.findall(layout):
                counts = VOTES.findall(cells)
                table[code, name] = (page, int(counts[dem]), int(counts[rep]))
        tables.append(table)

    graph = json.loads((root / "OH_pct20.json").read_text(encoding="utf-8"))
    by_name = defaultdict(list)
    for node in graph["nodes"]:
        if node["COUNTY"] == "CLARK":
            members = node["ORIG_NAME"].split(",")
            for member in members:
                by_name[member.removesuffix("_CLARK")].append((node["id"], len(members)))

    with output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(FIELDS)
        for code, name in sorted(tables[0]):
            key = name.replace(" - ", "-")
            predecessors = HISTORICAL.get(name, (key,))
            matches = [match for predecessor in predecessors for match in by_name[predecessor]]
            if name in HISTORICAL:
                status = SINGLE_PREDECESSOR_STATUS.get(name, "boundary_overlap")
            elif len(matches) > 1:
                status = "split_nodes"
            elif not matches:
                status = "unmatched"
            elif matches[0][1] > 1:
                status = "combined_node"
            else:
                status = "exact" if name == key else "normalized"
            pages, votes = [], []
            for table in tables:
                page, dem, rep = table[code, name]
                pages.append(page)
                votes.extend((dem, rep))
            writer.writerow(["Clark", code, name, "official", SOURCE,
                             ",".join(map(str, sorted(pages))),
                             ";".join(str(node_id) for node_id, _ in sorted(set(matches))),
                             status, *votes])


if __name__ == "__main__":
    folder = Path(__file__).resolve().parent
    extract(folder.parents[1], folder / "precinct_votes.csv")

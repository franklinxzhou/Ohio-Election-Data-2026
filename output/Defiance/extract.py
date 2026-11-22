#!/usr/bin/env python3
"""Extract Defiance's official precinct returns with Python 3 and pypdf."""

import csv
import json
import re
from collections import defaultdict
from pathlib import Path

from pypdf import PdfReader

SOURCE = "Raw/Defiance.pdf"
# First PDF page of each four-page contest and zero-based D/R columns.
CONTESTS = {
    "us_senate": (29, 0, 1),
    "governor": (1, 0, 2),
    "attorney_general": (5, 1, 0),
    "auditor_of_state": (9, 0, 1),
    "secretary_of_state": (13, 1, 2),
    "treasurer_of_state": (17, 1, 0),
    "supreme_court_2027_01_01": (21, 1, 0),
    "supreme_court_2027_01_02": (25, 0, 1),
}
FIELDS = ["county", "precinct_code", "precinct_name", "canvass_type", "source_file",
          "source_pages", "graph_node_ids", "graph_match_status"]
FIELDS += [f"{contest}_{party}" for contest in CONTESTS for party in ("dem", "rep")]
PRECINCT = re.compile(r"(\d{3}) (.+)")
MODE = re.compile(r"^(Normal|Absentee|Provisional) +\d+ +\d+ +(.+)$")
VOTES = re.compile(r"(\d+) +(?:[\d.]+%|-)(?=\s|$)")


def read_contest(pdf, first, dem, rep):
    modes = defaultdict(dict)
    pages = defaultdict(set)
    precinct = None
    for page in range(first, first + 4):
        for line in pdf.pages[page - 1].extract_text(extraction_mode="layout").splitlines():
            line = line.strip()
            if line == "Total":
                return modes, pages
            if match := PRECINCT.fullmatch(line):
                precinct = match.groups()
            elif precinct and (match := MODE.match(line)):
                mode, cells = match.groups()
                if mode in modes[precinct]:
                    raise ValueError(f"Duplicate {mode} for {precinct} on page {page}")
                counts = VOTES.findall(cells)
                modes[precinct][mode] = (int(counts[dem]), int(counts[rep]))
                pages[precinct].add(page)
    raise ValueError(f"Missing county totals heading for contest on page {first}")


def extract(root, output):
    pdf = PdfReader(root / SOURCE)
    tables = [read_contest(pdf, *contest) for contest in CONTESTS.values()]
    graph = json.loads((root / "OH_pct20.json").read_text(encoding="utf-8"))
    by_name = {}
    for node in graph["nodes"]:
        if node["COUNTY"] == "DEFIANCE":
            members = node["ORIG_NAME"].split(",")
            status = "combined_node" if len(members) > 1 else "exact"
            for member in members:
                by_name[member.removesuffix("_DEFIANCE")] = (node["id"], status)

    with output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(FIELDS)
        for precinct in tables[0][0]:
            code, name = precinct
            node_id, status = by_name[name]
            sources, counts = set(), []
            for votes, pages in tables:
                sources.update(pages[precinct])
                counts.extend(map(sum, zip(*votes[precinct].values())))
            writer.writerow(["Defiance", code, name, "official", SOURCE,
                             ",".join(map(str, sorted(sources))), node_id, status, *counts])


if __name__ == "__main__":
    folder = Path(__file__).resolve().parent
    extract(folder.parents[1], folder / "precinct_votes.csv")

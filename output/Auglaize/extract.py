#!/usr/bin/env python3
"""Extract Auglaize's November 9 unofficial precinct report with pypdf."""

import csv
import json
import re
from collections import defaultdict
from pathlib import Path

from pypdf import PdfReader

SOURCE = "Raw/Auglaize.pdf"
CONTESTS = {
    "For U.S. Senator (UTE 1-3-29)": "us_senate",
    "For Governor and Lieutenant Governor": "governor",
    "For Attorney General": "attorney_general",
    "For Auditor of State": "auditor_of_state",
    "For Secretary of State": "secretary_of_state",
    "For Treasurer of State": "treasurer_of_state",
    "For Justice of the Supreme Court (1-1-27)": "supreme_court_2027_01_01",
    "For Justice of the Supreme Court (1-2-27)": "supreme_court_2027_01_02",
}
VOTE_COLUMNS = [f"{contest}_{party}" for contest in CONTESTS.values() for party in ("dem", "rep")]
METADATA = ["county", "precinct_code", "precinct_name", "canvass_type", "source_file",
            "source_pages", "graph_node_ids", "graph_match_status"]
CANDIDATE = re.compile(r"(Dem|Rep) .+?\s{2,}([\d,]+)(?=\s)")

# Current county GIS boundaries compared with 2020 Census voting districts.
# Sources and overlap estimates are in precinct_merges_splits.txt.
CHANGES = {
    "0280": ("boundary_overlap", ("ST. MARYS E", "ST. MARYS W")),
    "0310": ("split_precinct", ("UNION",)),
    "0315": ("split_precinct", ("UNION",)),
    "0395": ("split_precinct", ("NEW BREMEN E",)),
}


def extract(root, output):
    precincts = {}
    for number, page in enumerate(PdfReader(root / SOURCE).pages, 1):
        lines = page.extract_text(extraction_mode="layout").splitlines()
        if "UNOFFICIAL RESULTS" not in lines[0]:
            raise ValueError(f"Unexpected report status on page {number}")
        code, name = lines[3].strip().split(maxsplit=1)
        votes, pages = precincts.setdefault((code, name), ({}, set()))
        contest = None
        for line in map(str.strip, lines[4:]):
            if line.startswith("For "):
                contest = CONTESTS.get(line)
            if line.startswith("Overvotes"):
                contest = None
            if contest and (candidate := CANDIDATE.match(line)):
                party, total = candidate.groups()
                column = f"{contest}_{party.lower()}"
                if column in votes:
                    raise ValueError(f"Duplicate {column} for {code} {name} on page {number}")
                votes[column] = int(total.replace(",", ""))
                pages.add(number)

    graph = json.loads((root / "OH_pct20.json").read_text(encoding="utf-8"))
    by_name = defaultdict(list)
    for node in graph["nodes"]:
        if node["COUNTY"] == "AUGLAIZE":
            members = node["ORIG_NAME"].split(",")
            for member in members:
                by_name[member.removesuffix("_AUGLAIZE")].append((node["id"], len(members)))

    rows = []
    for (code, name), (votes, pages) in precincts.items():
        if missing := set(VOTE_COLUMNS) - votes.keys():
            raise ValueError(f"Missing {', '.join(sorted(missing))} for {code} {name}")
        status, historical = CHANGES.get(code, ("", (name.upper(),)))
        matches = [match for member in historical for match in by_name[member]]
        ids = sorted({node_id for node_id, _ in matches})
        if not status:
            if len(ids) == 1:
                status = "combined_node" if matches[0][1] > 1 else "exact"
            else:
                status = "split_nodes" if ids else "unmatched"
        rows.append(["Auglaize", code, name, "unofficial", SOURCE, f"{min(pages)}-{max(pages)}",
                     ";".join(map(str, ids)), status, *(votes[column] for column in VOTE_COLUMNS)])

    with output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(METADATA + VOTE_COLUMNS)
        writer.writerows(rows)


if __name__ == "__main__":
    folder = Path(__file__).resolve().parent
    extract(folder.parents[1], folder / "precinct_votes.csv")

#!/usr/bin/env python3
"""Extract Ashland's Official Canvass. Run with Python 3 and pypdf installed."""

import csv
import json
import re
from collections import defaultdict
from pathlib import Path

from pypdf import PdfReader

SOURCE = "Raw/Ashland.pdf"
# First PDF page and zero-based D/R token offsets after the counting-group label.
CONTESTS = {
    "us_senate": (57, 2, 4),
    "governor": (1, 5, 9),
    "attorney_general": (8, 7, 5),
    "auditor_of_state": (15, 5, 7),
    "secretary_of_state": (22, 7, 9),
    "treasurer_of_state": (29, 7, 5),
    "supreme_court_2027_01_01": (36, 7, 5),
    "supreme_court_2027_01_02": (43, 5, 7),
}
GROUPS = {"Election Day", "Early Voting", "Absentee", "Provisional"}
PRECINCT = re.compile(r"(\d{2})\s+([A-Za-z].*)")
COUNTING_ROW = re.compile(r"(Election Day|Early Voting|Absentee|Provisional)\s+(\d.*)")


def normalize(name):
    compact = " ".join(re.sub(r"\bTWP\b|#", "", name.upper()).split())
    return "PERRY 1" if compact == "PERRY" else compact


def extract(root, output):
    pdf = PdfReader(root / SOURCE)
    votes, pages = defaultdict(dict), defaultdict(set)
    for contest, (first, dem, rep) in CONTESTS.items():
        precinct = None
        for number in range(first, first + 6):
            for line in map(str.strip, pdf.pages[number - 1].extract_text(extraction_mode="layout").splitlines()):
                if line == "Total":
                    precinct = None
                if label := PRECINCT.fullmatch(line):
                    precinct = label.groups()
                if precinct and (record := COUNTING_ROW.fullmatch(line)):
                    group, numbers = record.groups()
                    fields = numbers.split()
                    counts = votes[precinct].setdefault(contest, {})
                    if group in counts:
                        raise ValueError(f"Duplicate {group} for {precinct}, {contest}")
                    counts[group] = tuple(int(fields[i].replace(",", "")) for i in (dem, rep))
                    pages[precinct].add(number)

    graph = json.loads((root / "OH_pct20.json").read_text(encoding="utf-8"))
    by_name = defaultdict(list)
    for node in graph["nodes"]:
        if node["COUNTY"] == "ASHLAND":
            names = [name.removesuffix("_ASHLAND") for name in node["ORIG_NAME"].split(",")]
            for name in names:
                by_name[normalize(name)].append((node["id"], name, len(names)))

    columns = ["county", "precinct_code", "precinct_name", "canvass_type", "source_file",
               "source_pages", "graph_node_ids", "graph_match_status"]
    columns += [f"{contest}_{party}" for contest in CONTESTS for party in ("dem", "rep")]
    rows = []
    for precinct, contests in sorted(votes.items()):
        code, name = precinct
        matches = by_name[normalize(name)]
        if len(matches) == 1:
            _, graph_name, size = matches[0]
            status = "combined_node" if size > 1 else "exact" if graph_name == name.upper() else "normalized"
        else:
            status = "ambiguous" if matches else "unmatched"
        totals = []
        for contest in CONTESTS:
            counts = contests.get(contest, {})
            if counts.keys() != GROUPS:
                raise ValueError(f"Missing counting groups for {precinct}, {contest}")
            totals.extend(map(sum, zip(*counts.values())))
        rows.append(["Ashland", code, name, "official", SOURCE,
                     ";".join(map(str, sorted(pages[precinct]))),
                     ";".join(str(node_id) for node_id, _, _ in matches), status, *totals])

    with output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(columns)
        writer.writerows(rows)


if __name__ == "__main__":
    folder = Path(__file__).resolve().parent
    extract(folder.parents[1], folder / "precinct_votes.csv")

#!/usr/bin/env python3
"""Extract the Hocking precinct workbook with the documented graph crosswalk."""

import csv
import json
from collections import defaultdict
from pathlib import Path

from openpyxl import load_workbook

SOURCE = "Raw/Hocking.xlsx"
RACES = {
    "3": "us_senate",
    "9": "governor",
    "12": "attorney_general",
    "15": "auditor_of_state",
    "18": "secretary_of_state",
    "21": "treasurer_of_state",
    "24": "supreme_court_2027_01_01",
    "27": "supreme_court_2027_01_02",
}
PARTIES = {"Democratic": "dem", "Republican": "rep"}
OVERLAPS = {
    "LOGAN 2": ("LOGAN 2", "LOGAN 4"),
    "LOGAN 3": ("FALLS 3", "LOGAN 3"),
    "LOGAN 4": ("LOGAN 2", "LOGAN 3", "LOGAN 4"),
}


def extract(root, output):
    votes = defaultdict(dict)
    workbook = load_workbook(root / SOURCE, read_only=True, data_only=True)
    try:
        for precinct, _, contest, candidate, _, party, total, *_ in workbook[
            "Precinct Results"
        ].iter_rows(min_row=2, values_only=True):
            if contest in RACES and party in PARTIES and candidate.lower() != "write-in":
                field = f"{RACES[contest]}_{PARTIES[party]}"
                if field in votes[precinct]:
                    raise ValueError(f"Duplicate {field} for {precinct}")
                votes[precinct][field] = total
    finally:
        workbook.close()

    graph = json.loads((root / "OH_pct20.json").read_text(encoding="utf-8"))
    nodes = {
        member.removesuffix("_HOCKING"): node["id"]
        for node in graph["nodes"]
        if node["COUNTY"] == "HOCKING"
        for member in node["ORIG_NAME"].split(",")
    }
    fields = [f"{race}_{party}" for race in RACES.values() for party in PARTIES.values()]
    with output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow([
            "county", "precinct_code", "precinct_name", "canvass_type", "source_file",
            "source_pages", "graph_node_ids", "graph_match_status", *fields,
        ])
        for precinct, counts in sorted(votes.items()):
            code, name = precinct.split(" ", 1)
            if name in OVERLAPS:
                members, status = OVERLAPS[name], "boundary_overlap"
            elif name == "WARD":
                members, status = ("CARBON HILL", "MURRAY CITY"), "merged_precinct"
            elif name == "SALTCREEK":
                members, status = ("SALT CREEK",), "normalized"
            elif name in {"FALLS 2", "MARION 2"}:
                members, status = (name,), "combined_node"
            else:
                members, status = (name,), "exact"
            node_ids = ";".join(map(str, sorted({nodes[member] for member in members})))
            writer.writerow([
                "Hocking", code, name, "unofficial", SOURCE, "", node_ids, status,
                *(counts[field] for field in fields),
            ])


if __name__ == "__main__":
    folder = Path(__file__).resolve().parent
    extract(folder.parents[1], folder / "precinct_votes.csv")

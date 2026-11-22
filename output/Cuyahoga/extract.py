#!/usr/bin/env python3
"""Extract the Cuyahoga unofficial precinct export using Python 3."""

import csv
import json
import re
from collections import defaultdict
from pathlib import Path

SOURCE = "Raw/Cuyahoga.csv"
# Contest ID, Democratic choice ID, Republican choice ID.
RACES = {
    "us_senate": ("6", "13", "14"),
    "governor": ("1", "1", "3"),
    "attorney_general": ("2", "5", "4"),
    "auditor_of_state": ("3", "6", "7"),
    "secretary_of_state": ("4", "9", "10"),
    "treasurer_of_state": ("5", "12", "11"),
    "supreme_court_2027_01_01": ("9", "21", "20"),
    "supreme_court_2027_01_02": ("10", "22", "23"),
}
FIELDS = ["county", "precinct_code", "precinct_name", "canvass_type", "source_file",
          "source_pages", "graph_node_ids", "graph_match_status"]
CANDIDATES = {
    (contest, choice): f"{race}_{party}"
    for race, (contest, dem, rep) in RACES.items()
    for party, choice in (("dem", dem), ("rep", rep))
}
BOUNDARY_HEADER = "Current precinct | Status | Graph IDs | Historical precincts and area shares"


def key(name):
    return re.sub(r"\s*-\s*", "-", name.strip().upper())


def graph_members(root):
    graph = json.loads((root / "OH_pct20.json").read_text(encoding="utf-8"))
    for node in graph["nodes"]:
        if node["COUNTY"] == "CUYAHOGA":
            members = tuple(member.removesuffix("_CUYAHOGA") for member in node["ORIG_NAME"].split(","))
            yield node["id"], members, node["ENACTED_LOWER"]


def extract(root, output):
    votes = defaultdict(dict)
    names = {}
    with (root / SOURCE).open(encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            field = CANDIDATES.get((row["ContestId"], row["ChoiceId"]))
            if field is None:
                continue
            code, name = row["PrecinctId"], row["PrecinctName"]
            if names.setdefault(code, name) != name or field in votes[code]:
                raise ValueError(f"Conflicting row for precinct {code}, {field}")
            votes[code][field] = int(row["Total"])

    by_name = defaultdict(list)
    for node_id, members, _ in graph_members(root):
        for member in members:
            by_name[member].append((node_id, len(members)))

    notes = (output.parent / "precinct_merges_splits.txt").read_text(encoding="utf-8")
    _, _, records = notes.partition(BOUNDARY_HEADER + "\n")
    overrides = {}
    for line in records.splitlines():
        label, status, nodes, _ = line.split(" | ", 3)
        overrides[label] = (nodes, status)

    with output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow([*FIELDS, *CANDIDATES.values()])
        for code, counts in votes.items():
            label = key(names[code])
            if label in overrides:
                nodes, status = overrides[label]
            else:
                matches = sorted(by_name[label])
                if len(matches) > 1:
                    status = "split_nodes"
                else:
                    status = "exact" if names[code].upper() == label else "normalized"
                    if matches[0][1] > 1:
                        status = "combined_node"
                nodes = ";".join(str(node_id) for node_id, _ in matches)
            writer.writerow(["Cuyahoga", code, names[code], "unofficial", SOURCE, "",
                             nodes, status, *(counts[column] for column in CANDIDATES.values())])


if __name__ == "__main__":
    folder = Path(__file__).resolve().parent
    extract(folder.parents[1], folder / "precinct_votes.csv")

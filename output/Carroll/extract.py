#!/usr/bin/env python3
"""Extract Carroll's official precinct CSV and link it to the 2020 graph."""

import csv
import json
from collections import defaultdict
from pathlib import Path

SOURCE = "Raw/Carroll.csv"
RACES = [
    ("us_senate", "United States Senator (Unexpired term)", "Sherrod Brown", "Jon Husted"),
    ("governor", "Governor/ Lt. Governor", "Amy Acton and David Pepper", "Vivek Ramaswamy and Robert A. McColley"),
    ("attorney_general", "Attorney General", "John J. Kulewicz", "Keith Faber"),
    ("auditor_of_state", "Auditor Of State", "Annette Blackwell", "Frank LaRose"),
    ("secretary_of_state", "Secretary Of State", "Allison Russo", "Robert Sprague"),
    ("treasurer_of_state", "Treasurer Of State", "Seth Walsh", "Jay Edwards"),
    ("supreme_court_2027_01_01", "Justice Of The Supreme Court 1/1/27", "Marilyn Zayas", "Daniel R. Hawkins"),
    ("supreme_court_2027_01_02", "Justice Of The Supreme Court 1/2/27", "Jennifer Brunner", "Colleen O'Donnell"),
]
METADATA = ["county", "precinct_code", "precinct_name", "canvass_type", "source_file",
            "source_pages", "graph_node_ids", "graph_match_status"]
CANDIDATES = {
    (contest, name): f"{race}_{party}"
    for race, contest, dem, rep in RACES
    for party, name in (("dem", dem), ("rep", rep))
}


def extract(root, output):
    votes = defaultdict(dict)
    with (root / SOURCE).open(encoding="utf-8-sig", newline="") as file:
        if [next(file).strip() for _ in range(2)] != ["Official Election Results", "Carroll County"]:
            raise ValueError("Unexpected Carroll canvass header")
        for row in csv.DictReader(file):
            counts = votes[row["Precinct"]]
            if field := CANDIDATES.get((row["Contest Name"], row["Candidate Name"])):
                if field in counts:
                    raise ValueError(f"Duplicate {field} for {row['Precinct']}")
                counts[field] = int(row["Votes"].replace(",", ""))

    graph = json.loads((root / "OH_pct20.json").read_text(encoding="utf-8"))
    matches = {}
    for node in graph["nodes"]:
        if node["COUNTY"] != "CARROLL":
            continue
        members = node["ORIG_NAME"].split(",")
        for member in members:
            historical = member.removesuffix("_CARROLL")
            current = historical.replace(" TWP", "")
            if historical == "MINERVA A":
                current = "MINERVA"
            status = "exact" if current == historical else "normalized"
            if len(members) > 1:
                status = "combined_node"
            if current in matches:
                raise ValueError(f"Multiple graph links for {current}")
            matches[current] = (node["id"], status)

    with output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow([*METADATA, *CANDIDATES.values()])
        for label, counts in votes.items():
            name, code = label.rsplit(" ", 1)
            node_id, status = matches[name]
            writer.writerow(["Carroll", code, name, "official", SOURCE, "", node_id, status,
                             *(counts[field] for field in CANDIDATES.values())])


if __name__ == "__main__":
    folder = Path(__file__).resolve().parent
    extract(folder.parents[1], folder / "precinct_votes.csv")

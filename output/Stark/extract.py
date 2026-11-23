#!/usr/bin/env python3
"""Read the Stark unofficial precinct export and attach the graph links."""

import csv
from collections import defaultdict
from pathlib import Path

SOURCE = "Raw/Stark.csv"
RACES = [
    ("us_senate", "U.S. Senator (UTE 1-3-2029)", "Sherrod Brown", "Jon Husted"),
    ("governor", "Governor and Lieutenant Governor", "Amy Acton and David Pepper",
     "Vivek Ramaswamy and Robert A. McColley"),
    ("attorney_general", "Attorney General", "John J. Kulewicz", "Keith Faber"),
    ("auditor_of_state", "Auditor of State", "Annette Blackwell", "Frank LaRose"),
    ("secretary_of_state", "Secretary of State", "Allison Russo", "Robert Sprague"),
    ("treasurer_of_state", "Treasurer of State", "Seth Walsh", "Jay Edwards"),
    ("supreme_court_2027_01_01", "Justice of the Supreme Court (1-1-2027)",
     "Marilyn Zayas", "Daniel R. Hawkins"),
    ("supreme_court_2027_01_02", "Justice of the Supreme Court (1-2-2027)",
     "Jennifer Brunner", "Colleen O'Donnell"),
]
FIELDS = {
    (contest, name): f"{race}_{party}"
    for race, contest, dem, rep in RACES
    for party, name in (("dem", dem), ("rep", rep))
}


def extract(root, folder):
    votes = defaultdict(dict)
    with (root / SOURCE).open(encoding="utf-8-sig", newline="") as file:
        next(file)
        next(file)
        for row in csv.DictReader(file):
            if field := FIELDS.get((row["Contest Name"], row["Candidate Name"])):
                code = row["Precinct"]
                if field in votes[code]:
                    raise ValueError(f"Duplicate {field} for {code}")
                votes[code][field] = int(row["Votes"])

    notes = (folder / "precinct_merges_splits.txt").read_text()
    links = {}
    for line in notes.split("\nCrosswalk rows\n", 1)[1].splitlines():
        code, name, status, ids, _ = line.split(" | ")
        links[code] = name, status, ids
    if links.keys() != votes.keys():
        raise ValueError("County map codes and vote export codes differ")

    with (folder / "precinct_votes.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow([
            "county", "precinct_code", "precinct_name", "canvass_type", "source_file",
            "source_pages", "graph_node_ids", "graph_match_status", *FIELDS.values(),
        ])
        for code, counts in votes.items():
            name, status, ids = links[code]
            writer.writerow([
                "Stark", code, name, "unofficial", SOURCE, "", ids, status,
                *(counts[field] for field in FIELDS.values()),
            ])


if __name__ == "__main__":
    folder = Path(__file__).resolve().parent
    extract(folder.parents[1], folder)

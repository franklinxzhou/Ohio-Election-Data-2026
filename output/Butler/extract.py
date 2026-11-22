#!/usr/bin/env python3
"""Extract Butler's November 3 unofficial precinct export with Python 3."""

import csv
import json
import re
from collections import defaultdict
from pathlib import Path

SOURCE = "Raw/Butler.csv"
RACES = [
    ("us_senate", "UNITED STATES SENATOR UTE 1-3-2029", ("Sherrod Brown", "Jon Husted")),
    ("governor", "GOVERNOR STATE OF OHIO", ("Amy Acton and David Pepper", "Vivek Ramaswamy and Robert A. McColley")),
    ("attorney_general", "ATTORNEY GENERAL STATE OF OHIO", ("John J. Kulewicz", "Keith Faber")),
    ("auditor_of_state", "AUDITOR OF STATE STATE OF OHIO", ("Annette Blackwell", "Frank LaRose")),
    ("secretary_of_state", "SECRETARY OF STATE STATE OF OHIO", ("Allison Russo", "Robert Sprague")),
    ("treasurer_of_state", "TREASURER OF STATE STATE OF OHIO", ("Seth Walsh", "Jay Edwards")),
    ("supreme_court_2027_01_01", "SUPREME COURT JUSTICE  1-1-2027", ("Marilyn Zayas", "Daniel R. Hawkins")),
    ("supreme_court_2027_01_02", "SUPREME COURT JUSTICE  1-2-2027", ("Jennifer Brunner", "Colleen O'Donnell")),
]
FIELDS = ["county", "precinct_code", "precinct_name", "canvass_type", "source_file",
          "source_pages", "graph_node_ids", "graph_match_status"]
VOTE_FIELDS = [f"{race}_{party}" for race, _, _ in RACES for party in ("dem", "rep")]
CANDIDATES = {
    (contest, name): f"{race}_{party}"
    for race, contest, names in RACES for party, name in zip(("dem", "rep"), names)
}
# Geographic links from the county's map and the 2020 Census voting districts.
# The sourced TXT record lists the estimated area shares.
HISTORICAL = {
    "LIBERTY26": ("LIBERTY6",),
    "LIBERTY27": ("LIBERTY2", "LIBERTY3"),
    "LIBERTY28": ("LIBERTY3",),
    "LIBERTY29": ("LIBERTY11",),
    "LIBERTY30": ("LIBERTY11",),
    "LIBERTY31": ("LIBERTY20", "LIBERTY24"),
    "MADISON6": ("MADISON2", "MIDD6WD1"),
    "MADISON7": ("MADISON4",),
    "MONROE10": ("MONROE4",),
    "MONROE11": ("MONROE2", "MONROE9", "MONROE1"),
}


def key(name):
    for city, short in (("FAIRFIELD", "FAIR"), ("HAMILTON", "HAM"), ("MIDDLETOWN", "MIDD")):
        if match := re.fullmatch(rf"{city} PT(\d+) WD(\d+)", name):
            return f"{short}{match[1]}WD{match[2]}"
    for town, short in (("FAIRFIELD TWP", "FFTWP"), ("OXFORD TWP", "OXTWP"),
                        ("ST. CLAIR TWP", "STCLAIR"), ("WEST CHESTER TWP", "WC"),
                        ("SHARONVILLE", "SHARON")):
        if match := re.fullmatch(rf"{re.escape(town)} (\d+)", name):
            return short + match[1]
    return name.replace(" TWP ", " ").replace(" ", "")


def extract(root, output):
    votes = defaultdict(dict)
    with (root / SOURCE).open(encoding="utf-8-sig", newline="") as file:
        if next(file).strip() != "UNOFFICIAL ELECTION RESULTS" or next(file).strip() != "Butler County":
            raise ValueError("Unexpected Butler canvass header")
        for row in csv.DictReader(file):
            precinct = row["Precinct"]
            counts = votes[precinct]
            if column := CANDIDATES.get((row["Contest Name"], row["Candidate Name"])):
                if column in counts:
                    raise ValueError(f"Duplicate {column} for {precinct}")
                counts[column] = int(row["Votes"].replace(",", ""))

    graph = json.loads((root / "OH_pct20.json").read_text(encoding="utf-8"))
    by_code = defaultdict(list)
    for node in graph["nodes"]:
        if node["COUNTY"] == "BUTLER":
            members = node["ORIG_NAME"].split(",")
            for member in members:
                by_code[key(member.removesuffix("_BUTLER"))].append((node["id"], len(members)))

    with output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(FIELDS + VOTE_FIELDS)
        for code, counts in votes.items():
            if missing := set(VOTE_FIELDS) - counts.keys():
                raise ValueError(f"Missing {', '.join(sorted(missing))} for {code}")
            predecessors = HISTORICAL.get(code, (code,))
            matches = [match for predecessor in predecessors for match in by_code[predecessor]]
            if code in HISTORICAL:
                status = "split_precinct" if len(predecessors) == 1 else "boundary_overlap"
            elif len(matches) == 1:
                status = "combined_node" if matches[0][1] > 1 else "normalized"
            else:
                status = "split_nodes" if matches else "unmatched"
            writer.writerow(["Butler", code, code, "unofficial", SOURCE, "",
                             ";".join(map(str, sorted({node_id for node_id, _ in matches}))), status,
                             *(counts[column] for column in VOTE_FIELDS)])


if __name__ == "__main__":
    folder = Path(__file__).resolve().parent
    extract(folder.parents[1], folder / "precinct_votes.csv")

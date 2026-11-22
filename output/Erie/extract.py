#!/usr/bin/env python3
"""Extract Erie's official precinct returns with Python 3 and pypdf."""

import csv
import json
import re
from collections import defaultdict
from pathlib import Path

from pypdf import PdfReader

SOURCE = "Raw/Erie.pdf"
RACES = {
    "us_senate": ("Sherrod Brown", "Jon Husted"),
    "governor": ("Amy Acton and David Pepper", "Vivek Ramaswamy and Robert A. McColley"),
    "attorney_general": ("John J. Kulewicz", "Keith Faber"),
    "auditor_of_state": ("Annette Blackwell", "Frank LaRose"),
    "secretary_of_state": ("Allison Russo", "Robert Sprague"),
    "treasurer_of_state": ("Seth Walsh", "Jay Edwards"),
    "supreme_court_2027_01_01": ("Marilyn Zayas", "Daniel R. Hawkins"),
    "supreme_court_2027_01_02": ("Jennifer Brunner", "Colleen O'Donnell"),
}
VILLAGES = {
    "BER VILL": "BERLIN HEIGHTS VILLAGE",
    "KI VILL": "KELLEYS ISLAND VILLAGE",
    "BV VILL": "BAY VIEW VILLAGE",
    "CAST VILL": "CASTALIA VILLAGE",
    "MIL VILL": "MILAN VILL",
}
TOWNSHIPS = {
    "BER": "BERLIN", "FLO": "FLORENCE", "GRO": "GROTON",
    "HUR": "HURON", "MAR": "MARGARETTA", "MIL": "MILAN",
    "OX": "OXFORD", "PER": "PERKINS", "VER": "VERMILION",
}
FIELDS = ["county", "precinct_code", "precinct_name", "canvass_type", "source_file",
          "source_pages", "graph_node_ids", "graph_match_status"]
CANDIDATES = [f"{party} {name}" for dem, rep in RACES.values()
              for party, name in (("DEM", dem), ("REP", rep))]
FIELDS += [f"{race}_{party}" for race in RACES for party in ("dem", "rep")]
VOTE = re.compile(r"^ *(" + "|".join(map(re.escape, CANDIDATES)) + r") {2,}([\d,]+) +[\d.]+%",
                  re.MULTILINE)


def graph_name(name):
    if name in VILLAGES:
        return VILLAGES[name]
    prefix, _, suffix = name.partition(" ")
    if suffix.startswith("TWP") or prefix == "VER":
        return f"{TOWNSHIPS[prefix]} {suffix}"
    return name


def extract(root, output):
    votes = defaultdict(dict)
    pages = defaultdict(set)
    for page, contents in enumerate(PdfReader(root / SOURCE).pages, 1):
        layout = contents.extract_text(extraction_mode="layout")
        precinct = tuple(layout.splitlines()[4].strip().split(" ", 1))
        for candidate, count in VOTE.findall(layout):
            if candidate in votes[precinct]:
                raise ValueError(f"Duplicate {candidate} for {precinct}")
            votes[precinct][candidate] = int(count.replace(",", ""))
            pages[precinct].add(page)

    graph = json.loads((root / "OH_pct20.json").read_text(encoding="utf-8"))
    by_name = {}
    for node in graph["nodes"]:
        if node["COUNTY"] == "ERIE":
            members = node["ORIG_NAME"].split(",")
            for member in members:
                by_name[member.removesuffix("_ERIE")] = (node["id"], len(members))

    with output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(FIELDS)
        for precinct, counts in votes.items():
            code, name = precinct
            lookup = graph_name(name)
            node_id, size = by_name[lookup]
            status = "combined_node" if size > 1 else "exact" if name == lookup else "normalized"
            writer.writerow(["Erie", code, name, "official", SOURCE,
                             ",".join(map(str, sorted(pages[precinct]))), node_id, status,
                             *(counts[candidate] for candidate in CANDIDATES)])


if __name__ == "__main__":
    folder = Path(__file__).resolve().parent
    extract(folder.parents[1], folder / "precinct_votes.csv")

#!/usr/bin/env python3
"""Extract Licking's unofficial statewide precinct totals from its canvass."""

import csv
import json
import re
from collections import defaultdict
from pathlib import Path

from pypdf import PdfReader

SOURCE = "Raw/Licking.pdf"
RACES = [
    ("us_senate", "Sherrod Brown", "Jon Husted"),
    ("governor", "Amy Acton and David Pepper", "Vivek Ramaswamy and Robert A. McColley"),
    ("attorney_general", "John J. Kulewicz", "Keith Faber"),
    ("auditor_of_state", "Annette Blackwell", "Frank LaRose"),
    ("secretary_of_state", "Allison Russo", "Robert Sprague"),
    ("treasurer_of_state", "Seth Walsh", "Jay Edwards"),
    ("supreme_court_2027_01_01", "Marilyn Zayas", "Daniel R. Hawkins"),
    ("supreme_court_2027_01_02", "Jennifer Brunner", "Colleen O'Donnell"),
]
FIELDS = {
    candidate: f"{race}_{party}"
    for race, dem, rep in RACES for party, candidate in (("dem", dem), ("rep", rep))
}
PRECINCT = re.compile(r"^November 3, 2026 General Election +Licking County, Ohio\s+([^\n]+)", re.MULTILINE)
CANDIDATE = re.compile(r"^([^\n]+?) {2,}([\d,]+) +\d+\.\d+%", re.MULTILINE)
ALIASES = {
    "EDEN FALL TWP": "EDEN FALLSBURY TWP",
    "HARRISON TWP B-KIRK": "HARRISON TWP B",
    "HARTFORD TWP-VLG": "HARTFORD TWP",
    "HOPEWELL TWP-GRATIOT VLG": "HOPEWELL TWP/GRATIOT VLG",
    "NEWTON TWP B-ST LOU": "NEWTON TWP B",
    "ST. ALBANS TWP B-ALEX": "ST. ALBANS TWP B",
}


def graph_name(name):
    key = name.upper().replace("TOWNSHIP", "TWP").replace("VILLAGE", "VLG")
    if key.startswith("JOHNSTOWN "):
        key = key.replace("JOHNSTOWN ", "JOHNSTOWN VLG ", 1)
    return ALIASES.get(key, key)


def extract(root, output):
    votes, pages = defaultdict(dict), defaultdict(set)
    for number, page in enumerate(PdfReader(root / SOURCE).pages, 1):
        layout = page.extract_text(extraction_mode="layout")
        name = PRECINCT.search(layout)[1].strip()
        for label, count in CANDIDATE.findall(layout):
            if field := FIELDS.get(label):
                if field in votes[name]:
                    raise ValueError(f"Duplicate {field} for {name}")
                votes[name][field] = int(count.replace(",", ""))
                pages[name].add(number)

    graph = json.loads((root / "OH_pct20.json").read_text(encoding="utf-8"))
    matches = defaultdict(dict)
    for node in graph["nodes"]:
        if node["COUNTY"] == "LICKING":
            members = node["ORIG_NAME"].split(",")
            for member in members:
                matches[member.removesuffix("_LICKING")][node["id"]] = len(members) > 1

    with output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow([
            "county", "precinct_code", "precinct_name", "canvass_type", "source_file",
            "source_pages", "graph_node_ids", "graph_match_status", *FIELDS.values(),
        ])
        for name, counts in votes.items():
            key = graph_name(name)
            nodes = matches[key]
            if not nodes:
                raise ValueError(f"No graph match for {name}")
            ids = ";".join(map(str, sorted(nodes)))
            if len(nodes) > 1:
                status = "split_nodes"
            elif any(nodes.values()):
                status = "combined_node"
            else:
                status = "exact" if key == name.upper() else "normalized"
            writer.writerow([
                "Licking", "", name, "unofficial", SOURCE, ",".join(map(str, sorted(pages[name]))),
                ids, status, *(counts[field] for field in FIELDS.values()),
            ])


if __name__ == "__main__":
    folder = Path(__file__).resolve().parent
    extract(folder.parents[1], folder / "precinct_votes.csv")

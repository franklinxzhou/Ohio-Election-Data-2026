#!/usr/bin/env python3
"""Extract Lake's official precinct totals, reuniting ballot-style splits."""

import csv
import json
import re
from collections import defaultdict
from pathlib import Path

import pdfplumber

SOURCE = "Raw/Lake.pdf"
NOTES = "precinct_merges_splits.txt"
BOUNDARY_HEADER = "Mapped crosswalk exceptions"
RACES = [
    ("us_senate", "Sherrod Brown", "Jon Husted"),
    ("governor", "Amy Acton and David Pepper", "Vivek Ramaswamy and Robert A."),
    ("attorney_general", "John J. Kulewicz", "Keith Faber"),
    ("auditor_of_state", "Annette Blackwell", "Frank LaRose"),
    ("secretary_of_state", "Allison Russo", "Robert Sprague"),
    ("treasurer_of_state", "Seth Walsh", "Jay Edwards"),
    ("supreme_court_2027_01_01", "Marilyn Zayas", "Daniel R. Hawkins"),
    ("supreme_court_2027_01_02", "Jennifer Brunner", "Colleen O'Donnell"),
]
FIELDS = {
    label: f"{race}_{party}"
    for race, dem, rep in RACES for party, label in (("dem", dem), ("rep", rep))
}
CANDIDATE = re.compile(r"^(.+?) +([\d,]+) +\d+\.\d+%")
SPLIT_SUFFIXES = {
    "Concord Twp B": ("CHAR", "RLSD"),
    "Kirtland Hills AA": ("KIRT", "MENT"),
    "Painesville City 2B": ("PCTY", "RLSD"),
    "Painesville City 3B": ("PCTY", "RLSD"),
    "Painesville City 3C": ("PCTY", "RLSD"),
    "Waite Hill Village AA": ("KIRT", "WLEL"),
    "Willoughby City 3C": ("KIRT", "WLEL"),
}
PARENTS = {
    f"{base} {suffix}".upper(): base for base, suffixes in SPLIT_SUFFIXES.items()
    for suffix in suffixes
}


def graph_name(name):
    name = name.upper()
    name = name.replace("FAIRPORT HARBOR ", "FAIRPORT HBR ")
    name = name.replace("MENTOR-ON-THE-LAKE CITY ", "MENTOR-ON-THE-LAKE ")
    name = name.replace("WAITE HILL VILLAGE ", "WAITE HILL VLG ")
    if name.startswith("WILLOUGHBY HILLS ") and not name.startswith("WILLOUGHBY HILLS CITY "):
        name = name.replace("WILLOUGHBY HILLS ", "WILLOUGHBY HILLS CITY ", 1)
    return name


def graph_matches(root):
    nodes = json.loads((root / "OH_pct20.json").read_text(encoding="utf-8"))["nodes"]
    matches = defaultdict(dict)
    for node in nodes:
        if node["COUNTY"] == "LAKE":
            members = node["ORIG_NAME"].split(",")
            for member in members:
                matches[member.removesuffix("_LAKE")][node["id"]] = len(members) > 1
    return matches


def read_votes(source):
    votes, pages = defaultdict(dict), defaultdict(set)
    with pdfplumber.open(source) as pdf:
        for number, page in enumerate(pdf.pages, 1):
            # The same precinct header appears on every page. After the eight
            # statewide tables, later pages for that unit only have other races.
            name = page.crop((0, 0, page.width, 102)).extract_text().splitlines()[3].strip()
            if len(votes[name]) < len(FIELDS):
                for line in page.extract_text().splitlines():
                    match = CANDIDATE.match(line)
                    if match and (field := FIELDS.get(match[1])):
                        if field in votes[name]:
                            raise ValueError(f"Duplicate {field} for {name}")
                        votes[name][field] = int(match[2].replace(",", ""))
                        pages[name].add(number)
            page.close()
    return votes, pages


def extract(root, output):
    units, unit_pages = read_votes(root / SOURCE)
    precincts, pages = defaultdict(lambda: defaultdict(int)), defaultdict(set)
    for label, counts in units.items():
        name = PARENTS.get(label.upper(), label)
        for field in FIELDS.values():
            precincts[name][field] += counts[field]
        pages[name].update(unit_pages[label])

    matches = graph_matches(root)
    notes = (Path(__file__).resolve().parent / NOTES).read_text(encoding="utf-8")
    exceptions = {}
    for line in notes.split(BOUNDARY_HEADER + "\n", 1)[1].strip().splitlines():
        name, status, ids, _ = line.split(" | ")
        exceptions[name] = ids, status
    with output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow([
            "county", "precinct_code", "precinct_name", "canvass_type", "source_file",
            "source_pages", "graph_node_ids", "graph_match_status", *FIELDS.values(),
        ])
        for name, counts in precincts.items():
            key = graph_name(name)
            if key in exceptions:
                ids, status = exceptions[key]
            else:
                nodes = matches[key]
                ids = ";".join(map(str, sorted(nodes)))
                if len(nodes) > 1:
                    status = "split_nodes"
                elif any(nodes.values()):
                    status = "combined_node"
                else:
                    status = "exact" if key == name.upper() else "normalized"
            writer.writerow([
                "Lake", "", name, "official", SOURCE, ",".join(map(str, sorted(pages[name]))),
                ids, status, *(counts[field] for field in FIELDS.values()),
            ])


if __name__ == "__main__":
    folder = Path(__file__).resolve().parent
    extract(folder.parents[1], folder / "precinct_votes.csv")

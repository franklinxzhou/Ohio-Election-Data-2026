#!/usr/bin/env python3
"""Extract Clermont's unofficial precinct report with Python 3 and pypdf."""

import csv
import json
import re
from collections import defaultdict
from pathlib import Path

from pypdf import PdfReader

SOURCE = "Raw/Clermont.pdf"
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
FIELDS = ["county", "precinct_code", "precinct_name", "canvass_type", "source_file",
          "source_pages", "graph_node_ids", "graph_match_status"]
FIELDS += [f"{race}_{party}" for race in RACES for party in ("dem", "rep")]
CANDIDATES = [name for pair in RACES.values() for name in pair]
VOTE = re.compile(
    r"^ *(?:(?:Dem|Rep) )?(" + "|".join(map(re.escape, CANDIDATES)) + r") {2,}([\d,]+) +\d",
    re.MULTILINE,
)


# County GIS overlaps with the 2020 Census voting districts.
HISTORICAL = {
    "LOVELAND CITY A": ('LOVELAND CITY A', 'MIAMI TWP C'),
    "LOVELAND CITY B": ('LOVELAND CITY B', 'MIAMI TWP Y', 'MIAMI TWP L1L'),
    "LOVELAND CITY C": ('LOVELAND CITY B',),
    "BATAVIA VILLAGE A": ('BATAVIA VILLAGE A', 'BATAVIA TWP M', 'BATAVIA TWP H'),
    "BATAVIA TWP C": ('BATAVIA TWP C', 'WILLIAMSBURG TWP C'),
    "BATAVIA TWP M": ('BATAVIA TWP M', 'BATAVIA VILLAGE A'),
    "BATAVIA TWP O": ('BATAVIA TWP O', 'BATAVIA TWP F'),
    "BATAVIA TWP P": ('BATAVIA TWP C',),
    "FELICITY VILLAGE": ('FELICITY VILLAGE', 'FRANKLIN TWP D'),
    "JACKSON TWP B": ('JACKSON TWP B', 'WILLIAMSBURG TWP A'),
    "MILFORD CITY A": ('MILFORD CITY A', 'MIAMI TWP K'),
    "MILFORD CITY F": ('MILFORD CITY F', 'MIAMI TWP U'),
    "MILFORD CITY G": ('MILFORD CITY G', 'MIAMI TWP K'),
    "MILFORD CITY H": ('MILFORD CITY H', 'MIAMI TWP M'),
    "MIAMI TWP C": ('MIAMI TWP C', 'GOSHEN TWP N'),
    "MIAMI TWP M": ('MIAMI TWP M', 'MILFORD CITY H'),
    "MIAMI TWP U": ('MIAMI TWP U', 'MILFORD CITY H', 'MILFORD CITY F'),
    "NEW RICHMOND VILLAGE B": ('NEW RICHMOND VILLAGE B', 'OHIO TWP B'),
    "OHIO TWP B": ('OHIO TWP B', 'NEW RICHMOND VILLAGE A'),
    "OWENSVILLE VILLAGE": ('OWENSVILLE VILLAGE', 'STONELICK TWP A', 'STONELICK TWP E'),
    "STONELICK TWP E": ('STONELICK TWP E', 'JACKSON TWP C'),
    "BETHEL VILLAGE A": ('BETHEL VILLAGE A', 'TATE TWP D'),
    "BETHEL VILLAGE B": ('BETHEL VILLAGE B', 'TATE TWP H'),
    "UNION TWP B": ('UNION TWP B', 'UNION TWP J1J'),
    "UNION TWP N": ('UNION TWP N', 'UNION TWP W'),
    "UNION TWP P": ('UNION TWP P', 'PIERCE TWP J'),
    "UNION TWP Y": ('UNION TWP Y', 'UNION TWP J1J'),
    "WASHINGTON TWP A": ('WASHINGTON TWP A', 'FRANKLIN TWP D'),
    "WILLIAMSBURG VILLAGE A": ('WILLIAMSBURG VILLAGE A', 'WILLIAMSBURG TWP A'),
    "WILLIAMSBURG VILLAGE C": ('WILLIAMSBURG VILLAGE C', 'WILLIAMSBURG TWP B'),
}


def extract(root, output):
    totals = defaultdict(dict)
    pages = defaultdict(set)
    for number, page in enumerate(PdfReader(root / SOURCE).pages, 1):
        layout = page.extract_text(extraction_mode="layout")
        name = layout.splitlines()[4].strip()
        for candidate, count in VOTE.findall(layout):
            if candidate in totals[name]:
                raise ValueError(f"Duplicate count for {candidate} in {name}")
            totals[name][candidate] = int(count.replace(",", ""))
            pages[name].add(number)

    graph = json.loads((root / "OH_pct20.json").read_text(encoding="utf-8"))
    by_name = defaultdict(list)
    for node in graph["nodes"]:
        if node["COUNTY"] == "CLERMONT":
            members = node["ORIG_NAME"].split(",")
            for member in members:
                by_name[member.removesuffix("_CLERMONT")].append((node["id"], len(members)))

    with output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(FIELDS)
        for name, counts in totals.items():
            key = name.upper().replace(" TOWNSHIP ", " TWP ")
            predecessors = HISTORICAL.get(key, (key,))
            matches = [match for predecessor in predecessors for match in by_name[predecessor]]
            if key in HISTORICAL:
                status = "split_precinct" if len(predecessors) == 1 else "boundary_overlap"
            elif len(matches) > 1:
                status = "split_nodes"
            elif not matches:
                status = "unmatched"
            elif matches[0][1] > 1:
                status = "combined_node"
            else:
                status = "exact" if name.upper() == key else "normalized"
            writer.writerow(["Clermont", "", name, "unofficial", SOURCE,
                             ",".join(map(str, sorted(pages[name]))),
                             ";".join(str(node_id) for node_id, _ in sorted(set(matches))),
                             status, *(counts[c] for c in CANDIDATES)])


if __name__ == "__main__":
    folder = Path(__file__).resolve().parent
    extract(folder.parents[1], folder / "precinct_votes.csv")

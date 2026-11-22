#!/usr/bin/env python3
"""Extract Lorain's official precinct tables and apply the sourced crosswalk."""

import csv
import json
import re
from collections import defaultdict
from pathlib import Path

from pypdf import PdfReader

SOURCE = "Raw/Lorain.pdf"
NOTES = "precinct_merges_splits.txt"
BOUNDARY_HEADER = "Mapped crosswalk exceptions"
RACES = (
    "us_senate", "governor", "attorney_general", "auditor_of_state",
    "secretary_of_state", "treasurer_of_state",
    "supreme_court_2027_01_01", "supreme_court_2027_01_02",
)
FIELDS = [f"{race}_{party}" for race in RACES for party in ("dem", "rep")]
TABLES = {
    "Amy Acton": (("governor", 0, 2),),
    "Keith Faber": (
        ("attorney_general", 1, 0), ("auditor_of_state", 2, 3),
        ("secretary_of_state", 5, 6), ("treasurer_of_state", 8, 7),
    ),
    "Marilyn Zayas": (
        ("supreme_court_2027_01_01", 1, 0), ("supreme_court_2027_01_02", 2, 3),
    ),
    "Sherrod Brown": (("us_senate", 0, 1),),
}
ROW = re.compile(r"^ *([A-Z][A-Z\d .#&/\-]+?) {2,}([\d,][\d, ]*)$", re.MULTILINE)


def graph_name(name):
    return name.replace("SHEF LAKE CITY ", "SHEF. LAKE CITY ")


def graph_matches(root):
    nodes = json.loads((root / "OH_pct20.json").read_text(encoding="utf-8"))["nodes"]
    matches = defaultdict(dict)
    for node in nodes:
        if node["COUNTY"] == "LORAIN":
            members = node["ORIG_NAME"].split(",")
            for member in members:
                matches[member.removesuffix("_LORAIN")][node["id"]] = len(members) > 1
    return matches


def read_votes(source):
    votes, pages = defaultdict(dict), defaultdict(set)
    for number, page in enumerate(PdfReader(source).pages, 1):
        layout = page.extract_text(extraction_mode="layout")
        header = "\n".join(layout.splitlines()[:16])
        table = next((races for marker, races in TABLES.items() if marker in header), None)
        if table is None:
            continue
        for name, columns in ROW.findall(layout):
            counts = [int(value.replace(",", "")) for value in columns.split()]
            for race, dem, rep in table:
                for party, index in (("dem", dem), ("rep", rep)):
                    field = f"{race}_{party}"
                    if field in votes[name]:
                        raise ValueError(f"Duplicate {field} for {name}")
                    votes[name][field] = counts[index]
            pages[name].add(number)
    return votes, pages


def extract(root, output):
    votes, pages = read_votes(root / SOURCE)
    notes = (Path(__file__).resolve().parent / NOTES).read_text(encoding="utf-8")
    exceptions = {}
    for line in notes.split(BOUNDARY_HEADER + "\n", 1)[1].strip().splitlines():
        name, status, ids, _ = line.split(" | ")
        exceptions[name] = ids, status
    matches = graph_matches(root)
    with output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow([
            "county", "precinct_code", "precinct_name", "canvass_type", "source_file",
            "source_pages", "graph_node_ids", "graph_match_status", *FIELDS,
        ])
        for name, counts in votes.items():
            if name in exceptions:
                ids, status = exceptions[name]
            else:
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
                    status = "exact" if name == key else "normalized"
            writer.writerow([
                "Lorain", "", name, "official", SOURCE, ",".join(map(str, sorted(pages[name]))),
                ids, status, *(counts[field] for field in FIELDS),
            ])


if __name__ == "__main__":
    folder = Path(__file__).resolve().parent
    extract(folder.parents[1], folder / "precinct_votes.csv")

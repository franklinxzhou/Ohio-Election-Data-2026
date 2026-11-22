#!/usr/bin/env python3
"""Extract Democratic and Republican precinct totals from Preble's SOVC."""

import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from pypdf import PdfReader

SOURCE = "Raw/Preble.pdf"
# Physical pages, numeric row width, then zero-based D and R columns.
RACES = [
    ("us_senate", 15, 17, 11, 0, 1),
    ("governor", 3, 5, 10, 0, 2),
    ("attorney_general", 6, 8, 8, 1, 0),
    ("auditor_of_state", 6, 8, 8, 4, 5),
    ("secretary_of_state", 9, 11, 9, 1, 2),
    ("treasurer_of_state", 9, 11, 9, 6, 5),
    ("supreme_court_2027_01_01", 12, 14, 8, 1, 0),
    ("supreme_court_2027_01_02", 12, 14, 8, 4, 5),
]
ROW = re.compile(r"^\s*(\d{3} \S.*?) {2,}([\d,]+(?: +[\d,]+)*)\s*$")
ALIASES = {
    "COLLEGE CORNER": "COLLEGE CORNER-ISRAEL 1",
    "ISRAEL 1": "COLLEGE CORNER-ISRAEL 1",
    "ISRAEL 2": "ISRAEL II",
    "GRATIS SOUTH": "WEST ELKTON-GRATIS SOUTH",
    "WEST ELKTON": "WEST ELKTON-GRATIS SOUTH",
    "VERONA": "VERONA/HARRISON-NORTHEAST",
    "HARRISON NORTHEAST": "VERONA/HARRISON-NORTHEAST",
}


def graph_name(name):
    base = name.upper().split(" - ", 1)[0].replace(" TWP", "")
    if base == "GRATIS VILLAGE":
        return base
    base = base.replace(" VIILLAGE", " VILLAGE")
    base = base.replace(" VILLAGE", "")
    return ALIASES.get(base, base)


def extract(root, output):
    pdf = PdfReader(root / SOURCE)
    pages = {
        i: pdf.pages[i - 1].extract_text(extraction_mode="layout").splitlines()
        for i in range(3, 18)
    }
    votes, source_pages = defaultdict(dict), defaultdict(set)
    for race, first, last, width, dem, rep in RACES:
        for page in range(first, last + 1):
            for line in pages[page]:
                if not (match := ROW.fullmatch(line)):
                    continue
                name, numbers = match.groups()
                values = numbers.replace(",", "").split()
                if len(values) != width:
                    continue
                votes[name][f"{race}_dem"] = int(values[dem])
                votes[name][f"{race}_rep"] = int(values[rep])
                source_pages[name].add(page)

    graph = json.loads((root / "OH_pct20.json").read_text(encoding="utf-8"))
    matches = {}
    for node in graph["nodes"]:
        if node["COUNTY"] == "PREBLE":
            members = node["ORIG_NAME"].split(",")
            for member in members:
                matches[member.removesuffix("_PREBLE")] = node["id"], len(members) > 1

    links = {label: graph_name(label.split(" ", 1)[1]) for label in votes}
    member_counts = Counter(links.values())
    fields = [f"{race}_{party}" for race, *_ in RACES for party in ("dem", "rep")]
    with output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow([
            "county", "precinct_code", "precinct_name", "canvass_type", "source_file",
            "source_pages", "graph_node_ids", "graph_match_status", *fields,
        ])
        for label, counts in sorted(votes.items()):
            code, name = label.split(" ", 1)
            key = links[label]
            node, combined = matches[key]
            if member_counts[key] > 1:
                status = "split_precinct"
            else:
                status = "combined_node" if combined else ("exact" if key == name.upper() else "normalized")
            writer.writerow([
                "Preble", code, name, "official", SOURCE, ",".join(map(str, sorted(source_pages[label]))),
                node, status, *(counts[field] for field in fields),
            ])


if __name__ == "__main__":
    folder = Path(__file__).resolve().parent
    extract(folder.parents[1], folder / "precinct_votes.csv")

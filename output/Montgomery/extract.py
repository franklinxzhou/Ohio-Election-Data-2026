#!/usr/bin/env python3
"""Combine Montgomery's ballot-style rows into statewide precinct totals."""

import csv
import logging
import re
from collections import defaultdict
from pathlib import Path

from pypdf import PdfReader

SOURCE = "Raw/Montgomery.pdf"
# Physical page range and numeric candidate columns, in D/R order.
RACES = [
    ("us_senate", 96, 111, 14, 0, 1),
    ("governor", 15, 31, 13, 0, 2),
    ("attorney_general", 32, 47, 12, 1, 0),
    ("auditor_of_state", 32, 47, 12, 6, 7),
    ("secretary_of_state", 48, 63, 7, 1, 2),
    ("treasurer_of_state", 64, 79, 12, 1, 0),
    ("supreme_court_2027_01_01", 64, 79, 12, 7, 6),
    ("supreme_court_2027_01_02", 80, 95, 6, 0, 1),
]
ROW = re.compile(r"^\s*(\S(?:.*?\S)?) {2,}([\d,]+(?: +[\d,]+)*)\s*$")
COLUMNS = ["county", "precinct_code", "precinct_name", "canvass_type",
           "source_file", "source_pages", "graph_node_ids", "graph_match_status"]


def precinct_rows(root):
    pdf = PdfReader(root / SOURCE)
    pages = {
        i: pdf.pages[i - 1].extract_text(extraction_mode="layout")
        for i in range(15, 112)
    }
    votes, source_pages, styles = defaultdict(dict), defaultdict(set), defaultdict(set)
    for race, first, last, width, dem, rep in RACES:
        seen = set()
        for page in range(first, last + 1):
            for line in pages[page].splitlines():
                match = ROW.fullmatch(line)
                if not match:
                    continue
                label, numbers = match.groups()
                values = numbers.replace(",", "").split()
                if label == "Totals" or len(values) != width:
                    continue
                if label in seen:
                    raise ValueError(f"Duplicate {race} ballot style {label}")
                seen.add(label)
                name = re.sub(r" \d+$", "", label)
                styles[name].add(label)
                source_pages[name].add(page)
                for party, index in (("dem", dem), ("rep", rep)):
                    field = f"{race}_{party}"
                    votes[name][field] = votes[name].get(field, 0) + int(values[index])
    return votes, source_pages, styles


def export(root, folder):
    votes, pages, _ = precinct_rows(root)
    notes = (folder / "precinct_merges_splits.txt").read_text()
    links = {}
    for line in notes.split("\nCrosswalk rows\n", 1)[1].splitlines():
        code, name, status, ids, _ = line.split(" | ")
        links[code] = name, status, ids
    if votes.keys() != links.keys():
        raise ValueError("Canvass and county GIS precinct codes differ")
    fields = [f"{race[0]}_{party}" for race in RACES for party in ("dem", "rep")]
    with (folder / "precinct_votes.csv").open("w", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(COLUMNS + fields)
        for code, counts in votes.items():
            name, status, ids = links[code]
            writer.writerow([
                "Montgomery", code, name, "unofficial", SOURCE,
                ",".join(map(str, sorted(pages[code]))),
                ids, status,
                *(counts[field] for field in fields),
            ])


if __name__ == "__main__":
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    folder = Path(__file__).resolve().parent
    export(folder.parents[1], folder)

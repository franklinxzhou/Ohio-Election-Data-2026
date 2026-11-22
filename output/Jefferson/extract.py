#!/usr/bin/env python3
"""Extract Jefferson's official statewide precinct votes and link the 2020 graph."""

import csv
import json
import re
from collections import defaultdict
from pathlib import Path

from pypdf import PdfReader

SOURCE = "Raw/Jefferson.pdf"
# First PDF page and zero-based D/R candidate columns within each contest.
RACES = [
    ("us_senate", 15, 0, 1),
    ("governor", 1, 0, 2),
    ("attorney_general", 3, 1, 0),
    ("auditor_of_state", 5, 0, 1),
    ("secretary_of_state", 7, 1, 2),
    ("treasurer_of_state", 9, 1, 0),
    ("supreme_court_2027_01_01", 11, 1, 0),
    ("supreme_court_2027_01_02", 13, 0, 1),
]
# See the sourced crosswalk notes for the basis of each mapping.
MERGES = {
    "ELK": ("ELK", "BERGHOLZ"),
    "EMERSON": ("EMERSON", "MT PLEASANT"),
    "GRANT": ("GRANT", "EMPIRE"),
    "LINCOLN": ("LINCOLN", "SMITHFIELD"),
    "MINGO 1": ("MINGO A", "MINGO B"),
    "MINGO 2": ("MINGO C", "MINGO D"),
    "PINE VALLEY": ("PINE VALLEY", "DILLONVALE"),
    "PINEY FORK": ("PINEY FORK", "ADENA"),
    "SALINE": ("SALINE", "IRONDALE"),
    "STEUBENVILLE 1-1": ("STEUBENVILLE 1-1", "STEUBENVILLE 1-2"),
    "STEUBENVILLE 4-1": ("STEUBENVILLE 4-1", "STEUBENVILLE 4-2"),
    "TILTONSVILLE": ("TILTONSVILLE", "RAYLAND"),
    "WAYNE": ("WAYNE", "BLOOMINGDALE"),
    "WELLS": ("WELLS 1", "WELLS 2", "NEW ALEXANDRIA"),
    "WINTERSVILLE C": ("WINTERSVILLE C", "WINTERSVILLE D"),
}
ROW = re.compile(r"^Precinct (.*?) (\d{3}) {2,}(\d.*)$", re.MULTILINE)
VOTE = re.compile(r"([\d,]+)\s+\d+(?:\.\d+)?%")


def extract(root, output):
    pdf = PdfReader(root / SOURCE)
    votes, pages = defaultdict(dict), defaultdict(set)
    for race, first, dem, rep in RACES:
        for page in (first, first + 1):
            table = pdf.pages[page - 1].extract_text(extraction_mode="layout")
            for name, code, row in ROW.findall(table):
                counts = VOTE.findall(row)
                for party, index in (("dem", dem), ("rep", rep)):
                    votes[code, name][f"{race}_{party}"] = int(counts[index].replace(",", ""))
                pages[code, name].add(page)

    graph = json.loads((root / "OH_pct20.json").read_text(encoding="utf-8"))
    matches = {}
    for node in graph["nodes"]:
        if node["COUNTY"] == "JEFFERSON":
            members = node["ORIG_NAME"].split(",")
            for member in members:
                matches[member.removesuffix("_JEFFERSON")] = node["id"], len(members) > 1

    fields = [f"{race}_{party}" for race, *_ in RACES for party in ("dem", "rep")]
    with output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow([
            "county", "precinct_code", "precinct_name", "canvass_type", "source_file",
            "source_pages", "graph_node_ids", "graph_match_status", *fields,
        ])
        for code, name in sorted(votes):
            members = MERGES.get(name, (name,))
            node_ids = ";".join(map(str, sorted({matches[member][0] for member in members})))
            status = "exact"
            if name in MERGES:
                status = "merged_precinct"
            elif matches[name][1]:
                status = "combined_node"
            source_pages = ",".join(map(str, sorted(pages[code, name])))
            writer.writerow([
                "Jefferson", code, name, "official", SOURCE, source_pages, node_ids, status,
                *(votes[code, name][field] for field in fields),
            ])


if __name__ == "__main__":
    folder = Path(__file__).resolve().parent
    extract(folder.parents[1], folder / "precinct_votes.csv")

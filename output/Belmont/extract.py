#!/usr/bin/env python3
"""Extract Belmont's Official Canvass with Python 3 and pypdf."""

import csv
import json
import re
from collections import defaultdict
from pathlib import Path

from pypdf import PdfReader

SOURCE = "Raw/Belmont.pdf"
# Each statewide contest occupies 24 PDF pages.
CONTESTS = {
    "us_senate": 180,
    "governor": 12,
    "attorney_general": 36,
    "auditor_of_state": 60,
    "secretary_of_state": 84,
    "treasurer_of_state": 108,
    "supreme_court_2027_01_01": 132,
    "supreme_court_2027_01_02": 156,
}
VOTE_COLUMNS = [f"{contest}_{party}" for contest in CONTESTS for party in ("dem", "rep")]
METADATA = ["county", "precinct_code", "precinct_name", "canvass_type", "source_file",
            "source_pages", "graph_node_ids", "graph_match_status"]
PRECINCT = re.compile(r"(?m)^(\d{3}) +([A-Z][^\n]*(?:\n[A-Z][A-Z .'-]*)*)\n(?=Election Day\n)")
PARTY = re.compile(r"\((DEM|REP|LIB|OPC)\)")


def extract(root, output):
    pdf = PdfReader(root / SOURCE)
    votes, pages = defaultdict(dict), defaultdict(set)
    for contest, first in CONTESTS.items():
        for number in range(first, first + 24):
            # The final Precinct table is the candidate panel. The first
            # table on left-hand pages contains turnout and registration.
            panel = pdf.pages[number - 1].extract_text().rsplit("\nPrecinct\n", 1)[-1]
            header, *blocks = PRECINCT.split(panel)
            columns = [(i, f"{contest}_{party.lower()}") for i, party in enumerate(PARTY.findall(header))
                       if party in {"DEM", "REP"}]
            if not columns:
                continue
            for i in range(0, len(blocks), 3):
                code, name, detail = blocks[i:i + 3]
                precinct = code, " ".join(name.split())
                totals = detail.split("\nTotal\n", 1)[1].splitlines()
                for j, column in columns:
                    if column in votes[precinct]:
                        raise ValueError(f"Duplicate {column} for {precinct} on page {number}")
                    votes[precinct][column] = int(totals[j].replace(",", ""))
                    pages[precinct].add(number)

    graph = json.loads((root / "OH_pct20.json").read_text(encoding="utf-8"))
    by_name = {}
    for node in graph["nodes"]:
        if node["COUNTY"] == "BELMONT":
            members = node["ORIG_NAME"].split(",")
            for member in members:
                by_name[member.removesuffix("_BELMONT")] = node["id"], len(members)

    rows = []
    for precinct, counts in sorted(votes.items()):
        code, name = precinct
        if missing := set(VOTE_COLUMNS) - counts.keys():
            raise ValueError(f"Missing {', '.join(sorted(missing))} for {precinct}")
        if name == "FLUSHING TWP":
            # The former precincts are listed in the county's historic
            # canvasses. See precinct_merges_splits.txt for the sources.
            ids = [by_name["FLUSHING TWP 1"][0], by_name["FLUSHING TWP 2"][0]]
            status = "merged_precinct"
        else:
            node, size = by_name[name]
            ids = [node]
            status = "combined_node" if size > 1 else "exact"
        rows.append(["Belmont", code, name, "official", SOURCE,
                     ";".join(map(str, sorted(pages[precinct]))),
                     ";".join(map(str, ids)), status, *(counts[column] for column in VOTE_COLUMNS)])

    with output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(METADATA + VOTE_COLUMNS)
        writer.writerows(rows)


if __name__ == "__main__":
    folder = Path(__file__).resolve().parent
    extract(folder.parents[1], folder / "precinct_votes.csv")

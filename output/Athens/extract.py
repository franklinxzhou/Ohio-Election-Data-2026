#!/usr/bin/env python3
"""Extract Athens's Official Canvass. Run with Python 3 and pypdf installed."""

import csv
import json
import re
from collections import defaultdict
from pathlib import Path

from pypdf import PdfReader

SOURCE = "Raw/Athens.pdf"
CONTESTS = {
    "U.S. Senator UTE 1-3-29": "us_senate",
    "Governor and Lieutenant Governor": "governor",
    "Attorney General": "attorney_general",
    "Auditor of State": "auditor_of_state",
    "Secretary of State": "secretary_of_state",
    "Treasurer of State": "treasurer_of_state",
    "Justice of the Supreme Court FTC 1-1-27": "supreme_court_2027_01_01",
    "Justice of the Supreme Court FTC 1-2-27": "supreme_court_2027_01_02",
}
VOTE_COLUMNS = [f"{contest}_{party}" for contest in CONTESTS.values() for party in ("dem", "rep")]
METADATA = ["county", "precinct_code", "precinct_name", "canvass_type", "source_file",
            "source_pages", "graph_node_ids", "graph_match_status"]
CANDIDATE = re.compile(r"(Dem|Rep) .+?\s{2,}([\d,]+)\s+[\d.]+%")

# Precinct codes 0001–0050 from the county's November 2026 polling-place list.
# https://www.boe.ohio.gov/athens/c/upload/ELECTION_PollingLocations.pdf
OFFICIAL_ORDER = (
    "ATHENS 1-1|ATHENS 1-2|ATHENS 1-3|ATHENS 1-4|ATHENS 2-1|ATHENS 2-2|ATHENS 2-3|"
    "ATHENS 3-1|ATHENS 3-2|ATHENS 3-3|ATHENS 3-4|ATHENS 3-5|ATHENS 4-1|ATHENS 4-2|"
    "ATHENS 4-3|ATHENS 4-4|ATHENS 4-5|NELSONVILLE 1|NELSONVILLE 2|NELSONVILLE 3|NELSONVILLE 4|"
    "ALEXANDER EAST|ALEXANDER WEST|AMESVILLE VLG|AMES TOWNSHIP|ATHENS BAKER|ATHENS SOUTH|"
    "PLAINS 1|PLAINS 2|BERN TOWNSHIP|CANAAN TWP|CARTHAGE TWP|CHAUNCEY|DOVER EAST|DOVER WEST|"
    "ALBANY VILLAGE|LEE TOWNSHIP|LODI TOWNSHIP|ROME TOWNSHIP|GLOUSTER VILLAGE|JACKSONVILLE|"
    "TRIMBLE VILLAGE|TRIMBLE TOWNSHIP|COOLVILLE VILLAGE|TROY EAST|TROY WEST|NEW MARSHFIELD|"
    "WATERLOO|BUCHTEL VLG|YORK TOWNSHIP"
).split("|")

# Board of Elections motion 2025:12:05, attachment 2.
# https://www.boe.ohio.gov/athens/c/pdfs/minutes/2025/121725MINUTES.pdf
CHANGES = {
    "ATHENS 1-4": ("merged_precinct", ("ATHENS 1-4", "ATHENS 1-5")),
    "ATHENS 2-1": ("merged_precinct", ("ATHENS 2-1", "ATHENS 2-5")),
    "ATHENS 2-2": ("merged_precinct", ("ATHENS 2-2", "ATHENS 2-3")),
    "ATHENS 3-1": ("merged_precinct", ("ATHENS 3-1", "ATHENS 3-3")),
    "DOVER EAST": ("merged_precinct", ("MILLFIELD", "SUGAR CREEK")),
    "ATHENS 2-3": ("renamed", ("ATHENS 2-4",)),
    "ATHENS 3-3": ("renamed", ("ATHENS 3-4",)),
    "ATHENS 3-4": ("renamed", ("ATHENS 3-5",)),
    "ATHENS 3-5": ("renamed", ("ATHENS 3-6",)),
    "DOVER WEST": ("renamed", ("CIRCLE HILL",)),
    # Each also absorbed part of Athens East, which shares their graph nodes.
    "ATHENS SOUTH": ("split_nodes", ("ATHENS SOUTH", "ATHENS EAST")),
    "PLAINS 1": ("split_nodes", ("PLAINS 1", "ATHENS EAST")),
}


def normalize(name):
    name = re.sub(r"ATHENS WARD (\d+), PRECINCT (\d+)", r"ATHENS \1-\2", name.upper())
    name = re.sub(r" TWP$", " TOWNSHIP", name)
    return re.sub(r" (?:VILLAGE|VLG)$", "", name)


def extract(root, output):
    precincts = {}
    for number, page in enumerate(PdfReader(root / SOURCE).pages, 1):
        lines = page.extract_text(extraction_mode="layout").splitlines()
        name = lines[3].strip()
        votes, pages = precincts.setdefault(name, ({}, set()))
        contest = None
        for line in map(str.strip, lines[4:]):
            if line in CONTESTS:
                contest = CONTESTS[line]
            if line.startswith("Total Votes Cast"):
                contest = None
            if contest and (candidate := CANDIDATE.match(line)):
                party, count = candidate.groups()
                column = f"{contest}_{party.lower()}"
                if column in votes:
                    raise ValueError(f"Duplicate {column} for {name} on page {number}")
                votes[column] = int(count.replace(",", ""))
                pages.add(number)

    graph = json.loads((root / "OH_pct20.json").read_text(encoding="utf-8"))
    by_name = defaultdict(list)
    for node in graph["nodes"]:
        if node["COUNTY"] == "ATHENS":
            members = [name.removesuffix("_ATHENS") for name in node["ORIG_NAME"].split(",")]
            for member in members:
                by_name[normalize(member)].append((node["id"], member, len(members)))

    codes = {normalize(name): f"{i:04d}" for i, name in enumerate(OFFICIAL_ORDER, 1)}
    rows = []
    for name, (votes, pages) in precincts.items():
        if missing := set(VOTE_COLUMNS) - votes.keys():
            raise ValueError(f"Missing {', '.join(sorted(missing))} for {name}")
        key = normalize(name)
        status, predecessors = CHANGES.get(key, ("", (key,)))
        matches = {match for predecessor in predecessors for match in by_name[predecessor]}
        ids = sorted({node_id for node_id, _, _ in matches})
        if not status:
            if len(ids) == 1:
                _, member, size = next(iter(matches))
                status = "combined_node" if size > 1 else "exact" if member == name.upper() else "normalized"
            else:
                status = "split_nodes" if ids else "unmatched"
        rows.append(["Athens", codes[key], name, "official", SOURCE, f"{min(pages)}-{max(pages)}",
                     ";".join(map(str, ids)), status, *(votes[column] for column in VOTE_COLUMNS)])

    with output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(METADATA + VOTE_COLUMNS)
        writer.writerows(sorted(rows, key=lambda row: row[1]))


if __name__ == "__main__":
    folder = Path(__file__).resolve().parent
    extract(folder.parents[1], folder / "precinct_votes.csv")

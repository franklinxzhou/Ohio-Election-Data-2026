#!/usr/bin/env python3
"""Extract Ashtabula's Official Canvass. Run with Python 3 and pypdf installed."""

import csv
import json
import re
from collections import defaultdict
from pathlib import Path

from pypdf import PdfReader

SOURCE = "Raw/Ashtabula.pdf"
CONTESTS = {
    "For U.S. Senator (UTE 1-3-2029)": "us_senate",
    "For Governor and Lieutenant Governor": "governor",
    "For Attorney General": "attorney_general",
    "For Auditor of State": "auditor_of_state",
    "For Secretary of State": "secretary_of_state",
    "For Treasurer of State": "treasurer_of_state",
    "For Justice of the Supreme Court (FTC 1-1-27)": "supreme_court_2027_01_01",
    "For Justice of the Supreme Court (FTC 1-2-27)": "supreme_court_2027_01_02",
}
VOTE_COLUMNS = [f"{contest}_{party}" for contest in CONTESTS.values() for party in ("dem", "rep")]
METADATA = ["county", "precinct_code", "precinct_name", "canvass_type", "source_file",
            "source_pages", "graph_node_ids", "graph_match_status"]
PRECINCT = re.compile(r"(\d{3}) ([A-Za-z].*)")
CANDIDATE = re.compile(r"(Dem|Rep) .+?\s{2,}([\d,]+)")
ALIASES = {
    "GEN ON LAKE VILL": "GENEVA ON THE LAKE VILLAGE",
    "HARPERSFLD": "HARPERSFIELD",
    "JEFF VILL": "JEFFERSON VILLAGE",
    "N KINGS VILL": "NORTH KINGSVILLE VILLAGE",
    "WMSFLD": "WILLIAMSFIELD",
}


def normalize(name):
    parts = name.upper().replace(".", "").replace("-", "").split()
    compact = " ".join("TWP" if part == "TOWNSHIP" else part for part in parts if part != "CITY")
    if compact == "CHERRY VALLEY":
        return "CHERRY VALLEY TWP"
    for short, full in ALIASES.items():
        if compact == short or compact.startswith(short + " "):
            return full + compact[len(short):]
    return compact


def extract(root, output):
    precincts = {}
    for number, page in enumerate(PdfReader(root / SOURCE).pages, 1):
        lines = page.extract_text(extraction_mode="layout").strip().splitlines()
        code, name = PRECINCT.fullmatch(lines[4].strip()).groups()
        votes, pages = precincts.setdefault((code, name), ({}, set()))
        contest = None
        for line in map(str.strip, lines[5:]):
            if line.startswith("For "):
                contest = CONTESTS.get(line)
            if line.startswith("Total Votes Cast"):
                contest = None
            if contest and (candidate := CANDIDATE.fullmatch(line)):
                party, count = candidate.groups()
                column = f"{contest}_{party.lower()}"
                if column in votes:
                    raise ValueError(f"Duplicate {column} for {code} {name} on page {number}")
                votes[column] = int(count.replace(",", ""))
                pages.add(number)

    graph = json.loads((root / "OH_pct20.json").read_text(encoding="utf-8"))
    by_name = defaultdict(list)
    for node in graph["nodes"]:
        if node["COUNTY"] == "ASHTABULA":
            members = [name.removesuffix("_ASHTABULA") for name in node["ORIG_NAME"].split(",")]
            for member in members:
                by_name[normalize(member)].append((node["id"], member, len(members)))

    rows = []
    for (code, name), (votes, pages) in precincts.items():
        if missing := set(VOTE_COLUMNS) - votes.keys():
            raise ValueError(f"Missing {', '.join(sorted(missing))} for {code} {name}")
        matches = by_name[normalize(name)]
        if len(matches) == 1:
            _, member, size = matches[0]
            status = "combined_node" if size > 1 else "exact" if member == name.upper() else "normalized"
        elif matches:
            status = "split_nodes" if len({member for _, member, _ in matches}) == 1 else "ambiguous"
        else:
            status = "unmatched"
        rows.append(["Ashtabula", code, name, "official", SOURCE, f"{min(pages)}-{max(pages)}",
                     ";".join(str(node_id) for node_id, _, _ in matches), status,
                     *(votes[column] for column in VOTE_COLUMNS)])

    with output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(METADATA + VOTE_COLUMNS)
        writer.writerows(rows)


if __name__ == "__main__":
    folder = Path(__file__).resolve().parent
    extract(folder.parents[1], folder / "precinct_votes.csv")

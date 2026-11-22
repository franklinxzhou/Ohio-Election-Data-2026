#!/usr/bin/env python3
"""Extract Allen's Official Canvass. Run with Python 3 and pypdf installed."""

import csv
import json
import re
from pathlib import Path

from pypdf import PdfReader

CONTESTS = {
    "For U.S. Senator (UTE 1-3-29)": "us_senate",
    "For Governor and Lieutenant Governor": "governor",
    "For Attorney General": "attorney_general",
    "For Auditor of State": "auditor_of_state",
    "For Secretary of State": "secretary_of_state",
    "For Treasurer of State": "treasurer_of_state",
    "For Justice of the Supreme Court (1-1-27)": "supreme_court_2027_01_01",
    "For Justice of the Supreme Court (1-2-27)": "supreme_court_2027_01_02",
}
VOTE_COLUMNS = [f"{contest}_{party}" for contest in CONTESTS.values() for party in ("dem", "rep")]
METADATA = ["county", "precinct_code", "precinct_name", "canvass_type", "source_file",
            "source_pages", "graph_node_ids", "graph_match_status"]
SOURCE = "Raw/Allen.pdf"
CANDIDATE = re.compile(r"^(Dem|Rep) .+?\s{2,}([\d,]+)(?=\s)")


def extract(root, output):
    graph = json.loads((root / "OH_pct20.json").read_text(encoding="utf-8"))
    by_name = {}
    for node in graph["nodes"]:
        if node["COUNTY"] == "ALLEN":
            members = node["ORIG_NAME"].split(",")
            for member in members:
                by_name.setdefault(member.removesuffix("_ALLEN"), []).append((node["id"], len(members)))

    precincts = {}
    for page_number, page in enumerate(PdfReader(root / SOURCE).pages, 1):
        lines = page.extract_text(extraction_mode="layout").splitlines()
        code, name = lines[3].strip().split(maxsplit=1)
        votes, pages = precincts.setdefault((code, name), ({}, set()))
        contest = None
        for line in map(str.strip, lines[4:]):
            if line.startswith("For "):
                contest = CONTESTS.get(line)
            candidate = CANDIDATE.match(line) if contest else None
            if candidate:
                party, total = candidate.groups()
                column = f"{contest}_{party.lower()}"
                if column in votes:
                    raise ValueError(f"Duplicate {column} for {code} {name} on page {page_number}")
                votes[column] = int(total.replace(",", ""))
                pages.add(page_number)

    rows = []
    for (code, name), (votes, pages) in precincts.items():
        if missing := VOTE_COLUMNS - votes.keys():
            raise ValueError(f"Missing {', '.join(sorted(missing))} for {code} {name}")
        matches = by_name.get(name.upper(), [])
        if len(matches) == 1:
            status = "exact" if matches[0][1] == 1 else "combined_node"
        else:
            status = "ambiguous" if matches else "unmatched"
        rows.append(["Allen", code, name, "official", SOURCE, f"{min(pages)}-{max(pages)}",
                     ";".join(str(node_id) for node_id, _ in matches), status,
                     *(votes[column] for column in VOTE_COLUMNS)])

    with output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(METADATA + VOTE_COLUMNS)
        writer.writerows(rows)


if __name__ == "__main__":
    folder = Path(__file__).resolve().parent
    extract(folder.parents[1], folder / "precinct_votes.csv")

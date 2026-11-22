#!/usr/bin/env python3
"""Extract Knox County's official statewide precinct totals with pypdf."""

import csv
import json
import re
from collections import defaultdict
from pathlib import Path

from pypdf import PdfReader

SOURCE = "Raw/Knox.pdf"
NOTES = "precinct_merges_splits.txt"
BOUNDARY_HEADER = "Mapped crosswalk exceptions"
RACES = {
    "For U.S. Senator (UTE 1-3-2029)": "us_senate",
    "For Governor and Lieutenant Governor": "governor",
    "For Attorney General": "attorney_general",
    "For Auditor of State": "auditor_of_state",
    "For Secretary of State": "secretary_of_state",
    "For Treasurer of State": "treasurer_of_state",
    "For Justice of the Supreme Court (FTC 1-1-2027)": "supreme_court_2027_01_01",
    "For Justice of the Supreme Court (FTC 1-2-2027)": "supreme_court_2027_01_02",
}
PRECINCT = re.compile(r"^November 3, 2026 +Knox County\s+([^\n]+)", re.MULTILINE)
CANDIDATE = re.compile(r"^(DEM|REP) .+? {2,}([\d,]+) +\d+\.\d+%")
TOWN_WARD = re.compile(r"[1-4]-[A-C]")


def historical_name(name):
    if TOWN_WARD.fullmatch(name):
        return f"MOUNT VERNON {name}"
    return "CLAY-MARTINSBURG" if name == "CLAY-MART" else name


def graph_matches(root):
    nodes = json.loads((root / "OH_pct20.json").read_text(encoding="utf-8"))["nodes"]
    matches = defaultdict(dict)
    for node in nodes:
        if node["COUNTY"] == "KNOX":
            members = node["ORIG_NAME"].split(",")
            for member in members:
                matches[member.removesuffix("_KNOX")][node["id"]] = len(members) > 1
    return matches


def read_votes(source):
    votes, pages = defaultdict(dict), defaultdict(set)
    for page, pdf_page in enumerate(PdfReader(source).pages, 1):
        layout = pdf_page.extract_text(extraction_mode="layout")
        if "of 384" not in layout:  # Inserted local levy supplement.
            continue
        name = PRECINCT.search(layout)[1].strip()
        race = None
        for line in layout.splitlines():
            if line.startswith("For "):
                race = RACES.get(line.strip())
            elif race and (match := CANDIDATE.match(line)):
                party, count = match.groups()
                field = f"{race}_{party.lower()}"
                if field in votes[name]:
                    raise ValueError(f"Duplicate {field} for {name}")
                votes[name][field] = int(count.replace(",", ""))
                pages[name].add(page)
    return votes, pages


def extract(root, output):
    votes, pages = read_votes(root / SOURCE)
    matches = graph_matches(root)
    notes = (Path(__file__).resolve().parent / NOTES).read_text(encoding="utf-8")
    exceptions = {}
    for line in notes.split(BOUNDARY_HEADER + "\n", 1)[1].strip().splitlines():
        name, status, ids, _ = line.split(" | ")
        exceptions[name] = ids, status

    fields = [f"{race}_{party}" for race in RACES.values() for party in ("dem", "rep")]
    with output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow([
            "county", "precinct_code", "precinct_name", "canvass_type", "source_file",
            "source_pages", "graph_node_ids", "graph_match_status", *fields,
        ])
        for name, counts in votes.items():
            if name in exceptions:
                ids, status = exceptions[name]
            else:
                old_name = historical_name(name)
                nodes = matches[old_name]
                ids = ";".join(map(str, sorted(nodes)))
                status = "split_nodes" if len(nodes) > 1 else "combined_node" if any(nodes.values()) else (
                    "exact" if name == old_name else "normalized"
                )
            writer.writerow([
                "Knox", "", name, "official", SOURCE, ",".join(map(str, sorted(pages[name]))),
                ids, status, *(counts[field] for field in fields),
            ])


if __name__ == "__main__":
    folder = Path(__file__).resolve().parent
    extract(folder.parents[1], folder / "precinct_votes.csv")

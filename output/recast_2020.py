#!/usr/bin/env python3
"""Recast 2026 precinct votes onto graph nodes without allocating any votes."""

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

VOTE_FIELDS = [
    f"{race}_{party}"
    for race in (
        "us_senate", "governor", "attorney_general", "auditor_of_state",
        "secretary_of_state", "treasurer_of_state",
        "supreme_court_2027_01_01", "supreme_court_2027_01_02",
    )
    for party in ("dem", "rep")
]
FIELDS = ["graph_node_id", "county", "orig_name", "canvass_type",
          "source_precinct_count", *VOTE_FIELDS]


def unresolved_candidates(node_info):
    # Champaign's merge/split notes identify these two possible predecessors.
    # Summit's notes document revisions within Green, so exclude the whole city.
    green = {
        node_id for node_id, node in node_info.items()
        if node["COUNTY"] == "SUMMIT"
        and any(name.startswith("GREEN ") for name in node["ORIG_NAME"].split(","))
    }
    return {
        ("CHAMPAIGN", "0021"): {701, 702},
        **{("SUMMIT", code): green for code in ("176", "177", "178")},
    }


def recast(node_info, precinct_files):
    known_unresolved = unresolved_candidates(node_info)
    excluded_nodes, excluded_counties = set(), set()
    votes = defaultdict(lambda: [0] * len(VOTE_FIELDS))
    counts = defaultdict(int)
    canvasses = defaultdict(set)

    for path in precinct_files:
        with path.open(encoding="utf-8-sig", newline="") as file:
            for row in csv.DictReader(file):
                county = row["county"].upper()
                totals = [int(row[field]) for field in VOTE_FIELDS]
                ids = {int(value) for value in row["graph_node_ids"].split(";") if value.strip()}
                if any(node_id not in node_info or node_info[node_id]["COUNTY"] != county
                       for node_id in ids):
                    raise ValueError(f"{path}: invalid graph IDs for {row['precinct_name']}")
                if row["graph_match_status"] == "unmatched" or len(ids) != 1:
                    if ids:
                        excluded_nodes.update(ids)
                    elif any(totals):
                        candidates = known_unresolved.get((county, row["precinct_code"]))
                        if candidates:
                            excluded_nodes.update(candidates)
                        else:
                            excluded_counties.add(county)
                    continue

                node_id, = ids
                counts[node_id] += 1
                canvasses[node_id].add(row["canvass_type"])
                for index, total in enumerate(totals):
                    votes[node_id][index] += total

    for node_id in sorted(votes.keys() - excluded_nodes):
        node = node_info[node_id]
        if node["COUNTY"] not in excluded_counties:
            yield [node_id, node["COUNTY"], node["ORIG_NAME"],
                   ";".join(sorted(canvasses[node_id])), counts[node_id], *votes[node_id]]


def main():
    folder = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=folder / "perfect_recast_2020.csv")
    args = parser.parse_args()

    graph = json.loads((folder.parent / "OH_pct20.json").read_text(encoding="utf-8"))
    node_info = {node["id"]: node for node in graph["nodes"]}
    results = list(recast(node_info, sorted(folder.glob("*/precinct_votes.csv"))))
    with args.output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(FIELDS)
        writer.writerows(results)
    print(f"Wrote {len(results):,} graph nodes to {args.output}")


if __name__ == "__main__":
    main()

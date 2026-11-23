#!/usr/bin/env python3
"""Allocate all 2026 two-party returns to the 2020 Ohio graph."""

import argparse
import csv
import json
import os
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path
from tempfile import NamedTemporaryFile

from recast_2020 import VOTE_FIELDS, unresolved_candidates
from recast_geography import Geography, canonical

ROOT = Path(__file__).resolve().parent.parent
PARTIES = ("dem", "rep")


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as file:
        yield from csv.DictReader(file)


def count_votes(row):
    votes = {field: int(row[field]) for field in VOTE_FIELDS}
    if min(votes.values()) < 0:
        raise ValueError(f"Negative votes in {row}")
    return votes


def apportion(total, weights):
    """Hamilton rounding, with graph node ID as a stable tie-breaker."""
    exact = {node: Fraction(str(weight)) for node, weight in weights.items() if weight > 0}
    denominator = sum(exact.values())
    if not denominator:
        if total:
            raise ValueError("No positive allocation weight")
        return {}
    quotas = {node: total * weight / denominator for node, weight in exact.items()}
    counts = {node: int(quota) for node, quota in quotas.items()}
    order = sorted(counts, key=lambda node: (-(quotas[node] - counts[node]), node))
    for node in order[:total - sum(counts.values())]:
        counts[node] += 1
    return counts


def write_csv(path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", newline="", dir=path.parent, delete=False) as file:
        temporary = Path(file.name)
        try:
            writer = csv.DictWriter(file, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
            file.close()
            temporary.chmod(0o644)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def source_id(row):
    return (row.get("precinct_code", ""), row.get("precinct_name", ""))


def county_rows(folder):
    precincts = folder / "precinct_votes.csv"
    total = folder / "county_votes.csv"
    files = [path for path in (precincts, total) if path.is_file()]
    if len(files) != 1:
        raise ValueError(f"{folder.name}: expected exactly one canvass CSV")
    return list(read_csv(files[0])), files[0] == total


def allocate_county(rows, countywide, nodes, geography, known_unresolved, clean):
    county = next(iter(nodes.values()))["COUNTY"]
    allocated = defaultdict(Counter)
    expected = Counter()
    audit = []
    unlocated = []
    assignments = Counter()
    located = []

    def add(sources, weights_by_party, method, overlap=""):
        totals = Counter()
        for source in sources:
            totals.update(count_votes(source))
        allocation = defaultdict(Counter)
        used_weights = {}
        for party in PARTIES:
            weights = weights_by_party[party]
            if not any(weight > 0 for weight in weights.values()):
                weights = {node: nodes[node]["POP20"] for node in weights}
                if not any(weights.values()):
                    weights = dict.fromkeys(weights, 1)
                method += f"_population_for_{party}"
            used_weights[party] = weights
            for field in VOTE_FIELDS:
                if field.endswith("_" + party):
                    for node, votes in apportion(totals[field], weights).items():
                        allocation[node][field] = votes
        assignments[method] += len(sources)
        for node, votes in sorted(allocation.items()):
            if not any(votes.values()):
                continue
            allocated[node].update(votes)
            audit.append({
                "county": county,
                "source_precinct_codes": json.dumps([source_id(row)[0] for row in sources]),
                "source_precinct_names": json.dumps([source_id(row)[1] for row in sources]),
                "canvass_type": ";".join(sorted({row["canvass_type"] for row in sources})),
                "source_file": ";".join(sorted({row["source_file"] for row in sources})),
                "graph_node_id": node,
                "allocation_method": method,
                "dominant_node_area_share": overlap,
                **{f"{party}_weight": used_weights[party].get(node, 0) for party in PARTIES},
                **{field: votes[field] for field in VOTE_FIELDS},
            })

    for row in rows:
        if canonical(row["county"]) != canonical(county):
            raise ValueError(f"Unexpected canvass county {row['county']} in {county}")
        totals = count_votes(row)
        expected.update(totals)
        if not any(totals.values()):
            continue
        if countywide:
            add([row], geography.history(nodes), "countywide_vest_2020")
            continue
        candidates = {int(node) for node in row["graph_node_ids"].split(";") if node}
        if not candidates <= nodes.keys():
            raise ValueError(f"Out-of-county graph link for {source_id(row)}")
        if not candidates:
            candidates = known_unresolved.get((county, row["precinct_code"]), set())

        geometry = geography.current_geometry(row)
        if len(candidates) == 1 and candidates <= clean and row["graph_match_status"] != "unmatched":
            destination = next(iter(candidates))
            add([row], {party: {destination: 1} for party in PARTIES}, "clean_match")
            if geometry is not None:
                located.append(geometry)
            continue

        match = geography.overlap(row, geometry, candidates)
        if match:
            weights, method, overlap = match
            add([row], weights, method, overlap)
            located.append(geometry)
        elif len(candidates) == 1:
            destination = next(iter(candidates))
            add([row], {party: {destination: 1} for party in PARTIES}, "single_canvass_link")
            if geometry is not None:
                located.append(geometry)
        elif candidates:
            add([row], geography.history(candidates), "candidate_nodes_vest_2020")
        else:
            unlocated.append(row)

    if unlocated:
        weights, method = geography.remaining_history(nodes, located)
        add(unlocated, weights, method)

    if Counter({field: sum(counts[field] for counts in allocated.values()) for field in VOTE_FIELDS}) != expected:
        raise ValueError(f"County totals failed to reconcile for {county}")
    return allocated, audit, assignments


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vest", type=Path, default=ROOT / "shapes/Ohio/vest-2020.zip")
    parser.add_argument("--blocks", type=Path, help="Ohio 2020 TIGER/Line tabulation block ZIP")
    parser.add_argument("--pl", type=Path, help="Ohio 2020 P.L. 94-171 file ZIP")
    parser.add_argument("--block-nodes", type=Path, help="Optional verified block_geoid,graph_node_id CSV")
    parser.add_argument("--output-directory", type=Path, default=ROOT / "output")
    args = parser.parse_args()
    if bool(args.blocks) != bool(args.pl):
        parser.error("Supply --blocks and --pl together for block-level disaggregation")
    if args.block_nodes and not args.blocks:
        parser.error("--block-nodes requires --blocks and --pl")

    data = json.loads((ROOT / "OH_pct20.json").read_text(encoding="utf-8"))
    all_nodes = {node["id"]: node for node in data["nodes"]}
    counties = defaultdict(dict)
    for node_id, node in all_nodes.items():
        counties[canonical(node["COUNTY"])][node_id] = node
    known_unresolved = unresolved_candidates(all_nodes)
    clean = {int(row["graph_node_id"]) for row in read_csv(ROOT / "output/perfect_recast_2020.csv")}
    geography = Geography(ROOT / "shapes", counties, args.vest, args.blocks, args.pl, args.block_nodes)

    folders = {canonical(folder.name): folder for folder in (ROOT / "output").iterdir()
               if (folder / "precinct_votes.csv").exists() or (folder / "county_votes.csv").exists()}
    if counties.keys() != folders.keys():
        raise ValueError(f"Graph and canvass county sets differ: {counties.keys() ^ folders.keys()}")
    node_votes, audit, methods = {}, [], Counter()
    for county_key, nodes in sorted(counties.items()):
        rows, countywide = county_rows(folders[county_key])
        geography.prepare_county(county_key, rows if not countywide else [], nodes.keys() - clean)
        allocated, details, assignments = allocate_county(rows, countywide, nodes, geography, known_unresolved, clean)
        audit.extend(details)
        methods.update(assignments)
        node_votes.update(allocated)
        print(f"{county_key}: {dict(assignments)}", flush=True)

    audit_fields = ["county", "source_precinct_codes", "source_precinct_names", "canvass_type",
                    "source_file", "graph_node_id", "allocation_method", "dominant_node_area_share",
                    "dem_weight", "rep_weight", *VOTE_FIELDS]
    node_fields = ["graph_node_id", "county", "orig_name", *VOTE_FIELDS]
    write_csv(args.output_directory / "recast_2026_to_2020_allocations.csv", audit_fields, audit)
    write_csv(args.output_directory / "recast_2026_to_2020.csv", node_fields, (
        {"graph_node_id": node_id, "county": node["COUNTY"], "orig_name": node["ORIG_NAME"],
         **{field: node_votes.get(node_id, {}).get(field, 0) for field in VOTE_FIELDS}}
        for node_id, node in sorted(all_nodes.items())
    ))
    print(f"Wrote {len(all_nodes):,} nodes. Canvass rows by method: {dict(methods)}")


if __name__ == "__main__":
    main()

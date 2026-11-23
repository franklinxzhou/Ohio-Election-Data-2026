#!/usr/bin/env python3
"""Crosswalk Union County precinct polygons to Census 2020 VTDs."""

import argparse
import json
from collections import defaultdict
from pathlib import Path

from shapely import make_valid, union_all
from shapely.geometry import shape

from extract import HEADING, SOURCE, read_votes, write_csv

COUNTY_FIELDS = "SDE.precinct_regionForService."


def rows(root, precincts, county_path, census_path):
    graph = json.loads((root / "OH_pct20.json").read_text())
    nodes = defaultdict(set)
    combined = set()
    for node in graph["nodes"]:
        if node["COUNTY"] == "UNION":
            members = [name.removesuffix("_UNION") for name in node["ORIG_NAME"].split(",")]
            for name in members:
                nodes[name].add(node["id"])
            if len(members) > 1:
                combined.update(members)

    current = defaultdict(list)
    for feature in json.loads(county_path.read_text())["features"]:
        name = feature["properties"][COUNTY_FIELDS + "PRECINCTNA"].strip().upper()
        current[name].append(make_valid(shape(feature["geometry"])))
    historic = {
        f["properties"]["BASENAME"]: make_valid(shape(f["geometry"]))
        for f in json.loads(census_path.read_text())["features"]
    }

    for code, name in sorted(precincts):
        boundary = union_all(current[name])
        overlaps = []
        for former, previous in historic.items():
            if boundary.intersects(previous):
                area = boundary.intersection(previous).area
                if area >= 0.02 * boundary.area or area >= 0.95 * previous.area:
                    overlaps.append((area / boundary.area, former, area / previous.area))
        overlaps.sort(reverse=True)
        _, primary, former_share = overlaps[0]
        ids = sorted({node for _, former, _ in overlaps for node in nodes[former]})
        if len(overlaps) > 1:
            status = "boundary_overlap"
        elif former_share < 0.95:
            status = "split_precinct"
        elif len(ids) > 1:
            status = "split_node"
        elif primary in combined:
            status = "combined_node"
        else:
            status = "exact" if name.upper() == primary else "normalized"
        detail = "; ".join(f"{former} ({share:.2%} current / {old_share:.2%} 2020)"
                           for share, former, old_share in overlaps)
        yield f"{code} | {name} | {status} | {';'.join(map(str, ids))} | {detail}"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("county_geojson", type=Path)
    parser.add_argument("census_geojson", type=Path)
    args = parser.parse_args()
    folder = Path(__file__).resolve().parent
    root = folder.parents[1]
    votes, pages = read_votes(root / SOURCE)
    notes = folder / "precinct_merges_splits.txt"
    preamble = notes.read_text().split(f"\n{HEADING}\n", 1)[0].rstrip()
    records = rows(root, votes, args.county_geojson, args.census_geojson)
    notes.write_text("\n".join([preamble, "", HEADING, *records, ""]))
    write_csv(folder, votes, pages)

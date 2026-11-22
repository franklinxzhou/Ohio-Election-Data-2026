#!/usr/bin/env python3
"""Intersect the county and city maps with the 2020 Census VTDs in EPSG:5070."""

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

from shapely import make_valid, union_all
from shapely.geometry import shape

HEADING = "Crosswalk rows"
DOCUMENTED = {
    "COMMERCIAL POINT CENTRAL": {"COMMERCIAL POINT EAST", "SCIOTO-SOUTH"},
    "COMMERCIAL POINT-EAST": {"SCIOTO-NORTH"},
    "COMMERCIAL POINT-WEST": {"COMMERCIAL POINT WEST", "SCIOTO-NORTH"},
}


def key(name):
    return re.sub(r"[^A-Z0-9]", "", name)


def polygons(paths, field):
    pieces = defaultdict(list)
    for path in paths:
        for feature in json.loads(path.read_text())["features"]:
            name = feature["properties"][field].strip().upper()
            if name and feature["geometry"]:
                pieces[name].append(make_valid(shape(feature["geometry"])))
    return {name: union_all(parts) for name, parts in pieces.items()}


def records(root, current_paths, historical_path):
    graph = json.loads((root / "OH_pct20.json").read_text())
    nodes = {}
    for node in graph["nodes"]:
        if node["COUNTY"] == "PICKAWAY":
            members = node["ORIG_NAME"].split(",")
            for member in members:
                nodes[member.removesuffix("_PICKAWAY")] = node["id"], len(members) > 1
    current = polygons(current_paths, "NAME")
    historic = polygons([historical_path], "BASENAME")
    for label, boundary in sorted(current.items()):
        name = "COMMERCIAL POINT CENTRAL" if label == "COMMERCIAL POINT-CENTRAL" else label
        overlaps = []
        for old, previous in historic.items():
            area = boundary.intersection(previous).area
            if (area >= 0.02 * boundary.area or area >= 0.95 * previous.area
                    or old in DOCUMENTED.get(name, ())):
                overlaps.append((area / boundary.area, old, area / previous.area))
        overlaps.sort(reverse=True)
        _, primary, previous_share = overlaps[0]
        ids = sorted({nodes[old][0] for _, old, _ in overlaps})
        if len(overlaps) > 1:
            status = "boundary_overlap"
        elif key(name) != key(primary) and previous_share < 0.95:
            status = "split_precinct"
        elif nodes[primary][1]:
            status = "combined_node"
        else:
            status = "exact" if name == primary else "normalized"
        detail = "; ".join(f"{old} ({share:.2%} current / {former:.2%} former)"
                           for share, old, former in overlaps)
        yield f"{name} | {status} | {';'.join(map(str, ids))} | {detail}"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("county_geojson", type=Path)
    parser.add_argument("city_geojson", type=Path)
    parser.add_argument("census_geojson", type=Path)
    args = parser.parse_args()
    folder = Path(__file__).resolve().parent
    notes = folder / "precinct_merges_splits.txt"
    preamble = notes.read_text().split("\n" + HEADING + "\n", 1)[0].rstrip()
    rows = records(folder.parents[1], [args.county_geojson, args.city_geojson], args.census_geojson)
    notes.write_text("\n".join([preamble, "", HEADING, *rows, ""]))

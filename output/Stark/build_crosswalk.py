#!/usr/bin/env python3
"""Intersect the county precinct map with the 2020 Census VTDs in EPSG:5070."""

import argparse
import json
from collections import defaultdict
from pathlib import Path

from shapely import make_valid, union_all
from shapely.geometry import shape

HEADING = "Crosswalk rows"


def precinct_code(code):
    if code.startswith("CAN.C"):
        return "CC" + code.removeprefix("CAN.C")
    if code.startswith("N.CAN"):
        return "NC" + code.removeprefix("N.CAN")
    return "MLAKE" if code == "MLAKA" else code


def records(root, county_path, census_path):
    graph = json.loads((root / "OH_pct20.json").read_text())
    nodes = defaultdict(set)
    combined = set()
    for node in graph["nodes"]:
        if node["COUNTY"] == "STARK":
            members = [name.removesuffix("_STARK") for name in node["ORIG_NAME"].split(",")]
            for name in members:
                nodes[name].add(node["id"])
            if len(members) > 1:
                combined.update(members)
    parts, names = defaultdict(list), {}
    for feature in json.loads(county_path.read_text())["features"]:
        attrs = feature["properties"]
        code = precinct_code(attrs["BOEPREID"])
        names[code] = attrs["NAME"]
        parts[code].append(make_valid(shape(feature["geometry"])))
    historic = {
        f["properties"]["BASENAME"]: make_valid(shape(f["geometry"]))
        for f in json.loads(census_path.read_text())["features"]
    }
    for code, pieces in sorted(parts.items()):
        boundary = union_all(pieces)
        overlaps = []
        for old, previous in historic.items():
            area = boundary.intersection(previous).area
            if area >= .02 * boundary.area or area >= .95 * previous.area:
                overlaps.append((area / boundary.area, old, area / previous.area))
        overlaps.sort(reverse=True)
        _, primary, former_share = overlaps[0]
        name = names[code]
        ids = sorted({node for _, old, _ in overlaps for node in nodes[old]})
        if len(overlaps) > 1:
            status = "boundary_overlap"
        elif name != primary and former_share < .95:
            status = "split_precinct"
        elif len(ids) > 1:
            status = "split_node"
        elif primary in combined:
            status = "combined_node"
        else:
            status = "exact" if name == primary else "normalized"
        detail = "; ".join(f"{old} ({share:.2%} current / {former:.2%} former)"
                           for share, old, former in overlaps)
        yield f"{code} | {name} | {status} | {';'.join(map(str, ids))} | {detail}"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("county_geojson", type=Path)
    parser.add_argument("census_geojson", type=Path)
    args = parser.parse_args()
    folder = Path(__file__).resolve().parent
    notes = folder / "precinct_merges_splits.txt"
    preamble = notes.read_text().split("\n" + HEADING + "\n", 1)[0].rstrip()
    rows = records(folder.parents[1], args.county_geojson, args.census_geojson)
    notes.write_text("\n".join([preamble, "", HEADING, *rows, ""]))

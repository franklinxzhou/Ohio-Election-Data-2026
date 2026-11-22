#!/usr/bin/env python3
"""Regenerate the boundary records from the two sourced EPSG:5070 GeoJSON files."""

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

from shapely import STRtree, make_valid, union_all
from shapely.geometry import shape

from extract import BOUNDARY_HEADER, SOURCE, graph_members, key

GIS_LABELS = {
    "BEDFD06B": "BEDFORD-06-B",
    "OLMST00B": "OLMSTED TOWNSHIP-00-B",
}


def features(path):
    return json.loads(path.read_text(encoding="utf-8"))["features"]


def records(root, current_path, historical_path):
    with (root / SOURCE).open(encoding="utf-8-sig", newline="") as file:
        names = {key(row["PrecinctName"]) for row in csv.DictReader(file)}

    node_ids = defaultdict(set)
    for node_id, members, _ in graph_members(root):
        for member in members:
            node_ids[member].add(node_id)

    historical = []
    for feature in features(historical_path):
        props = feature["properties"]
        label = key(props["BASENAME"])
        if label == "NORTH OLMSTEAD-03-B":
            label = "NORTH OLMSTED-03-B"
        historical.append((label, props["GEOID"], make_valid(shape(feature["geometry"]))))
    tree = STRtree([polygon for _, _, polygon in historical])

    current = defaultdict(list)
    for feature in features(current_path):
        props = feature["properties"]
        label = key(GIS_LABELS.get(props["Precinct"], props["Name"]))
        current[label].append(make_valid(shape(feature["geometry"])))
    if names != current.keys():
        raise ValueError(f"GIS and canvass names differ: {sorted(names ^ current.keys())}")

    for name in sorted(names):
        precinct = union_all(current[name])
        overlaps = []
        for index in tree.query(precinct, predicate="intersects"):
            label, geoid, district = historical[index]
            area = precinct.intersection(district).area
            share = area / precinct.area
            if share >= 0.02:
                overlaps.append((share, label, geoid, area / district.area))
        overlaps.sort(key=lambda match: (-match[0], match[1]))
        if not overlaps:
            raise ValueError(f"No retained historical overlap for {name}")
        if [label for _, label, _, _ in overlaps] == [name]:
            continue

        status = "boundary_overlap"
        share, _, _, reverse = overlaps[0]
        if len(overlaps) == 1 and share >= 0.98:
            status = "renamed" if reverse >= 0.98 else "split_precinct"
        ids = sorted({node_id for _, label, _, _ in overlaps for node_id in node_ids[label]})
        nodes = ";".join(map(str, ids))
        detail = "; ".join(f"{label} ({geoid}) {share:.3%}" for share, label, geoid, _ in overlaps)
        yield f"{name} | {status} | {nodes} | {detail}\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("current", type=Path)
    parser.add_argument("historical", type=Path)
    args = parser.parse_args()
    folder = Path(__file__).resolve().parent
    notes = folder / "precinct_merges_splits.txt"
    preamble, heading, _ = notes.read_text(encoding="utf-8").partition(BOUNDARY_HEADER + "\n")
    if not heading:
        raise ValueError("Missing boundary records heading")
    rows = "".join(records(folder.parents[1], args.current, args.historical))
    notes.write_text(preamble + heading + rows, encoding="utf-8")

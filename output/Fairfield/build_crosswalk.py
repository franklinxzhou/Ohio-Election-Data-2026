#!/usr/bin/env python3
"""Regenerate the boundary records from the county shapefile ZIP and 2020 EPSG:5070 GeoJSON."""

import argparse
import json
import re
from zipfile import ZipFile
from collections import defaultdict
from pathlib import Path

import shapefile
from pyproj import CRS, Transformer
from shapely import STRtree, make_valid, transform, union_all
from shapely.geometry import shape

from extract import BOUNDARY_HEADER, SOURCE, graph_key, graph_members, read_panels

def features(path):
    return json.loads(path.read_text(encoding="utf-8"))["features"]


def records(root, current_path, historical_path):
    panels = read_panels(root / SOURCE)
    codes = {code for page in range(1, 5) for code in panels[page]}

    node_ids = defaultdict(set)
    for node_id, members, _ in graph_members(root):
        for member in members:
            node_ids[member].add(node_id)

    historical = []
    for feature in features(historical_path):
        props = feature["properties"]
        label = props["BASENAME"]
        historical.append((label, props["GEOID"], make_valid(shape(feature["geometry"]))))
    tree = STRtree([polygon for _, _, polygon in historical])

    with ZipFile(current_path) as archive:
        crs = CRS.from_wkt(archive.read("precincts.prj").decode())
    project = Transformer.from_crs(crs, 5070, always_xy=True).transform
    current = defaultdict(list)
    with shapefile.Reader(str(current_path)) as reader:
        for row in reader.iterShapeRecords():
            code = row.record["ALLCAPS"]
            if re.fullmatch(r"\d[A-E]", code):
                code = f"LAN-{code}"
            elif code.startswith("LIV-"):
                code = code[:5]
            polygon = transform(shape(row.shape.__geo_interface__), project, interleaved=False)
            current[code].append(make_valid(polygon))
    if codes != current.keys():
        raise ValueError(f"GIS and canvass codes differ: {sorted(codes ^ current.keys())}")

    for code in sorted(codes):
        precinct = union_all(current[code])
        overlaps = []
        for index in tree.query(precinct, predicate="intersects"):
            label, geoid, district = historical[index]
            area = precinct.intersection(district).area
            share = area / precinct.area
            if share >= 0.02:
                overlaps.append((share, label, geoid, area / district.area))
        overlaps.sort(key=lambda match: (-match[0], match[1]))
        if not overlaps:
            raise ValueError(f"No retained historical overlap for {code}")
        if [label for _, label, _, _ in overlaps] == [graph_key(code)]:
            continue

        status = "boundary_overlap"
        share, _, _, reverse = overlaps[0]
        if len(overlaps) == 1 and share >= 0.98:
            status = "renamed" if reverse >= 0.98 else "split_precinct"
        ids = sorted({node_id for _, label, _, _ in overlaps for node_id in node_ids[label]})
        nodes = ";".join(map(str, ids))
        detail = "; ".join(f"{label} ({geoid}) {share:.3%}" for share, label, geoid, _ in overlaps)
        yield f"{code} | {status} | {nodes} | {detail}\n"


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

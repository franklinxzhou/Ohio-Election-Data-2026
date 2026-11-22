#!/usr/bin/env python3
"""Build Marion's crosswalk from the sourced Ohio 2024 ZIP and 2020 GeoJSON."""

import argparse
import json
import zipfile
from collections import defaultdict
from pathlib import Path

import shapefile
from pyproj import CRS, Transformer
from shapely import make_valid, transform, union_all
from shapely.geometry import shape

from extract import HEADING, SOURCE, read_votes


def records(root, ohio_zip, census_geojson):
    historic = {
        f["properties"]["BASENAME"].upper(): make_valid(shape(f["geometry"]))
        for f in json.loads(census_geojson.read_text())["features"]
    }
    county = union_all(list(historic.values()))
    with zipfile.ZipFile(ohio_zip) as archive:
        crs = CRS.from_wkt(archive.read("OH24.prj").decode())
    project = Transformer.from_crs(crs, 5070, always_xy=True).transform
    bbox = Transformer.from_crs(5070, crs, always_xy=True).transform_bounds(*county.bounds)
    current = defaultdict(list)
    with shapefile.Reader(ohio_zip) as layer:
        for row in layer.iterShapeRecords(bbox=bbox):
            polygon = make_valid(transform(shape(row.shape.__geo_interface__), project, interleaved=False))
            if county.intersection(polygon).area >= 0.5 * polygon.area:
                name = row.record["Statewides"].upper().removeprefix("PRECINCT ")
                current[name].append(polygon)

    graph = json.loads((root / "OH_pct20.json").read_text())
    matches = defaultdict(dict)
    for node in graph["nodes"]:
        if node["COUNTY"] == "MARION":
            members = node["ORIG_NAME"].split(",")
            for member in members:
                matches[member.removesuffix("_MARION")][node["id"]] = len(members) > 1
    labels = read_votes(root / SOURCE)[0]
    if {name.upper().replace("TOWNSHIP", "TWP") for _, name in labels} != current.keys():
        raise ValueError("Map and canvass precinct names differ")
    for code, name in sorted(labels):
        key = name.upper().replace("TOWNSHIP", "TWP")
        polygon = union_all(current[key])
        overlaps = []
        for old, district in historic.items():
            area = polygon.intersection(district).area
            if area >= 0.02 * polygon.area or area >= 0.95 * district.area:
                overlaps.append((area / polygon.area, old, area / district.area))
        overlaps.sort(reverse=True)
        if not overlaps or any(old not in matches for _, old, _ in overlaps):
            raise ValueError(f"Missing historical graph match for {name}")
        nodes = {node: combined for _, old, _ in overlaps for node, combined in matches[old].items()}
        share, old, reverse = overlaps[0]
        if len(overlaps) > 1:
            status = "merged_precinct" if all(rev >= 0.95 for _, _, rev in overlaps) else "boundary_overlap"
        elif share < 0.98 and old != key:
            status = "boundary_overlap"
        elif old != key:
            status = "renamed" if reverse >= 0.98 else "split_precinct"
        elif len(nodes) > 1:
            status = "split_nodes"
        elif any(nodes.values()):
            status = "combined_node"
        else:
            status = "exact" if name.upper() == key else "normalized"
        ids = ";".join(map(str, sorted(nodes)))
        detail = "; ".join(f"{label} ({fraction:.2%})" for fraction, label, _ in overlaps)
        yield f"{code} {name} | {status} | {ids} | {detail}\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ohio_zip", type=Path)
    parser.add_argument("census_geojson", type=Path)
    args = parser.parse_args()
    folder = Path(__file__).resolve().parent
    notes = folder / "precinct_merges_splits.txt"
    preamble, heading, _ = notes.read_text().partition(HEADING + "\n")
    if not heading:
        raise ValueError("Missing precinct crosswalk heading")
    crosswalk = "".join(records(folder.parents[1], args.ohio_zip, args.census_geojson))
    notes.write_text(preamble + heading + crosswalk)

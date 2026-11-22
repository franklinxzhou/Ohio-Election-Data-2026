#!/usr/bin/env python3
"""Derive Montgomery graph links from county precincts and 2020 Census VTDs."""

import argparse
import json
import re
import zipfile
from collections import defaultdict
from pathlib import Path

import shapefile
from pyproj import CRS, Transformer
from shapely import STRtree, make_valid, transform, union_all
from shapely.geometry import shape

LAYER = "Precinct_2022_Polygon"
HEADING = "Crosswalk rows"


def normalized(name):
    name = re.sub(r" (?:TOWNSHIP|TWP)\b", "", name)
    name = name.replace("W CARROLLTON", "WEST CARROLLTON")
    name = re.sub(r"(?<= )0(?=\d)", "", name)
    return re.sub(r"[^A-Z0-9]", "", name)


def records(root, county_zip, census_geojson):
    graph = json.loads((root / "OH_pct20.json").read_text())
    ids = defaultdict(set)
    groups = defaultdict(list)
    for node in graph["nodes"]:
        if node["COUNTY"] == "MONTGOMERY":
            names = tuple(s.removesuffix("_MONTGOMERY") for s in node["ORIG_NAME"].split(","))
            groups[names].append(node["id"])
            for name in names:
                ids[name].add(node["id"])
    combined = {name for names in groups if len(names) > 1 for name in names}

    features = json.loads(census_geojson.read_text())["features"]
    old_names = [f["properties"]["BASENAME"].upper() for f in features]
    old_shapes = [make_valid(shape(f["geometry"])) for f in features]
    tree = STRtree(old_shapes)
    with zipfile.ZipFile(county_zip) as archive:
        crs = CRS.from_wkt(archive.read(f"{LAYER}.prj").decode())
    project = Transformer.from_crs(crs, 5070, always_xy=True).transform
    pieces, names = defaultdict(list), {}
    with shapefile.Reader(f"{county_zip}/{LAYER}.shp") as layer:
        for row in layer.iterShapeRecords():
            code = re.sub(r"(?<= )0(?=\d)", "", row.record["VLABEL"])
            names[code] = row.record["VNAME"]
            pieces[code].append(make_valid(transform(
                shape(row.shape.__geo_interface__), project, interleaved=False,
            )))

    group_lines = [
        f"  {', '.join(map(str, node_ids))} | {', '.join(members)}"
        for members, node_ids in groups.items() if len(members) > 1 or len(node_ids) > 1
    ]
    lines = []
    for code, polygons in sorted(pieces.items()):
        polygon = union_all(polygons)
        overlaps = []
        for idx in tree.query(polygon):
            old = old_shapes[idx]
            area = polygon.intersection(old).area
            if area >= 0.02 * polygon.area or area >= 0.95 * old.area:
                overlaps.append((area / polygon.area, old_names[idx], area / old.area))
        overlaps.sort(reverse=True)
        _, predecessor, old_share = overlaps[0]
        name = names[code]
        linked = sorted({node for _, old, _ in overlaps for node in ids[old]})
        if len(overlaps) > 1:
            status = "boundary_overlap"
        elif normalized(name) != normalized(predecessor) and old_share < 0.95:
            status = "split_precinct"
        elif len(linked) > 1:
            status = "split_node"
        elif predecessor in combined:
            status = "combined_node"
        else:
            status = "exact" if name == predecessor else "normalized"
        detail = "; ".join(f"{old} ({part:.2%} current / {before:.2%} former)"
                           for part, old, before in overlaps)
        lines.append(f"{code} | {name} | {status} | {';'.join(map(str, linked))} | {detail}")
    return group_lines, lines


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("county_zip", type=Path)
    parser.add_argument("census_geojson", type=Path)
    args = parser.parse_args()
    folder = Path(__file__).resolve().parent
    notes = folder / "precinct_merges_splits.txt"
    marker = "\nShared or split graph groups\n"
    preamble = notes.read_text().split(marker, 1)[0].rstrip()
    groups, links = records(folder.parents[1], args.county_zip, args.census_geojson)
    notes.write_text("\n".join([preamble, "", marker.strip(), *groups, "", HEADING, *links, ""]))

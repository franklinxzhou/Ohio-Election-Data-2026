#!/usr/bin/env python3
"""Crosswalk Summit's 2024 precinct boundaries to 2020 VTDs in EPSG:5070."""

import argparse
import gzip
import json
from collections import defaultdict
from pathlib import Path

from pyproj import Transformer
from shapely import make_valid, transform
from shapely.geometry import shape

from extract import HEADING, SOURCE, precinct_headings

REVISED = {"GREEN 1-A", "GREEN 1-B", "GREEN 1-C"}


def records(root, current_path, census_path):
    graph = json.loads((root / "OH_pct20.json").read_text())
    nodes = defaultdict(set)
    combined = set()
    for node in graph["nodes"]:
        if node["COUNTY"] == "SUMMIT":
            members = [name.removesuffix("_SUMMIT") for name in node["ORIG_NAME"].split(",")]
            for name in members:
                nodes[name].add(node["id"])
            if len(members) > 1:
                combined.update(members)

    project = Transformer.from_crs(4326, 5070, always_xy=True).transform
    with gzip.open(current_path, "rt") as file:
        current = {
            f["properties"]["GEOID"].removeprefix("39153-"):
            make_valid(transform(shape(f["geometry"]), project, interleaved=False))
            for f in json.load(file)["features"]
            if f["properties"]["GEOID"].startswith("39153-")
        }
    historic = {
        f["properties"]["BASENAME"]: make_valid(shape(f["geometry"]))
        for f in json.loads(census_path.read_text())["features"]
    }
    for code, name in precinct_headings(root / SOURCE):
        boundary = current[name]
        overlaps = []
        for old, previous in historic.items():
            if boundary.intersects(previous):
                area = boundary.intersection(previous).area
                if area >= 0.02 * boundary.area or area >= 0.95 * previous.area:
                    overlaps.append((area / boundary.area, old, area / previous.area))
        overlaps.sort(reverse=True)
        _, primary, former_share = overlaps[0]
        ids = sorted({node for _, old, _ in overlaps for node in nodes[old]})
        if name in REVISED:
            status, ids = "unmatched", []
        elif len(overlaps) > 1:
            status = "boundary_overlap"
        elif former_share < 0.95:
            status = "split_precinct"
        elif len(ids) > 1:
            status = "split_node"
        elif primary in combined:
            status = "combined_node"
        else:
            status = "exact" if name == primary else "normalized"
        detail = "; ".join(f"{old} ({share:.2%} 2024 / {former:.2%} 2020)"
                           for share, old, former in overlaps)
        yield f"{code} | {name} | {status} | {';'.join(map(str, ids))} | {detail}"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ohio_2024_geojson_gz", type=Path)
    parser.add_argument("census_geojson", type=Path)
    args = parser.parse_args()
    folder = Path(__file__).resolve().parent
    notes = folder / "precinct_merges_splits.txt"
    preamble = notes.read_text().split(f"\n{HEADING}\n", 1)[0].rstrip()
    rows = records(folder.parents[1], args.ohio_2024_geojson_gz, args.census_geojson)
    notes.write_text("\n".join([preamble, "", HEADING, *rows, ""]))

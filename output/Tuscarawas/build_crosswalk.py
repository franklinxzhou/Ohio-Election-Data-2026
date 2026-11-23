#!/usr/bin/env python3
"""Crosswalk 2024 Tuscarawas precinct polygons to Census 2020 VTDs."""

import argparse
import gzip
import json
from collections import defaultdict
from pathlib import Path

from pyproj import Transformer
from shapely import make_valid, transform
from shapely.geometry import shape

from extract import HEADING, SOURCE, read_votes, write_csv

# 2026 ballots and canvass identify 077 as West and 078 as East.
GEOMETRY_CODE = {"077": "078", "078": "077"}


def rows(root, precincts, county_path, census_path):
    graph = json.loads((root / "OH_pct20.json").read_text())
    nodes = defaultdict(set)
    combined = set()
    for node in graph["nodes"]:
        if node["COUNTY"] == "TUSCARAWAS":
            members = [name.removesuffix("_TUSCARAWAS") for name in node["ORIG_NAME"].split(",")]
            for name in members:
                nodes[name].add(node["id"])
            if len(members) > 1:
                combined.update(members)

    project = Transformer.from_crs(4326, 5070, always_xy=True).transform
    with gzip.open(county_path, "rt") as file:
        current = {
            f["properties"]["GEOID"][6:9]:
            make_valid(transform(shape(f["geometry"]), project, interleaved=False))
            for f in json.load(file)["features"]
            if f["properties"]["GEOID"].startswith("39157-")
        }
    historic = {
        f["properties"]["BASENAME"]: make_valid(shape(f["geometry"]))
        for f in json.loads(census_path.read_text())["features"]
    }

    for code, name in sorted(precincts):
        boundary = current[GEOMETRY_CODE.get(code, code)]
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
        detail = "; ".join(f"{former} ({share:.2%} 2024 / {old_share:.2%} 2020)"
                           for share, former, old_share in overlaps)
        yield f"{code} | {name} | {status} | {';'.join(map(str, ids))} | {detail}"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ohio_2024_geojson_gz", type=Path)
    parser.add_argument("census_geojson", type=Path)
    args = parser.parse_args()
    folder = Path(__file__).resolve().parent
    root = folder.parents[1]
    votes, pages = read_votes(root / SOURCE)
    notes = folder / "precinct_merges_splits.txt"
    preamble = notes.read_text().split(f"\n{HEADING}\n", 1)[0].rstrip()
    records = rows(root, votes, args.ohio_2024_geojson_gz, args.census_geojson)
    notes.write_text("\n".join([preamble, "", HEADING, *records, ""]))
    write_csv(folder, votes, pages)

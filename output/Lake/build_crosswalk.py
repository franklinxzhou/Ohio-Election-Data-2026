#!/usr/bin/env python3
"""Rebuild Lake's crosswalk exceptions from the two cited EPSG:5070 GeoJSON layers."""

import argparse
import json
from pathlib import Path

from shapely import make_valid
from shapely.geometry import shape

from extract import BOUNDARY_HEADER, NOTES, graph_matches


def polygons(path, field):
    return {
        feature["properties"][field].strip().upper(): make_valid(shape(feature["geometry"]))
        for feature in json.loads(path.read_text(encoding="utf-8"))["features"]
    }


def records(root, county_path, census_path):
    matches = graph_matches(root)
    current = polygons(county_path, "NAME")
    historic = polygons(census_path, "BASENAME")
    historic.pop("VOTING DISTRICTS NOT DEFINED")
    for name, precinct in sorted(current.items()):
        overlaps = []
        for old_name, polygon in historic.items():
            area = precinct.intersection(polygon).area
            if area >= 0.02 * precinct.area:
                overlaps.append((area / precinct.area, old_name))
        overlaps.sort(reverse=True)
        if not overlaps:
            raise ValueError(f"No historical overlap for {name}")
        if [old_name for _, old_name in overlaps] == [name]:
            continue
        ids = sorted({node for _, old_name in overlaps for node in matches[old_name]})
        detail = "; ".join(f"{old_name} ({share:.2%})" for share, old_name in overlaps)
        yield f"{name} | boundary_overlap | {';'.join(map(str, ids))} | {detail}\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("county_geojson", type=Path)
    parser.add_argument("census_geojson", type=Path)
    args = parser.parse_args()
    folder = Path(__file__).resolve().parent
    notes = folder / NOTES
    preamble, heading, _ = notes.read_text(encoding="utf-8").partition(BOUNDARY_HEADER + "\n")
    if not heading:
        raise ValueError("Missing boundary records heading")
    exceptions = "".join(records(folder.parents[1], args.county_geojson, args.census_geojson))
    notes.write_text(preamble + heading + exceptions, encoding="utf-8")

#!/usr/bin/env python3
"""Rebuild the Lorain crosswalk from the cited current and 2020 GeoJSON files."""

import argparse
import json
from pathlib import Path

from pyproj import Transformer
from shapely import STRtree, make_valid, transform
from shapely.geometry import shape

from extract import BOUNDARY_HEADER, NOTES, graph_matches, graph_name

# The public map transposes these labels, as shown by the township maps.
CORRECTED_LABELS = {"BRIGHTON TWP": "BROWNHELM TWP", "BROWNHELM TWP": "BRIGHTON TWP"}
UNDEFINED = "VOTING DISTRICTS NOT DEFINED"


def records(root, county_path, census_path):
    matches = graph_matches(root)
    old_names, old_polygons = [], []
    for feature in json.loads(census_path.read_text())["features"]:
        name = feature["properties"]["BASENAME"].upper().removeprefix("PRECINCT ")
        if name != UNDEFINED:
            old_names.append(name)
            old_polygons.append(make_valid(shape(feature["geometry"])))
    tree = STRtree(old_polygons)
    project = Transformer.from_crs(4326, 5070, always_xy=True).transform
    rows = []
    for feature in json.loads(county_path.read_text())["features"]:
        label = feature["properties"]["precinct"]
        name = CORRECTED_LABELS.get(label, label)
        geometry = transform(shape(feature["geometry"]), project, interleaved=False)
        precinct = make_valid(geometry)
        overlaps = []
        for i in tree.query(precinct, predicate="intersects"):
            other = old_polygons[i]
            area = precinct.intersection(other).area
            if area >= 0.02 * precinct.area:
                overlaps.append((area / precinct.area, old_names[i], area / other.area))
        overlaps.sort(reverse=True)
        if not overlaps:
            raise ValueError(f"No historical match for {name}")
        if [old for _, old, _ in overlaps] == [graph_name(name)]:
            continue
        status = "boundary_overlap"
        share, _, reverse_share = overlaps[0]
        if len(overlaps) == 1 and share >= 0.98:
            status = "renamed" if reverse_share >= 0.98 else "split_precinct"
        ids = sorted({node for _, old, _ in overlaps for node in matches[old]})
        detail = "; ".join(f"{old} ({share:.2%})" for share, old, _ in overlaps)
        rows.append(f"{name} | {status} | {';'.join(map(str, ids))} | {detail}\n")
    return sorted(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("county_geojson", type=Path)
    parser.add_argument("census_geojson", type=Path)
    args = parser.parse_args()
    folder = Path(__file__).resolve().parent
    notes = folder / NOTES
    preamble, heading, _ = notes.read_text().partition(BOUNDARY_HEADER + "\n")
    if not heading:
        raise ValueError("Missing boundary records heading")
    exceptions = records(folder.parents[1], args.county_geojson, args.census_geojson)
    notes.write_text(preamble + heading + "".join(exceptions))

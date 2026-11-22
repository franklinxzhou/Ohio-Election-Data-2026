#!/usr/bin/env python3
"""Build Miami boundary links from the county precinct ZIP and 2020 Census GeoJSON."""

import argparse
import json
import zipfile
from collections import defaultdict
from pathlib import Path

import shapefile
from pyproj import CRS, Transformer
from shapely import make_valid, transform, union_all
from shapely.geometry import shape

from extract import HEADING, graph_matches, graph_name


def records(root, county_zip, census_geojson):
    matches = graph_matches(root)
    historic = {
        f["properties"]["BASENAME"].upper(): make_valid(shape(f["geometry"]))
        for f in json.loads(census_geojson.read_text())["features"]
    }
    with zipfile.ZipFile(county_zip) as archive:
        prj, = [name for name in archive.namelist() if name.endswith(".prj")]
        crs = CRS.from_wkt(archive.read(prj).decode())
    project = Transformer.from_crs(crs, 5070, always_xy=True).transform
    current = defaultdict(list)
    with shapefile.Reader(county_zip) as layer:
        for row in layer.iterShapeRecords():
            label = row.record["ID_Name"].strip()
            if label:
                polygon = transform(shape(row.shape.__geo_interface__), project, interleaved=False)
                current[label].append(make_valid(polygon))
    for label, pieces in sorted(current.items()):
        precinct = union_all(pieces)
        overlaps = []
        for old, district in historic.items():
            area = precinct.intersection(district).area
            if area >= 0.02 * precinct.area or area >= 0.95 * district.area:
                overlaps.append((area / precinct.area, old))
        overlaps.sort(reverse=True)
        names = [old for _, old in overlaps]
        if not names:
            raise ValueError(f"No historical match for {label}")
        if names == [graph_name(label[4:])] and label != "086 HUBER HEIGHTS B":
            continue
        status = "split_precinct" if label in {"086 HUBER HEIGHTS B", "088 HUBER HEIGHTS D"} else "boundary_overlap"
        ids = ";".join(map(str, sorted({matches[name][0] for name in names})))
        detail = "; ".join(f"{name} ({share:.2%})" for share, name in overlaps)
        yield f"{label} | {status} | {ids} | {detail}\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("county_zip", type=Path)
    parser.add_argument("census_geojson", type=Path)
    args = parser.parse_args()
    folder = Path(__file__).resolve().parent
    notes = folder / "precinct_merges_splits.txt"
    preamble, heading, _ = notes.read_text().partition(HEADING + "\n")
    if not heading:
        raise ValueError("Missing crosswalk heading")
    notes.write_text(preamble + heading + "".join(records(folder.parents[1], args.county_zip, args.census_geojson)))

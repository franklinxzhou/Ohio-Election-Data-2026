#!/usr/bin/env python3
"""Regenerate the Knox boundary records from the cited county ZIP and TIGERweb GeoJSON."""

import argparse
import io
import json
import zipfile
from collections import defaultdict
from pathlib import Path

import shapefile
from pyproj import CRS, Transformer
from shapely import make_valid, transform, union_all
from shapely.geometry import shape

from extract import BOUNDARY_HEADER, NOTES, graph_matches, historical_name


def records(root, county_zip, census_geojson):
    matches = graph_matches(root)
    historic = {
        feature["properties"]["BASENAME"]: make_valid(shape(feature["geometry"]))
        for feature in json.loads(census_geojson.read_text())["features"]
    }
    current = defaultdict(list)
    with zipfile.ZipFile(county_zip) as archive:
        reader = shapefile.Reader(**{
            ext: io.BytesIO(archive.read(f"vote_precincts.{ext}")) for ext in ("shp", "shx", "dbf")
        })
        crs = CRS.from_wkt(archive.read("vote_precincts.prj").decode())
        project = Transformer.from_crs(crs, 5070, always_xy=True).transform
        for item in reader.iterShapeRecords():
            name = item.record["NAME"].strip().upper()
            if name == "CLAY":
                name = "CLAY-MART"
            geometry = transform(shape(item.shape.__geo_interface__), project, interleaved=False)
            current[name].append(make_valid(geometry))

    for name, pieces in sorted(current.items()):
        polygon = union_all(pieces)
        overlaps = []
        for old_name, old_polygon in historic.items():
            area = polygon.intersection(old_polygon).area
            if area >= 0.02 * polygon.area:
                overlaps.append((area / polygon.area, old_name))
        overlaps.sort(reverse=True)
        if not overlaps:
            raise ValueError(f"No historical match for {name}")
        if [old_name for _, old_name in overlaps] == [historical_name(name)]:
            continue
        status = "split_precinct" if name in {"MILFORD A", "MILFORD B", "PLEASANT A", "PLEASANT B"} else "boundary_overlap"
        ids = sorted({node for _, old_name in overlaps for node in matches[old_name]})
        detail = "; ".join(f"{old_name} ({share:.2%})" for share, old_name in overlaps)
        yield f"{name} | {status} | {';'.join(map(str, ids))} | {detail}\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("county_zip", type=Path)
    parser.add_argument("census_geojson", type=Path)
    args = parser.parse_args()
    folder = Path(__file__).resolve().parent
    notes = folder / NOTES
    preamble, heading, _ = notes.read_text().partition(BOUNDARY_HEADER + "\n")
    if not heading:
        raise ValueError("Missing boundary records heading")
    overlaps = "".join(records(folder.parents[1], args.county_zip, args.census_geojson))
    notes.write_text(preamble + heading + overlaps)

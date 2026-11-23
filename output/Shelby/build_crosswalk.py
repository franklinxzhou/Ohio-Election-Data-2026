#!/usr/bin/env python3
"""Map Shelby precinct polygons to 2020 Census voting districts and graph nodes."""

import argparse
import json
from collections import defaultdict
from pathlib import Path

from pyproj import Transformer
from shapely import make_valid, symmetric_difference_all, transform, union_all
from shapely.geometry import Polygon, shape

HEADING = "Crosswalk exceptions"


def records(root, county_file, census_file):
    graph = json.loads((root / "OH_pct20.json").read_text())
    nodes = {
        member.removesuffix("_SHELBY"): node["id"]
        for node in graph["nodes"] if node["COUNTY"] == "SHELBY"
        for member in node["ORIG_NAME"].split(",")
    }
    county = json.loads(county_file.read_text())
    project = Transformer.from_crs(county["spatialReference"]["latestWkid"], 5070, always_xy=True)
    pieces = defaultdict(list)
    for feature in county["features"]:
        code = int(feature["attributes"]["Precinct_Number"].rsplit("#", 1)[1])
        rings = [make_valid(Polygon(ring)) for ring in feature["geometry"]["rings"]]
        polygon = symmetric_difference_all(rings)
        pieces[code].append(make_valid(transform(polygon, project.transform, interleaved=False)))

    census = json.loads(census_file.read_text())
    historic = {
        f["properties"]["BASENAME"]: make_valid(shape(f["geometry"]))
        for f in census["features"]
    }
    for code, parts in sorted(pieces.items()):
        current = union_all(parts)
        links = []
        for name, old in historic.items():
            area = current.intersection(old).area
            if area >= .02 * current.area or area >= .95 * old.area:
                links.append((area / current.area, name, area / old.area))
        links.sort(reverse=True)
        _, primary, old_share = links[0]
        if len(links) == 1 and int(primary.split()[0]) == code:
            continue
        status = "split_precinct" if len(links) == 1 and old_share < .95 else "boundary_overlap"
        ids = ";".join(map(str, sorted({nodes[name] for _, name, _ in links})))
        details = "; ".join(f"{name} ({share:.2%} current / {former:.2%} former)"
                            for share, name, former in links)
        yield f"{code} | {status} | {ids} | {details}"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("county_json", type=Path)
    parser.add_argument("census_geojson", type=Path)
    args = parser.parse_args()
    folder = Path(__file__).resolve().parent
    notes = folder / "precinct_merges_splits.txt"
    preamble = notes.read_text().split("\n" + HEADING + "\n", 1)[0].rstrip()
    rows = records(folder.parents[1], args.county_json, args.census_geojson)
    notes.write_text("\n".join([preamble, "", HEADING, *rows, ""]))

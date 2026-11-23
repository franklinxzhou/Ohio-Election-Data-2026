#!/usr/bin/env python3
"""Crosswalk 2024 Wood precinct polygons to Census 2020 VTDs."""

import argparse
import gzip
import json
from collections import defaultdict
from pathlib import Path

from pyproj import Transformer
from shapely import make_valid, transform
from shapely.geometry import shape

from extract import HEADING, SOURCE, CODE, read_votes, write_csv
from pypdf import PdfReader

SHAPE_NAMES = {
    "CENTER TWP": "CENTER TOWNSHIP",
    "FREEDOM TWP": "FREEDOM TOWNSHIP",
    "FREEDOM TWP PEMBERVILLE": "FREEDOM TWP PEMBERVILLE VILL",
    "GRAND RAPIDS TWP GR": "GRAND RAPIDS TWP GR VILL",
    "LAKE TWP MILLBURY": "LAKE TWP MILLBURY VILL",
    "LAKE TWP WALBRIDGE A": "LAKE TWP WALBRIDGE VILL A",
    "LAKE TWP WALBRIDGE B": "LAKE TWP WALBRIDGE VILL B",
    "MIDDLETON TWP HASKINS": "MIDDLETON TWP HASKINS VILL",
    "TROY TWP LUCKEY": "TROY TWP LUCKEY VILL",
    "WASHINGTON TWP TONTOGANY": "WASHINGTON TWP TONTOGANY VILL",
    "WESTON VILLAGE": "WESTON TWP WESTON VILL",
}

DISTRICT_SPLIT_GROUPS = ({7861, 7862}, {7864, 7865})


def house_districts(source):
    districts = defaultdict(set)
    pdf = PdfReader(source)
    for district, numbers in ((44, (59,)), (75, (61, 62, 63, 64))):
        for number in numbers:
            layout = pdf.pages[number - 1].extract_text(extraction_mode="layout")
            for match in CODE.finditer(layout):
                districts[match[0][:3]].add(district)
    return districts


def rows(root, precincts, county_path, census_path):
    graph = json.loads((root / "OH_pct20.json").read_text())
    nodes = defaultdict(set)
    lower_district = {}
    combined = set()
    for node in graph["nodes"]:
        if node["COUNTY"] == "WOOD":
            lower_district[node["id"]] = node["ENACTED_LOWER"]
            members = [name.removesuffix("_WOOD") for name in node["ORIG_NAME"].split(",")]
            for name in members:
                nodes[name].add(node["id"])
            if len(members) > 1:
                combined.update(members)
    districts = house_districts(root / SOURCE)

    project = Transformer.from_crs(4326, 5070, always_xy=True).transform
    with gzip.open(county_path, "rt") as file:
        current = {
            f["properties"]["GEOID"][6:]:
            make_valid(transform(shape(f["geometry"]), project, interleaved=False))
            for f in json.load(file)["features"]
            if f["properties"]["GEOID"].startswith("39173-")
        }
    historic = {
        f["properties"]["BASENAME"]: make_valid(shape(f["geometry"]))
        for f in json.loads(census_path.read_text())["features"]
    }

    for code, name in sorted(precincts.items()):
        boundary = current[SHAPE_NAMES.get(name, name)]
        overlaps = []
        for former, previous in historic.items():
            if boundary.intersects(previous):
                area = boundary.intersection(previous).area
                if area >= 0.02 * boundary.area or area >= 0.95 * previous.area:
                    overlaps.append((area / boundary.area, former, area / previous.area))
        overlaps.sort(reverse=True)
        _, primary, former_share = overlaps[0]
        ids = {node for _, former, _ in overlaps for node in nodes[former]}
        used_district = False
        for group in DISTRICT_SPLIT_GROUPS:
            shared = ids & group
            if shared == group and code in districts:
                used_district = True
                ids.difference_update(node for node in shared
                                      if lower_district[node] not in districts[code])
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
        if used_district:
            detail += "; canvass House district(s) " + "/".join(map(str, sorted(districts[code])))
        yield f"{code} | {name} | {status} | {';'.join(map(str, sorted(ids)))} | {detail}"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ohio_2024_geojson_gz", type=Path)
    parser.add_argument("census_geojson", type=Path)
    args = parser.parse_args()
    folder = Path(__file__).resolve().parent
    root = folder.parents[1]
    names, votes, pages = read_votes(root / SOURCE)
    notes = folder / "precinct_merges_splits.txt"
    preamble = notes.read_text().split(f"\n{HEADING}\n", 1)[0].rstrip()
    records = rows(root, names, args.ohio_2024_geojson_gz, args.census_geojson)
    notes.write_text("\n".join([preamble, "", HEADING, *records, ""]))
    write_csv(folder, names, votes, pages)

#!/usr/bin/env python3
"""Extract Warren's April 2025 precinct paths and labels from its GeoPDF."""

import argparse
import json
import re
from pathlib import Path

from pypdf import PdfReader
from pyproj import CRS, Transformer
from shapely import make_valid, symmetric_difference_all, transform
from shapely.geometry import Point, Polygon, mapping

# Map-path indexes for labels absent from the precinct text layer.
# See the crosswalk notes for their geographic identification.
PATH_CODES = {0: 219, 41: 124, 77: 49, 83: 165, 101: 50,
              134: 218, 140: 122, 151: 167, 156: 223, 170: 151}


def map_paths(page):
    rings, stack = [], []
    offset = (0, 0)
    stroke, width = None, None
    for args, op in page.get_contents().operations:
        if op == b"q":
            stack.append((offset, stroke, width))
        elif op == b"Q" and stack:
            offset, stroke, width = stack.pop()
        elif op == b"cm":
            offset = float(args[4]) + offset[0], float(args[5]) + offset[1]
        elif op == b"RG":
            stroke = tuple(args)
        elif op == b"w":
            width = args[0]
        elif op in (b"m", b"l", b"c"):
            point = float(args[-2]) + offset[0], float(args[-1]) + offset[1]
            if op == b"m":
                rings.append([point])
            elif rings:
                rings[-1].append(point)
        elif op in (b"B*", b"f*", b"n", b"S", b"f", b"B", b"s", b"b", b"b*"):
            if op in (b"B*", b"f*") and stroke == (.204, .204, .204) and width == 2.016:
                yield symmetric_difference_all([make_valid(Polygon(r)) for r in rings if len(r) > 3])
            rings = []


def codes_by_path(page, polygons):
    labels = []

    def collect(text, _cm, tm, font, _size):
        if font and abs(tm[0] - 11.808) < .05 and re.fullmatch(r"\s*\d{1,3}\s*", text):
            text, x, y = text.strip(), tm[4], tm[5]
            if labels:
                last, left, baseline = labels[-1]
                if abs(baseline - y) < .02 and abs(left + 6.62 * len(last) - x) < 1:
                    labels[-1] = last + text, left, y
                    return
            labels.append((text, x, y))

    page.extract_text(visitor_text=collect)
    codes = {}
    for label, x, y in labels:
        point = Point(x + 3.31 * len(label), y + 4)
        indexes = [i for i, polygon in enumerate(polygons) if polygon.covers(point)]
        if len(indexes) == 1:
            codes[indexes[0]] = int(label)
    return codes | PATH_CODES


def page_transform(page):
    viewport = page["/VP"][0]
    measure = viewport["/Measure"]
    local = CRS.from_wkt(str(measure["/GCS"]["/WKT"]))
    to_local = Transformer.from_crs(4326, local, always_xy=True)
    to_equal_area = Transformer.from_crs(local, 5070, always_xy=True)
    left, top, right, bottom = map(float, viewport["/BBox"])
    coords = list(map(float, measure["/GPTS"]))
    sw, nw, ne, se = [to_local.transform(lon, lat)
                      for lat, lon in zip(coords[::2], coords[1::2])]
    scale_x = ((se[0] - sw[0]) + (ne[0] - nw[0])) / (2 * (right - left))
    scale_y = ((nw[1] - sw[1]) + (ne[1] - se[1])) / (2 * (top - bottom))

    def project(x, y):
        return to_equal_area.transform(sw[0] + (x - left) * scale_x, sw[1] + (y - bottom) * scale_y)

    return project


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("map_pdf", type=Path)
    parser.add_argument("output_geojson", type=Path)
    args = parser.parse_args()
    page = PdfReader(args.map_pdf).pages[0]
    polygons = list(map_paths(page))
    codes = codes_by_path(page, polygons)
    if len(polygons) != 185 or len(codes) != 185 or len(set(codes.values())) != 185:
        raise ValueError("Expected 185 uniquely identified precinct paths")
    project = page_transform(page)
    features = [{
        "type": "Feature", "properties": {"code": f"{codes[i]:03}"},
        "geometry": mapping(transform(polygon, project, interleaved=False)),
    } for i, polygon in enumerate(polygons)]
    args.output_geojson.write_text(json.dumps({"type": "FeatureCollection", "features": features}))

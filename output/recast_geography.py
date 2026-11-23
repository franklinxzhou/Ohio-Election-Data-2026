"""VEST geography and voting-age-population weights for the statewide recast."""

import csv
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree

import numpy as np
import shapely
from pyogrio import read_dataframe
from pyproj import Transformer
from shapely.geometry import Polygon, shape

AREA_CRS = "EPSG:5070"
SNAP_SHARE = 0.98
PARTIES = ("dem", "rep")
GRAPH_VOTES = {"dem": "G20PREDEM", "rep": "G20PREREP"}
VEST_VOTES = {"dem": "G20PREDBID", "rep": "G20PRERTRU"}

# County layers and the fields already used to link them to the canvasses.
# Historical proxy layers in shapes/ are excluded from 2026 overlays.
CURRENT = {
    "ATHENS": [("Athens/precincts.geojson", "precinctid", "code")],
    "AUGLAIZE": [("Auglaize/precincts.geojson", "PRECINCTID", "auglaize")],
    "BUTLER": [("Butler/precincts.kml", "name", "code")],
    "CLARK": [("Clark/precincts.geojson", "NAME", "name")],
    "CLERMONT": [("Clermont/precincts.geojson", "PRECINCT", "name")],
    "CUYAHOGA": [("Cuyahoga/precincts.geojson", "Name", "name")],
    "DELAWARE": [("Delaware/precincts.geojson", "precinctid", "delaware")],
    "FAIRFIELD": [("Fairfield/precincts.zip", "ALLCAPS", "fairfield")],
    "FRANKLIN": [("Franklin/precincts.geojson", "NAME", "name")],
    "GREENE": [("Greene/precincts.geojson", "PRECINCT", "code")],
    "HAMILTON": [("Hamilton/precincts.geojson", "PRECINCT", "code")],
    "HOCKING": [("Hocking/precincts.zip", "PRECINCT", "name")],
    "KNOX": [("Knox/precincts.zip", "NAME", "name")],
    "LAKE": [("Lake/precincts.geojson", "NAME", "name")],
    "LICKING": [("Licking/precincts.geojson", "PrecinctName", "name")],
    "LORAIN": [("Lorain/precincts.geojson", "precinct", "name")],
    "PICKAWAY": [("Pickaway/county-precincts.geojson", "NAME", "name"),
                 ("Pickaway/circleville-precincts.geojson", "NAME", "name")],
    "SHELBY": [("Shelby/precincts.esrijson", "Precinct_Number", "shelby")],
    "STARK": [("Stark/precincts.geojson", "BOEPREID", "code")],
    "UNION": [("Union/precincts.geojson", "SDE.precinct_regionForService.PRECINCTNA", "name")],
}

CUYAHOGA_LABELS = {"BEDFD06B": "BEDFORD-06-B", "OLMST00B": "OLMSTED TOWNSHIP-00-B"}
LICKING_LABELS = {
    "EDEN FALL TOWNSHIP": "Eden + Fallsbury Twps.",
    "HARRISON TWP B-KIRK": "Harrison Twp. B + Kirkersville Vlg.",
    "HARTFORD TWP-VLG": "Hartford Twp. + Hartford Vlg.",
    "NEWTON TWP B-ST LOU": "Newton Twp. B + St. Louisville Vlg.",
    "ST. ALBANS TWP B-ALEX": "St. Albans Twp. B + Alexandria Vlg.",
}


def canonical(text):
    return re.sub(r"[^A-Z0-9]", "", str(text).upper())


def former_name(text):
    return canonical(re.sub(r"^\d+\s+", "", text.strip()))


def current_key(text):
    text = str(text).upper().strip()
    text = text.replace("TOWNSHIP", "TWP").replace("VILLAGE", "VLG")
    text = text.replace("HARBOR", "HBR")
    return canonical(re.sub(r"(?<!\d)0+(?=\d)", "", text))


def code_key(text):
    key = canonical(text)
    return (key.lstrip("0") or "0") if key.isdecimal() else key


def gis_key(county, mode, value):
    label = str(value).upper()
    if mode == "auglaize":
        label = label.split("-", 1)[0]
    if mode == "delaware":
        label = label[:-2]
    if mode == "fairfield":
        if re.fullmatch(r"\d[A-E]", label):
            label = "LAN-" + label
        if label.startswith("LIV-"):
            label = label[:5]
    if mode == "shelby":
        label = label.rsplit("#", 1)[-1]
    if county == "STARK":
        label = label.replace("CAN.C", "CC").replace("N.CAN", "NC")
        if label == "MLAKA":
            label = "MLAKE"
    if county == "CLARK":
        for full, short in (("BETHEL", "BETH"), ("GERMAN", "GERM"), ("GREEN", "GREE"), ("HARMONY", "HARM")):
            label = re.sub(rf"^{full}\b", short, label)
    if county == "LAKE":
        label = re.sub(r"\b(MENTOR-ON-THE-LAKE|WILLOUGHBY HILLS) CITY\b", r"\1", label)
    return current_key(label) if mode == "name" else code_key(label)


def layer_path(path):
    return f"zip://{path.resolve()}" if path.suffix.lower() == ".zip" else path


def polygonal(geometry):
    if geometry is None or shapely.is_empty(geometry):
        return None
    geometry = shapely.make_valid(geometry)
    parts = [part for part in shapely.get_parts(geometry) if part.geom_type in ("Polygon", "MultiPolygon")]
    return shapely.union_all(parts) if parts else None


def projected(geometry, crs):
    transform = Transformer.from_crs(crs, AREA_CRS, always_xy=True).transform
    return polygonal(shapely.transform(geometry, transform, interleaved=False))


def kml_features(path):
    ns = {"kml": "http://www.opengis.net/kml/2.2"}
    root = ElementTree.parse(path).getroot()

    def ring(polygon, xpath):
        coordinates = polygon.findtext(xpath, namespaces=ns)
        return [tuple(float(x) for x in point.split(",")[:2]) for point in coordinates.split()]

    folders = [folder for folder in root.findall(".//kml:Folder", ns)
               if folder.findtext("kml:name", namespaces=ns) == "2026 Precincts"]
    if len(folders) != 1:
        raise ValueError("Expected the Butler 2026 Precincts KML folder")
    for placemark in folders[0].findall(".//kml:Placemark", ns):
        label = placemark.findtext("kml:name", namespaces=ns).split(".", 1)[0]
        for item in placemark.findall(".//kml:Polygon", ns):
            shell = ring(item, "kml:outerBoundaryIs/kml:LinearRing/kml:coordinates")
            holes = [ring(inner, "kml:LinearRing/kml:coordinates")
                     for inner in item.findall("kml:innerBoundaryIs", ns)]
            yield label, projected(Polygon(shell, holes), "EPSG:4326")


def current_layer(path, field):
    if path.suffix == ".kml":
        yield from kml_features(path)
        return
    if path.suffix == ".geojson":
        data = json.loads(path.read_text(encoding="utf-8"))
        crs = data.get("crs", {}).get("properties", {}).get("name", "EPSG:4326")
        for feature in data["features"]:
            if feature["geometry"] and feature["properties"].get(field):
                props = feature["properties"]
                label = props[field]
                if path.parent.name == "Cuyahoga":
                    label = CUYAHOGA_LABELS.get(props["Precinct"], label)
                yield label, projected(shape(feature["geometry"]), crs)
        return
    if path.suffix == ".esrijson":
        # Force the ESRIJSON driver on GDAL builds that select it by extension.
        path = f"ESRIJSON:{path}"
    layer = "precincts" if field == "ALLCAPS" else None
    data = read_dataframe(layer_path(Path(path)) if not isinstance(path, str) else path,
                          columns=[field], layer=layer).to_crs(AREA_CRS)
    yield from zip(data[field], map(polygonal, data.geometry))


def read_pl(path):
    """Join P3 total voting-age population to 2020 Census block GEOIDs."""
    records, counts = {}, {}
    with ZipFile(path) as archive, archive.open("ohgeo2020.pl") as geography:
        for line in geography:
            if line[8:11] == b"750":
                fields = line.split(b"|", 10)
                records[fields[7]] = fields[9].decode("ascii")
        with archive.open("oh000022020.pl") as population:
            for line in population:
                fields = line.split(b"|", 6)
                geoid = records.get(fields[4])
                if geoid:
                    counts[geoid] = int(fields[5])
    if not records or len(counts) != len(records):
        raise ValueError("Incomplete Ohio block geography and P3 join")
    return counts


@dataclass
class HistoricalPrecinct:
    geometry: object
    nodes: tuple
    votes: dict
    distribution: dict


class Geography:
    def __init__(self, shapes, counties, vest, blocks, pl, block_nodes):
        self.shapes = shapes
        self.county_fips = {name: f"{2 * index + 1:03}" for index, name in enumerate(sorted(counties))}
        self.past = defaultdict(list)
        self.baseline = {party: defaultdict(float) for party in PARTIES}
        self.block_nodes = {}
        self.graph_counties = {node: county for county, nodes in counties.items() for node in nodes}
        if block_nodes:
            with block_nodes.open(newline="", encoding="utf-8-sig") as file:
                for row in csv.DictReader(file):
                    geoid, node = row["block_geoid"], int(row["graph_node_id"])
                    county = self.graph_counties.get(node)
                    if (county is None or len(geoid) != 15 or
                        geoid[:5] != "39" + self.county_fips[county] or geoid in self.block_nodes):
                        raise ValueError(f"Invalid block assignment {row}")
                    self.block_nodes[geoid] = node
        self.load_vest(vest, counties)

        self.blocks = None
        if blocks:
            vap = read_pl(pl)
            data = read_dataframe(layer_path(blocks), columns=["GEOID20", "COUNTYFP20"])
            if set(vap) != set(data["GEOID20"]):
                raise ValueError("Census block shapefile and P.L. voter-age table have different GEOIDs")
            data["vap"] = data["GEOID20"].map(vap)
            self.blocks = {fips: county.to_crs(AREA_CRS) for fips, county in
                           data[data["vap"] > 0].groupby("COUNTYFP20")}

    def load_vest(self, path, counties):
        fips_county = {v: k for k, v in self.county_fips.items()}
        by_name = {}
        for county, nodes in counties.items():
            for node, info in nodes.items():
                for name in info["ORIG_NAME"].split(","):
                    key = (county, former_name(name.removesuffix("_" + info["COUNTY"])))
                    by_name.setdefault(key, set()).add(node)

        data = read_dataframe(layer_path(path), columns=["COUNTYFP20", "NAME20", *VEST_VOTES.values()]).to_crs(AREA_CRS)
        seen = set()
        for row in data.itertuples(index=False):
            county = fips_county[row.COUNTYFP20]
            key = (county, former_name(row.NAME20))
            node_ids = tuple(sorted(by_name.get(key, ())))
            if not node_ids or key in seen:
                raise ValueError(f"VEST and graph precinct names do not join uniquely: {county} {row.NAME20}")
            seen.add(key)
            votes = {party: int(getattr(row, field)) for party, field in VEST_VOTES.items()}
            distribution = {}
            for party in PARTIES:
                weights = [counties[county][node][GRAPH_VOTES[party]] for node in node_ids]
                if not sum(weights):
                    weights = [counties[county][node]["POP20"] for node in node_ids]
                denominator = sum(weights)
                distribution[party] = {node: w / denominator if denominator else 1 / len(node_ids)
                                       for node, w in zip(node_ids, weights)}
                for node, share in distribution[party].items():
                    self.baseline[party][node] += votes[party] * share
            self.past[county].append(HistoricalPrecinct(polygonal(row.geometry), node_ids, votes, distribution))
        if by_name.keys() != seen:
            raise ValueError(f"Graph precincts missing in VEST: {sorted(by_name.keys() - seen)[:12]}")

    def history(self, nodes):
        return {party: {node: self.baseline[party][node] for node in nodes} for party in PARTIES}

    def prepare_county(self, county, rows, incomplete):
        self.county = county
        self.historical = [precinct for precinct in self.past[county] if precinct.geometry is not None]
        self.history_tree = shapely.STRtree([p.geometry for p in self.historical])
        self.current = {}
        self.block_cache = {}
        self.block_tree = None
        if not rows or (not incomplete and all(len(row["graph_node_ids"].split(";")) == 1
                                               and row["graph_node_ids"] for row in rows)):
            return
        layers = defaultdict(list)
        key_types = set()
        for relative, field, mode in CURRENT.get(county, ()):
            path = self.shapes / relative
            if not path.exists():
                continue
            key_types.add(mode)
            for value, geometry in current_layer(path, field):
                if geometry is None or value is None:
                    continue
                key = gis_key(county, mode, value)
                if key:
                    layers[key].append(geometry)
        if len(key_types) > 1:
            raise ValueError(f"Mixed GIS join key types for {county}")
        if not layers:
            return
        mode = next(iter(key_types))
        by_key = defaultdict(list)
        for row in rows:
            code, name = row["precinct_code"], row["precinct_name"]
            if mode == "name":
                label = name
                if county == "KNOX" and name == "CLAY-MART":
                    label = "CLAY"
                if county == "LICKING":
                    label = LICKING_LABELS.get(name, label)
                key = gis_key(county, mode, label)
            else:
                key = code_key(code)
            by_key[key].append((code, name))
        for key in layers.keys() & by_key.keys():
            if len(by_key[key]) == 1:
                self.current[by_key[key][0]] = shapely.union_all(layers[key])
        print(f"{county}: joined {len(self.current)}/{len(rows)} canvass precincts to GIS", flush=True)
        if self.current and self.blocks and self.county_fips[county] in self.blocks:
            data = self.blocks[self.county_fips[county]]
            self.block_geometry = shapely.make_valid(data.geometry.to_numpy())
            self.block_area = shapely.area(self.block_geometry)
            self.block_vap = data["vap"].to_numpy()
            self.block_geoid = data["GEOID20"].to_numpy()
            self.block_tree = shapely.STRtree(self.block_geometry)

    def current_geometry(self, row):
        return self.current.get((row["precinct_code"], row["precinct_name"]))

    def precinct_blocks(self, index):
        """Intersect populated blocks with one historical precinct."""
        if index not in self.block_cache:
            historical = self.historical[index]
            idx = self.block_tree.query(historical.geometry, predicate="intersects")
            idx = idx[self.block_area[idx] > 0]
            fragments = shapely.intersection(self.block_geometry[idx], historical.geometry)
            positive = shapely.area(fragments) > 0
            idx, fragments = idx[positive], fragments[positive]
            densities = self.block_vap[idx] / self.block_area[idx]
            denominator = float(np.dot(shapely.area(fragments), densities))
            node_ids = [self.block_nodes.get(geoid) for geoid in self.block_geoid[idx]]
            self.block_cache[index] = (fragments, densities, denominator, node_ids)
        return self.block_cache[index]

    def portion_history(self, intersections):
        weights = {party: defaultdict(float) for party in PARTIES}
        split_group = False
        for index, intersection in intersections:
            old = self.historical[index]
            fragments, density, denominator, ids = self.precinct_blocks(index)
            if not denominator:
                continue
            overlap_vap = shapely.area(shapely.intersection(fragments, intersection)) * density
            if len(old.nodes) > 1 and ids and all(node in old.nodes for node in ids):
                # An explicit block-to-node file locates this split precinct.
                # Scale within each node using its own VAP denominator, preserving
                # the VEST party totals and graph's within-group party proportions.
                total_by_node, overlap_by_node = defaultdict(float), defaultdict(float)
                for node, total, partial in zip(ids, shapely.area(fragments) * density, overlap_vap):
                    total_by_node[node] += float(total)
                    overlap_by_node[node] += float(partial)
                fractions = {node: overlap_by_node[node] / total for node, total in total_by_node.items()}
            else:
                if len(old.nodes) > 1 and np.any(overlap_vap > 0):
                    split_group = True
                fractions = dict.fromkeys(old.nodes, float(overlap_vap.sum()) / denominator)

            for party in PARTIES:
                for node, fraction in fractions.items():
                    weights[party][node] += old.votes[party] * old.distribution[party][node] * fraction
        return weights, split_group

    def overlap(self, row, geometry, candidates):
        if geometry is None or not geometry.area:
            return None
        intersections = []
        single_node_areas = defaultdict(list)
        for index in self.history_tree.query(geometry, predicate="intersects"):
            old = self.historical[index]
            intersection = geometry.intersection(old.geometry)
            if intersection.area > 0:
                intersections.append((index, intersection))
                if len(old.nodes) == 1:
                    single_node_areas[old.nodes[0]].append(intersection)
        if not intersections:
            return None
        shares = {node: shapely.union_all(areas).area / geometry.area
                  for node, areas in single_node_areas.items()}
        if shares:
            node = max(shares, key=lambda candidate: (shares[candidate], -candidate))
            share = shares[node]
            known_merge = row["graph_match_status"] == "merged_precinct" and len(candidates) > 1
            if share >= SNAP_SHARE and not known_merge:
                return {party: {node: 1} for party in PARTIES}, "area_tolerance_match", f"{share:.8f}"

        coverage = shapely.union_all([piece for _, piece in intersections]).area / geometry.area
        if self.block_tree is None or coverage < SNAP_SHARE:
            return None
        weights, shared = self.portion_history(intersections)
        if not all(sum(weight.values()) > 0 for weight in weights.values()):
            return None
        method = "block_vap_with_shared_vest_precinct" if shared else "block_vap"
        return weights, method, f"{max(shares.values()):.8f}" if shares else ""

    def remaining_history(self, nodes, located):
        if self.block_tree is not None and located:
            covered = shapely.union_all(located)
            remainder = [(idx, precinct.geometry.difference(covered))
                         for idx, precinct in enumerate(self.historical)]
            weights, _ = self.portion_history([(idx, geometry) for idx, geometry in remainder
                                               if not geometry.is_empty])
            if all(sum(w.values()) > 0 for w in weights.values()):
                return weights, "unlocated_precincts_uncovered_vest_2020"
        return self.history(nodes), "unlocated_precincts_county_vest_2020"

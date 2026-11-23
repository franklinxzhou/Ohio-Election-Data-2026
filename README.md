# Ohio Precinct-Level Election Results Estimate: 2026 General Election

This repository provides precinct-level estimates of the results of the November 3, 2026, general election in Ohio from [Duke Quantifying Gerrymandering Group](https://sites.duke.edu/quantifyinggerrymandering/). The underlying election canvass data were collected as of November 21, 2026.

## Data Sources

We prioritize election results according to the following hierarchy of sources:

1. **Precinct-level official canvass (preferred):** Certified election results published by the respective county Boards of Elections (BoEs).

2. **Precinct-level unofficial canvass:** Unofficial election results, typically published by county BoEs shortly after Election Day. This category includes the following counties: Butler, Clermont, Cuyahoga, Fulton, Highland, Medina, Mercer, Montgomery, Pickaway, Portage, Putnam, Scioto, and Stark.

3. **County-level official or unofficial canvass:** For counties where precinct-level results are unavailable, we use county-level returns to construct precinct-level estimates. The estimation methodology will be documented in a forthcoming section. This category includes Columbiana, Gallia, Hancock, Jackson, Lucas, Mahoning, Muskingum, Trumbull, and Williams.

The resulting dataset therefore combines certified precinct-level results, unofficial precinct-level results, and precinct-level estimates derived from county-level returns. These distinctions should be taken into account when interpreting the data.

## Mapping 2026 Precincts to 2020 Precincts

Our Ohio precinct adjacency graph was constructed using the [2020 precinct-level election data published by the Voting and Election Science Team (VEST)](https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/K7760H).

Between the 2020 and 2026 general elections, numerous Ohio counties modified their precinct boundaries, creating inconsistencies between the precinct geographies underlying our adjacency graph and those used to report the 2026 election results.

To reconcile these differences, we first attempted to match precincts using their names, accounting for common abbreviations, naming conventions, and minor variations in spelling. We then consulted county BoE meeting minutes, precinct boundary shapefiles, and other publicly available documentation to identify precinct consolidations, subdivisions, and boundary adjustments.

Our objective is to align the 2026 election returns with the 2020 precinct geography used in our redistricting analysis as accurately as the available records permit.

### Reproduce the statewide recast

Run `output/recast_remaining.py` from the repository root with Python 3.11 or newer and `geopandas`, `numpy`, `pyogrio`, `pyproj`, and `shapely>=2.1`. The script takes the county canvass CSVs, `OH_pct20.json`, the clean recast, and the VEST 2020 archive supplied for this project.

Download the [Ohio 2020 Census block shapefile](https://www2.census.gov/geo/tiger/TIGER2020PL/STATE/39_OHIO/39/tl_2020_39_tabblock20.zip) and the [Ohio P.L. 94-171 redistricting file](https://www2.census.gov/programs-surveys/decennial/2020/data/01-Redistricting_File--PL_94-171/Ohio/oh2020.pl.zip). Pass the paths to the ZIPs as follows.

```sh
python output/recast_remaining.py \
  --blocks /path/to/tl_2020_39_tabblock20.zip \
  --pl /path/to/oh2020.pl.zip
```

For unresolved precincts with mapped 2026 boundaries, the script checks whether one graph node covers at least 98% of the precinct. Documented merges spanning multiple nodes proceed to allocation. Other mapped precincts use VEST party votes weighted by the voting-age population of the intersecting Census blocks. For partial blocks, voting-age population is prorated by polygon area. The precinct geometries and population overlays use EPSG:5070.

For an unlocated precinct, the script uses VEST vote shares across its candidate nodes when available. It pools precincts with no candidate nodes and uses the uncovered part of the county where mapped precincts establish coverage. Countywide totals use VEST party shares across all nodes in the county. Where several graph nodes share a VEST precinct, the script uses the graph's historical party counts for relative shares within that group. A verified `block_geoid,graph_node_id` CSV supplied via `--block-nodes` can locate those pieces for block-weighted overlaps. Older boundary layers are retained as references.

The script writes `output/recast_2026_to_2020.csv` with one row per graph node and `output/recast_2026_to_2020_allocations.csv` with the contributing canvass units, allocation method, weights, and integer vote counts. Largest-remainder rounding preserves every reported county total by race and party.

## Research Purpose and Limitations

The primary objective of this dataset is **not to provide a definitive reconstruction of the 2026 election results at the precinct level**. Rather, it is to support a sensitivity analysis of our ensemble-based redistricting study under an unusually Democratic-favorable electoral environment.

Specifically, we seek to investigate two questions:

1. **Robustness of ensemble-based analysis:** Do our conclusions about the partisan characteristics of Ohio's congressional redistricting plans remain robust under a substantially different electoral environment, particularly one characterized by a Democratic wave?

2. **Electoral vulnerability under gerrymandering:** To what extent can a heavily gerrymandered congressional plan attenuate Democratic electoral gains, potentially making the translation of statewide electoral success into congressional representation unusually fragile?

Given the incomplete availability of certified precinct-level returns, the estimates should be understood as an exploratory research dataset rather than an authoritative record of the 2026 election.

Our full analysis of Ohio's three proposed/enacted congressional districting plans will be published soon. Please check back for details!

## AI Use Disclosure

In the preparation of this dataset, the author used ChatGPT (GPT-6.2 Sol, OpenAI) as an AI-assisted programming and research support tool. Its use included:

1. Data extraction and processing: Assisting in the development of parsers for county-level election canvass documents and adapting these parsers to the varying structures and formatting conventions of PDF files published by county BoEs.
2. Source documentation: Assisting in organizing and cross-referencing publicly available records of precinct boundary changes, including county BoE meeting minutes and precinct boundary documentation.
3. Data validation: Assisting in comparing aggregated precinct-level election returns against independently reported county-level totals.

AI-generated code, suggestions, and validation procedures were used as research aids rather than independent sources of data or authoritative verification. *The author retains full responsibility for the implementation of the methods, the accuracy and integrity of the resulting dataset, as well as any errors or omissions.*

---
name: sdi
description: Find and analyze Madrid open data to answer location / plot-feasibility questions about a place, by progressively discovering and querying a federation of cloud-native spatial data catalogs (Apache Iceberg + STAC + COG on object storage, queried with DuckDB/GDAL). Use this WHENEVER the user asks something geographic about a specific location in Madrid — e.g. "¿puedo construir aquí?", "is this plot buildable?", "what protections / hazards / constraints affect this parcel?", "what does the data say about building / opening a business at this address?". Trigger on plot feasibility, siting, land-use, protected-area, natural-hazard, or services-at-a-location questions.
---

# SDI — find & analyze Madrid open data by progressive discovery

You **find and analyze spatial data** to answer a located question. You do **not** know the
datasets in advance — you discover them progressively: registry → catalog → dataset → query,
reading metadata at each step. Everything specific (endpoints, schemas, how to query each
dataset) lives **in the catalogs and their metadata**; this skill stays generic so it works as
the federation grows.

*(Part of the **Portolan** project — open, agent-ready spatial data infrastructure: open files
on object storage, queried by an open engine. No GIS server, no portal, no data copies.)*

## The progressive-discovery loop — narrate it out loud
1. **Registry → pick a catalog.** [`catalogs.md`](catalogs.md) lists the Madrid catalogs: each is
   an independent publisher with an Iceberg endpoint, a CRS, a WGS84 extent, and a description of
   what it holds. Choose the catalog(s) whose description fits the question. For a *located*
   question pre-filter by extent (a sierra plot → the Comunidad regional catalog; a plot inside
   Madrid municipality → also the city catalogs).
2. **Catalog → browse its datasets.** Attach the catalog and read its **STAC index**
   `catalog.datasets`. Each row is a dataset with metadata in `properties`/`assets`. Filter to
   what's relevant — don't assume names.
3. **Dataset → understand it.** Read `properties` (theme, title, crs, semantics) and `assets`:
   `iceberg:table_id` (`v3.<name>` vector / `tab.<name>` tabular), the remote GeoParquet href, or
   the COG href under `data/cog/`. Note the CRS (comunidad = EPSG:25830 metric; city open-data =
   EPSG:4326).
4. **Query — write it yourself.** Compose SQL from the schema. The decisive checks for "can I
   build here?" are **point-in-polygon** and **nearest distance**; rasters are sampled with GDAL.
   See the patterns below.
5. **Synthesize.** Answer in plain language with a **verdict**, and a panel where **every figure
   shows its catalog · dataset · the query** that produced it. Build/replay the HTML artifact
   (`webapp/`).

## Connecting & querying (the patterns that matter here)
Use the DuckDB **CLI**: `duckdb -unsigned -json -c "<sql>"`. Prelude:
```sql
INSTALL httpfs;LOAD httpfs; INSTALL spatial;LOAD spatial; INSTALL iceberg;LOAD iceberg;
SET geometry_always_xy=true;
ATTACH 'cm' (TYPE iceberg, ENDPOINT '<endpoint from catalogs.md>', AUTHORIZATION_TYPE 'none');
SELECT * FROM cm.catalog.datasets WHERE properties ILIKE '%<topic>%';
```
The point comes in as lon/lat (WGS84). For **comunidad-madrid** (EPSG:25830) transform it once:
`PT = ST_Transform(ST_Point(lon,lat),'EPSG:4326','EPSG:25830')`. Then:

- **Land classification (is it buildable?)** — point-in-polygon on the planning layer:
  `SELECT DS_CLASIF_GEN FROM cm.v3.vpla_v_clasificacion_ref_23 WHERE ST_Contains(geom, PT)` →
  *Suelo Urbano / Urbanizable / No Urbanizable*. (Read **No Urbanizable before Urbanizable** — substring trap.)
- **Protected areas (the usual blocker)** — `ST_Contains(geom, PT)` on `idem_ma_enp`,
  `idem_ma_red_natura_lic_zec`, `idem_ma_red_natura_zepa`, `idem_ma_montes_up`,
  `idem_ma_montes_preservados`; vías pecuarias with `ST_DWithin(geom, PT, 50)`. Return the **name**.
- **Natural hazards** — the `peligrosid_*` vectors carry a **`PELIGROSID` level 0–5**; report the
  level, warn only at ≥4. (`peligrosid_2_1` avenidas, `4_1` sismos, `5_1` ladera, …) Raster risk:
  sample the COG with `gdallocationinfo -valonly -wgs84 /vsicurl/<endpoint>/data/cog/<id>.tif <lon> <lat>`
  (`zonasriesgo_peligrosid_3_1` fire, `zonasriesgo_riesgo_*`).
- **Geology / soil** — `idem_ma_litologia_50m` (DS_DESCRIPCION, DS_PERMEABILIDAD), `idem_ma_clasif_suelos_98`.
- **Nearest services (EIEL)** — `SELECT round(min(ST_Distance(geom, PT))) FROM cm.v3.idem_eiel_*`
  (carretera, cent_sanitario, cent_ensenanza, captacion, depuradora). Distances are metres (25830).
- **City federation** — if the plot is in Madrid municipality, also query **madrid-opendata**
  (EPSG:4326, geom col `geometry`): parks (`principales_parques_y_jardines_municipales`),
  air-quality & noise stations. For metric distance transform both sides to 25830.
- **Amenities / "lo que hay alrededor" (colegios, comercio, salud, transporte)** — the official catalogs are
  patchy here (EIEL only small munis; city portal only Madrid). Use **Overture** `places` as a **remote
  GeoParquet on its own S3** (no copy): bbox-prune + filter `categories.primary`, optionally `ST_Within` a
  municipio/barrio polygon. This is the uniform, comparable-everywhere amenity layer — ideal for comparing
  locations. See the `query_hint` in `catalogs.md`.

`tools/site_check.py` runs exactly this screen end-to-end and writes a sourced report.

## Honest framing — do NOT regress
- **Always an orientative spatial screening, not a permit decision.** Every number keeps its catalog · dataset · query.
- **Land classification** is the *regional refundido* — **Madrid capital is governed by its own PGOUM**;
  for a plot in Madrid municipality, say so (the regional layer won't classify it), don't report "sin clasificación" as if buildable.
- **Hazards:** report the mapped 0–5 level; "alta/muy alta" (≥4) is the warning. Don't infer risk from mere coverage.
- **Protected areas** don't forbid building per se but subject it to the park's PORN/PRUG and Natura 2000 evaluation — say that.
- Slope/flood-line from a DEM is a *fallback*; prefer the mapped hazard layers.

## Web demo
`webapp/` is a **precomputed snapshot** of one run of this flow (replays the Manzanares el Real
"¿puedo construir aquí?" scenario from committed `data/*.json`). In a live session, do the
discovery yourself — that's the point. Rebuild a scenario with `tools/build_scenario.py`.

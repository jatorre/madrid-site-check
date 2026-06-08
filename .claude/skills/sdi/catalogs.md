# Catalog registry — the Madrid open-data infrastructures you can reach

The **directory** the `sdi` skill reads first: *which catalogs exist and what each holds*, so you
can pick one. You don't get dataset-level detail here — once you choose a catalog, **attach it and
read its own STAC index** (`catalog.datasets`); each dataset carries its own metadata (theme,
semantics, CRS, schema) from which **you compose your own query**. Registry → catalog → dataset →
query. Adding a source = a new endpoint + an entry here; the skill doesn't change.

All three are **Apache Iceberg + STAC** catalogs on Google Cloud Storage (region `europe-southwest1`,
Madrid), **public & anonymous**, attached with DuckDB. Each publishes its own `catalog.datasets`
index (stac-geoparquet) listing **only what is actually materialized**. Shapes: an **Iceberg table**
(`v3.<name>` vectors with native geometry, `tab.<name>` non-spatial), a **remote GeoParquet**
(`data/parquet/<id>.parquet`), or a **Cloud-Optimized GeoTIFF** (`data/cog/<id>.tif`, sampled with GDAL).

```sql
ATTACH '<alias>' (TYPE iceberg, ENDPOINT '<endpoint>', AUTHORIZATION_TYPE 'none');
SELECT id, json_extract_string(properties,'$.theme') theme,
       json_extract_string(properties,'$.title') title,
       json_extract_string(assets,'$.data.href')  data
FROM <alias>.catalog.datasets WHERE properties ILIKE '%<topic>%';
```

## The catalogs

### 🟥 Comunidad de Madrid — IDEM  (the regional SDI; the decisive layers)
The Infraestructura de Datos Espaciales regional: planning classification & ordenanza, protected
areas (ENP, Red Natura 2000 LIC/ZEC + ZEPA, montes de U.P. y preservados, vías pecuarias), the full
**natural-hazard archive** (48 `peligrosid_*` vector layers + 98 risk/vulnerability **COG** rasters:
flood, fire, seismic, landslide, subsidence…), geology/lithology, soils, hydrography, elevation
(contours), and the **EIEL** municipal-infrastructure inventory (water, sewage, roads, schools, health).
Also 2,232 tabular statistics. **CRS: EPSG:25830 (metric — distances in metres).** ~2,578 datasets.
- **Attach as** `cm` · **endpoint** `https://storage.googleapis.com/carto-portolan-madrid/comunidad-madrid`
- Source: datos.comunidad.madrid · geoidem (WFS/WCS). Extent: Comunidad de Madrid.

### 🐻 Ayuntamiento de Madrid — datos abiertos
The City of Madrid open-data portal as a catalog: ~108 geospatial layers (parks & gardens, air-quality
& noise monitoring stations, SER regulated parking, ZBE low-emission zones, facilities) + ~419 tabular.
Use it to **enrich a plot inside Madrid municipality** (the regional planning layer doesn't cover the
capital — Madrid is governed by its **PGOUM**). **CRS: EPSG:4326 (geom column `geometry`).** ~527 materialized.
- **Attach as** `od` · **endpoint** `https://storage.googleapis.com/carto-portolan-madrid/madrid-opendata`
- Source: datos.madrid.es. Extent: municipio de Madrid.

### 🗺️ Ayuntamiento de Madrid — Geoportal / IDEAM
The City's geoportal/IDEAM cartography & imagery: base topography, street directory (callejero),
mobiliario urbano, túneles, MDT elevation service. Mostly base/infrastructure — supporting, not
decisive for buildability. **CRS: EPSG:25830.** ~80 materialized (of ~1,006 catalogued).
- **Attach as** `city` · **endpoint** `https://storage.googleapis.com/carto-portolan-madrid/madrid-city`
- Source: geoportal.madrid.es / IDEAM. Extent: municipio de Madrid.

### 🌍 Overture Maps (global) — POIs/amenities, **remote GeoParquet (no materialization)**
What the official catalogs *don't* give uniformly: **amenities by location**, comparable everywhere. (Verified
gap: the regional EIEL only surveys small municipalities — 636 schools, big cities absent; the city portal
covers only Madrid capital.) Overture already publishes planet-scale **cloud-native GeoParquet on its own
public S3**, so we **register it remote and query it in place** — nothing is copied into our bucket, same as
the Helsinki demo. `places` = points of interest with `categories.primary` (school, supermarket, pharmacy,
hospital, restaurant, park, bus_stop…), `names`, `geometry`, and a `bbox` struct for pruning. **CRS: EPSG:4326.**
- **No `ATTACH`** — read the GeoParquet directly. Endpoint (pin the latest release; check `aws s3 ls --no-sign-request s3://overturemaps-us-west-2/release/`):
  `s3://overturemaps-us-west-2/release/2026-05-20.0/theme=places/type=place/*.parquet`
- **`query_hint` (genuinely tricky access — use it):**
  ```sql
  INSTALL httpfs;LOAD httpfs; INSTALL spatial;LOAD spatial;
  CREATE SECRET ov (TYPE s3, PROVIDER config, REGION 'us-west-2');  -- empty creds = anonymous public read
  SELECT p.categories.primary cat, count(*) n
  FROM read_parquet('s3://overturemaps-us-west-2/release/<REL>/theme=places/type=place/*.parquet') p
  WHERE p.bbox.xmin BETWEEN <minx> AND <maxx> AND p.bbox.ymin BETWEEN <miny> AND <maxy>  -- ALWAYS bbox-prune first
    AND p.categories.primary IN ('school','supermarket','pharmacy','hospital','restaurant','park')
  GROUP BY 1;
  -- precise count per area: join to a polygon (e.g. comunidad-madrid municipio, transformed to 4326):
  --   ... AND ST_Within(p.geometry, <muni_polygon_4326>)
  ```
  The `bbox` prune (on row-group stats) is what makes it fast (~10 s region-wide). Without it, it scans the planet.

## Adding a source (the direction)
Stand up an Iceberg endpoint, publish a STAC `catalog.datasets` index so datasets are discoverable
(theme + semantics + CRS + schema), and add an entry here. No skill code changes — the agent reads
this file, attaches the catalog, searches the index, and queries. That's the Portolan idea: SDIs as
open, self-describing, agent-usable infrastructure.

---

## v3 + "informe de mi dirección" update (verified live)

**Catastro de España — `catastro-es`** · base `https://storage.googleapis.com/catastro-es-portolan`
- `v3/{edificios,parcelas,direcciones}/data/provincia=NN.parquet` (Hive by provincia, EPSG:4326, geom col `geom`, flat bbox cols `xmin/ymin/xmax/ymax`). Madrid province = `28`.
- Also **PMTiles** vector tiles at `tiles/{tema}.pmtiles` (range-served) — use as a map base via `pmtiles://`.
- Building/parcel at a point: `WHERE xmin BETWEEN lon±d AND ... ORDER BY ST_Distance(...) LIMIT 1` → `reference, current_use, year_built, num_dwellings`, parcela `area_m2`.

**CARTO LDS (geocoding + isochrones)** — via `carto sql query carto_dw "<sql>" --json`. The managed AT isn't exposed on the SQL API, so use the **BYOT scalar functions** with an API Access Token (`carto credentials create token --connection carto_dw --source "SELECT 1" --apis sql,lds`; store token in gitignored `.lds.env`, base `https://gcp-us-east1.api.carto.com`):
```sql
`carto-un`.carto.GEOCODE(base, token, 'Calle de Alcalá 100, Madrid', 'ES', NULL)        -- → GEOGRAPHY (country = ISO2!)
`carto-un`.carto.ISOLINE(base, token, <point>, 'walk', 900, 'time', NULL)               -- → polygon (15 min)
```

**Gotchas confirmed:**
- DuckDB secrets must be **scoped** when mixing GCS + Overture: `SCOPE 's3://'` (GCS) vs `SCOPE 's3://overturemaps-us-west-2'` (Overture), else GCS secret hijacks the Overture read (404).
- Overture `geometry` is already a `GEOMETRY` type (not WKB) — use it directly, **not** `ST_GeomFromWKB`.
- madrid-opendata vector geom col is `geom`; attributes often arrive as a GeoRSS `content` blob (`CAST(content AS VARCHAR)`), not structured fields.
- EIEL service datasets carry a `_23` suffix (`idem_eiel_cent_sanitario_23`, `idem_eiel_cent_ensenanza_23`, `idem_eiel_parque_23`).
- Public GCS buckets had **no CORS** → set `GET/HEAD, origin *` so browser/PMTiles work cross-origin.

**Honest coverage (state it in the answer):** air-quality history is materialized only for **2005** and excludes Madrid capital → no "¿respiro mejor que hace 20 años?"; no clean 1985→2025 municipal series; arbolado + concejales-desde-1979 not in the current materialized city set. Show these as gaps — where open data should be opened/maintained.

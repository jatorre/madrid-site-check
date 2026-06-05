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

## Adding a source (the direction)
Stand up an Iceberg endpoint, publish a STAC `catalog.datasets` index so datasets are discoverable
(theme + semantics + CRS + schema), and add an entry here. No skill code changes — the agent reads
this file, attaches the catalog, searches the index, and queries. That's the Portolan idea: SDIs as
open, self-describing, agent-usable infrastructure.

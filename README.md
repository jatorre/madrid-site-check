# ¿Puedo construir aquí? — Madrid plot due-diligence from open data

A **useful, get-it-done** tool, not an article: give it a plot (address/coords) and it returns a **sourced
"plot report"** — land classification, protected areas, natural hazards, geology/soil, and nearest public
services — answered **live and anonymously** from Madrid's open-data **Portolan catalogs**. Every line carries
the *catalog · dataset* it came from, so the citizen, developer or technician can verify and re-run it.

It's the citizen/developer counterpart of the OGC Connect Helsinki site-screening: same federated, provenance-first
pattern, applied to a real question — *"is this plot buildable, and what do I have to watch out for?"*

## Federated catalogs (all public, anonymous, queried in place)
| Catalog | Endpoint | Role here |
|---|---|---|
| **comunidad-madrid** | `…/carto-portolan-madrid/comunidad-madrid` | the decisive regional layers: planning classification & ordenanza, protected areas (ENP, Natura 2000, montes, vías pecuarias), natural hazards (flood/fire/seismic/landslide/subsidence — vector + raster COGs), geology/soil, EIEL services. EPSG:25830. |
| **madrid-opendata** | `…/carto-portolan-madrid/madrid-opendata` | city layers, federated when the plot is **in Madrid municipality** (parks, air-quality & noise stations). EPSG:4326. |
| **madrid-city** | `…/carto-portolan-madrid/madrid-city` | geoportal/IDEAM cartography (available; mostly base/mobiliario — not decisive for buildability). |

Base = `https://storage.googleapis.com/carto-portolan-madrid`.

## Run
```bash
python3 tools/site_check.py <lat> <lon> "label"   # one plot
python3 tools/site_check.py --samples             # the 4 demo plots below
```
DuckDB for vectors (point-in-polygon / nearest, native CRS per catalog), GDAL `gdallocationinfo` for the hazard
COGs. No server, no downloads, no credentials.

## Demo plots (in `reports/`) — a clean four-way contrast
| Plot | Verdict |
|---|---|
| **Parla** (sur metropolitano) | ✅ Suelo URBANO — edificable, sin condicionantes |
| **Manzanares el Real** | ✅ Suelo URBANO **pero** dentro del Parque Regional + Natura 2000 |
| **Cercedilla** (sierra) | ⛔ Suelo NO URBANIZABLE protegido — Parque Nacional + Natura 2000 + Monte de U.P. |
| **Madrid — Malasaña** | ℹ️ rige el PGOUM municipal (clasificación regional no cubre la capital); federa capas de ciudad (parque 307 m, estaciones de aire/ruido) |

## What it checks (each cites its source)
- **Planeamiento:** municipio · clasificación del suelo (urbano / urbanizable / no urbanizable) · ordenanza y uso predominante.
- **Espacios protegidos:** ENP · Natura 2000 (LIC/ZEC, ZEPA) · Montes de U.P. y preservados · vías pecuarias (≤50 m) · humedales.
- **Riesgos naturales:** peligrosidad por avenidas, torrencialidad, rotura de presas, sismos, movimientos de ladera, subsidencia, suelos expansivos (nivel 0–5) + rásters de riesgo (incendio, sísmico, ladera, avenidas).
- **Geología y suelo:** litología y permeabilidad · tipo de suelo (Soil Taxonomy).
- **Servicios (EIEL):** distancia a captación de agua, depuradora, carretera, centro de enseñanza, centro sanitario.
- **Ciudad de Madrid (federado):** parque/jardín municipal, estaciones de calidad del aire y de ruido.

## Honesty / limits
- **Orientativo — no sustituye la consulta urbanística oficial** del Ayuntamiento / Comunidad.
- Planning (`vpla_*`) coverage is the regional *refundido*; **Madrid capital is governed by its own PGOUM** (flagged, not classified here).
- Hazard levels use the source's 0–5 scheme (0 = sin dato). Slope is not yet computed (the landslide hazard layer is the proxy; a DEM would sharpen it).

## Layout
```
tools/site_check.py   the screener (layer registry + point-query engine + report generator)
reports/*.md|json     generated plot reports (each with full provenance)
```

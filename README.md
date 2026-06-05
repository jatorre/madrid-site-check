# ¿Puedo construir aquí? — ask Madrid's open data, in a conversation

A **Helsinki-style AI-conversation demo**: ask a plain-language question about a plot in Madrid and an
agent **progressively discovers the open-data catalogs**, queries them **live**, and answers with a
verdict — *every figure carrying its catalog · dataset · query*. The citizen/developer use case:
*"I'm thinking of buying this plot to build a house — can I, and what do I have to watch out for?"*

![demo](webapp/preview.png)

**Live demo:** `webapp/` → `index.html` (the federation) + `app.html` (the conversation + map).
Open `index.html` or serve the folder: `python3 -m http.server -d webapp 8799`.

## How it works
- **`.claude/skills/sdi/`** — the live agent loop (`SKILL.md`) + the catalog registry (`catalogs.md`):
  *registry → catalog → dataset → query → assess*. In a live session the agent does the discovery itself.
- **`webapp/`** — a **precomputed snapshot** of one run (the Manzanares el Real scenario), replayed from
  `data/scenario.json`, in the same conversation+map UI as the OGC Connect Helsinki demo. Every tool card
  shows the **real SQL and its real result**.
- **`tools/site_check.py`** — the engine: address/coords → the full sourced screen (also runs standalone).
- **`tools/build_scenario.py`** — rebuilds `webapp/data/scenario.json` by running the real queries.

## The federated catalogs (all public, anonymous, cloud-native — queried in place)
| Catalog | Endpoint | Role |
|---|---|---|
| 🟥 **comunidad-madrid** (IDEM) | `…/carto-portolan-madrid/comunidad-madrid` | the decisive layers: planning classification & ordenanza, protected areas (ENP, Natura 2000, montes, vías pecuarias), natural hazards (vector levels + COG rasters), geology/soil, EIEL services. EPSG:25830 |
| 🐻 **madrid-opendata** | `…/carto-portolan-madrid/madrid-opendata` | city layers when the plot is in Madrid municipality (parks, air/noise stations). EPSG:4326 |
| 🗺️ **madrid-city** (Geoportal/IDEAM) | `…/carto-portolan-madrid/madrid-city` | base cartography (supporting). EPSG:25830 |

Base = `https://storage.googleapis.com/carto-portolan-madrid`. Built as **Portolan** catalogs
(Apache Iceberg + STAC + COG) in another session; this repo just *uses* them.

## The demo scenario (Manzanares el Real) — real data
**✅ Suelo Urbano (edificable) — pero dentro del Parque Regional de la Cuenca Alta del Manzanares + Natura 2000 (LIC).**
Riesgos muy bajos; carretera a 31 m, centro sanitario a 424 m. → *Edificable, sujeto a la normativa del parque
(PORN/PRUG) y a evaluación de Red Natura.* Other plots run via the CLI: `reports/` (Parla ✅, Cercedilla ⛔, Madrid ℹ️ PGOUM).

## Run the screen on any plot
```bash
python3 tools/site_check.py <lat> <lon> "etiqueta"     # one plot → sourced report (reports/)
python3 tools/site_check.py --samples                   # the demo plots
python3 tools/build_scenario.py                         # rebuild the webapp conversation
```

## Honest framing
**Orientativo — no sustituye la consulta urbanística oficial.** Land classification is the regional
*refundido* (Madrid capital is governed by its **PGOUM**, flagged not classified). Hazards report the
source's 0–5 level (warn at ≥4). Protected areas don't forbid building but subject it to the park's rules.
Descriptive, not a permit decision. Every number keeps its catalog · dataset · query.

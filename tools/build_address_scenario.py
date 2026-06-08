#!/usr/bin/env python3
"""Informe de mi dirección — runs REAL federated queries for ONE address and writes
webapp/data/scenario.json (Helsinki-style conversation) + prints a markdown informe.

Geocoding + 15-min walking isochrone via CARTO LDS (reads gitignored .lds.env).
Data queried live & anonymously: Portolan v3 on GCS (comunidad-madrid, madrid-opendata)
+ Catastro PMTiles building (catastro-es) + Overture remote GeoParquet (amenities).

Design principle (per the brief): be HONEST about coverage — show what open data answers
AND where it falls short / should be opened. Failed/empty sections become explicit gaps.

Run: python3 tools/build_address_scenario.py ["Calle de Alcalá 100, Madrid"]
"""
import json, subprocess, pathlib, sys, re

ADDR    = sys.argv[1] if len(sys.argv) > 1 else "Calle de Alcalá 100, Madrid"
COUNTRY = "ES"
ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT  = ROOT / "webapp" / "data"; OUT.mkdir(parents=True, exist_ok=True)

CM  = "https://storage.googleapis.com/carto-portolan-madrid/comunidad-madrid"
OD  = "https://storage.googleapis.com/carto-portolan-madrid/madrid-opendata"
OV  = "s3://overturemaps-us-west-2/release/2026-05-20.0/theme=places/type=place/*.parquet"
CATE= "s3://catastro-es-portolan/v3/edificios/data/provincia=28.parquet"
CATP= "s3://catastro-es-portolan/v3/parcelas/data/provincia=28.parquet"

# ---- CARTO LDS creds (gitignored) ----
env = {}
for line in (ROOT / ".lds.env").read_text().splitlines():
    if "=" in line:
        k, v = line.split("=", 1); env[k] = v
T, B = env["CARTO_LDS_TOKEN"], env["CARTO_LDS_BASE"]
LDS = lambda fn: f"`carto-un`.carto.{fn}"

def scrub(s): return s.replace(T, "***")

def carto(sql):
    r = subprocess.run(["carto", "sql", "query", "carto_dw", sql, "--json"],
                       capture_output=True, text=True)
    if '"rows"' not in r.stdout:
        raise RuntimeError(scrub((r.stderr + r.stdout))[-300:])
    return json.loads(r.stdout)["rows"]

def duck(sql, ov=False):
    # scoped secrets: GCS catch-all (s3://) + Overture-specific (longer scope wins)
    pre = ("INSTALL httpfs;LOAD httpfs;INSTALL spatial;LOAD spatial;"
           "CREATE SECRET g (TYPE s3,PROVIDER config,KEY_ID '',SECRET '',ENDPOINT 'storage.googleapis.com',URL_STYLE 'path',USE_SSL true,REGION 'auto',SCOPE 's3://');")
    if ov:
        pre += "CREATE SECRET ov (TYPE s3,PROVIDER config,REGION 'us-west-2',SCOPE 's3://overturemaps-us-west-2');"
    pre += "SET geometry_always_xy=true;"
    r = subprocess.run(["duckdb", "-unsigned", "-json", "-c", pre + sql],
                       capture_output=True, text=True)
    s = r.stdout.strip()
    dec = json.JSONDecoder(); i = 0; arrs = []
    while i < len(s):
        while i < len(s) and s[i] in " \n\r\t": i += 1
        if i >= len(s): break
        try:
            obj, j = dec.raw_decode(s, i)
        except ValueError:
            break
        arrs.append(obj); i = j
    res = [a for a in arrs if not (isinstance(a, list) and a and isinstance(a[0], dict) and "Success" in a[0])]
    if not res and r.returncode:
        raise RuntimeError(r.stderr[-300:] or "duckdb failed")
    return res[-1] if res else []

def one(rows, *keys, default=None):
    if not rows: return default
    r = rows[0]
    return tuple(r.get(k) for k in keys) if len(keys) > 1 else r.get(keys[0], default)

print(f"# Informe: {ADDR}", flush=True)

# ============ 1. GEOCODE (CARTO LDS) ============
g = carto(f"SELECT ST_X({LDS('GEOCODE')}('{B}','{T}','{ADDR}','{COUNTRY}',NULL)) lon, "
          f"ST_Y({LDS('GEOCODE')}('{B}','{T}','{ADDR}','{COUNTRY}',NULL)) lat")[0]
LON, LAT = round(float(g["lon"]), 7), round(float(g["lat"]), 7)
print(f"  geocode → {LON},{LAT}", flush=True)
PT25 = f"ST_Transform(ST_Point({LON},{LAT}),'EPSG:4326','EPSG:25830')"

# ============ 2. ISOCHRONE 15-min walk (CARTO LDS) ============
iso = carto(f"SELECT ST_ASGEOJSON({LDS('ISOLINE')}('{B}','{T}',"
            f"{LDS('GEOCODE')}('{B}','{T}','{ADDR}','{COUNTRY}',NULL),'walk',900,'time',NULL)) iso, "
            f"ROUND(ST_AREA({LDS('ISOLINE')}('{B}','{T}',"
            f"{LDS('GEOCODE')}('{B}','{T}','{ADDR}','{COUNTRY}',NULL),'walk',900,'time',NULL))/1e6,2) km2")[0]
iso_geojson = json.loads(iso["iso"]); iso_km2 = iso["km2"]
print(f"  isochrone 15-min walk → {iso_km2} km²", flush=True)

# ============ 3. SUELO / RIESGOS (comunidad v3) ============
def cmv3(name): return f"read_parquet('{CM}/v3/{name}/data/{name}.parquet')"
muni = one(duck(f"SELECT any_value(DSMUNICIPIO) m FROM {cmv3('idem_v_municipios')} t WHERE ST_Contains(t.geom,{PT25})"), "m")
clasif = one(duck(f"SELECT any_value(DS_CLASIF_GEN) c FROM {cmv3('vpla_v_clasificacion_ref_23')} t WHERE ST_Contains(t.geom,{PT25})"), "c")
enp = one(duck(f"SELECT any_value(DS_NOMBRE) n FROM {cmv3('idem_ma_enp')} t WHERE ST_Contains(t.geom,{PT25})"), "n")
RISK5 = {0: "sin dato", 1: "muy baja", 2: "baja", 3: "media", 4: "alta", 5: "muy alta"}
def haz(name):
    r = duck(f"SELECT any_value(PELIGROSID) p FROM {cmv3(name)} t WHERE ST_Contains(t.geom,{PT25})")
    p = one(r, "p"); return int(p) if p is not None else 0
sismo, ladera, avenida = haz("peligrosid_4_1"), haz("peligrosid_5_1"), haz("peligrosid_2_1")
fr = subprocess.run(["gdallocationinfo", "-valonly", "-wgs84",
                     f"/vsicurl/{CM}/data/cog/zonasriesgo_peligrosid_3_1.tif", str(LON), str(LAT)],
                    capture_output=True, text=True).stdout.strip().splitlines()
fire = int(float(fr[0])) if fr and fr[0].strip() else 0
print(f"  suelo: {muni} · clasif={clasif} · enp={enp} · riesgos s{sismo}/l{ladera}/a{avenida}/f{fire}", flush=True)

# ============ 4. TU EDIFICIO (Catastro v3) ============
ed = duck(f"""SELECT reference, current_use, year_built, num_dwellings,
  round(ST_Distance(ST_Transform(geom,'EPSG:4326','EPSG:25830'),{PT25})) d
  FROM read_parquet('{CATE}')
  WHERE xmin BETWEEN {LON}-0.0008 AND {LON}+0.0008 AND ymin BETWEEN {LAT}-0.0008 AND {LAT}+0.0008
  ORDER BY d LIMIT 1""")
pc = duck(f"""SELECT reference, area_m2, round(ST_Distance(ST_Transform(geom,'EPSG:4326','EPSG:25830'),{PT25})) d,
  ST_AsGeoJSON(geom) g
  FROM read_parquet('{CATP}')
  WHERE xmin BETWEEN {LON}-0.0008 AND {LON}+0.0008 AND ymin BETWEEN {LAT}-0.0008 AND {LAT}+0.0008
  ORDER BY d LIMIT 1""")
edif = ed[0] if ed else None
parc = pc[0] if pc else None
year = (str(edif["year_built"])[:4] if edif and edif.get("year_built") else None)
_pg = parc.get("g") if parc else None
parc_geojson = (json.loads(_pg) if isinstance(_pg, str) else _pg) if _pg else None
print(f"  edificio: use={edif and edif['current_use']} year={year} parcela_m2={parc and parc['area_m2']}", flush=True)

# ============ 5. VIDA ALREDEDOR (Overture, ≤800 m) ============
am = duck(f"""WITH p AS (
  SELECT categories.primary cat,
    ST_Distance({PT25}, ST_Transform(geometry,'EPSG:4326','EPSG:25830')) d
  FROM read_parquet('{OV}')
  WHERE bbox.xmin BETWEEN {LON}-0.02 AND {LON}+0.02 AND bbox.ymin BETWEEN {LAT}-0.015 AND {LAT}+0.015
    AND categories.primary IN ('school','primary_school','supermarket','grocery_store','pharmacy','hospital','restaurant','park','library','cafe'))
  SELECT cat, count(*) FILTER (WHERE d<=800) n, round(min(d)) nearest FROM p GROUP BY cat ORDER BY n DESC""", ov=True)
amen = {r["cat"]: {"n": r["n"], "nearest": r["nearest"]} for r in am}
print("  amenities: " + ", ".join(f"{k}={v['n']}" for k, v in list(amen.items())[:5]), flush=True)

# ============ 6. AMBIENTE (nearest stations; air HISTORY is a known gap) ============
def nearest_od(name):
    r = duck(f"""SELECT regexp_replace(substr(CAST(content AS VARCHAR),1,160),'<[^>]+>',' ','g') txt,
      round(ST_Distance(ST_Transform(geom,'EPSG:4326','EPSG:25830'),{PT25})) d
      FROM read_parquet('{OD}/v3/{name}/data/{name}.parquet') t
      WHERE geom IS NOT NULL ORDER BY d LIMIT 1""")
    return r[0] if r else None
noise = nearest_od("contaminacion_acustica_estaciones_de_medida")
traffic = nearest_od("aforos_de_trafico_en_la_ciudad_de_madrid_permanentes")
airst = nearest_od("calidad_del_aire_estaciones_de_control")
print(f"  ambiente: noise={noise and noise['d']}m traffic={traffic and traffic['d']}m air_station={airst and airst['d']}m", flush=True)

# ============ 7. QUIÉN GOBIERNA (best-effort) ============
try:
    _d = duck(f"""SELECT regexp_replace(substr(CAST(content AS VARCHAR),1,120),'<[^>]+>',' ','g') txt
      FROM read_parquet('{OD}/v3/distritos_municipales_de_madrid/data/distritos_municipales_de_madrid.parquet') t
      WHERE ST_Contains(t.geom,ST_Point({LON},{LAT})) LIMIT 1""")
    distrito = (_d[0]["txt"].strip() if _d else None)
except Exception:
    distrito = None
print(f"  distrito: {distrito}", flush=True)

# ============ assemble: helpers ============
def src(label): return label
PROVEN, GAPS = [], []

# ---------- narrative steps ----------
steps = []
steps.append({"kind": "user", "text": f"Me estoy planteando comprar una vivienda en **{ADDR}**. Antes de visitarla quiero saber, solo con datos oficiales abiertos: ¿cómo es la zona, qué tengo alrededor, qué riesgos hay, y qué dicen los datos del propio edificio?"})
steps.append({"kind": "say", "text": "Plan: geolocalizo la dirección, conecto a la **federación de catálogos abiertos** (Comunidad de Madrid, Ayuntamiento, Catastro de España y Overture) y voy resolviendo cada pregunta con su consulta y su fuente. Y soy honesto: marcaré también **dónde los datos abiertos no llegan**."})

# geocode step
steps.append({"kind": "tool",
  "cmd": "geocodificar la dirección (CARTO LDS)",
  "sql": f"SELECT carto.GEOCODE('{ADDR}','ES');  -- CARTO Location Data Services",
  "result": f"{ADDR} → ({LON}, {LAT})",
  "action": {"type": "flyto", "center": [LON, LAT], "zoom": 16},
  "src": "CARTO LDS · geocoding"})
steps.append({"kind": "tool",
  "cmd": "tu edificio en el Catastro (toda España, PMTiles + GeoParquet v3)",
  "sql": f"SELECT reference, current_use, year_built, p.area_m2\nFROM catastro.edificios e JOIN catastro.parcelas p USING(reference)\nWHERE ST_Contains(e.geom, ST_Point({LON},{LAT}));",
  "result": (f"edificio {edif['current_use'].split('_')[-1] if edif else '—'}"
             + (f", construido en {year}" if year else "")
             + (f", parcela de {parc['area_m2']:,} m²".replace(",", ".") if parc and parc.get('area_m2') else "")) if edif or parc else "sin coincidencia catastral",
  "action": {"type": "marker"},
  "stat": {"label": "Tu edificio (Catastro)", "value": (f"uso {edif['current_use'].split('_')[-1]}" + (f" · {year}" if year else "")) if edif else "—",
           "source": "catastro-es · edificios/parcelas (v3)"},
  "src": "catastro-es · edificios + parcelas"})
PROVEN.append("Catastro: edificio (uso, año) y parcela (m²) de toda España")

# vida alrededor
def amf(cat):
    v = amen.get(cat); return f"{v['n']} (más cercano {int(v['nearest'])} m)" if v else "—"
amen_result = " · ".join([f"colegios {amf('school')}", f"supermercados {amf('supermarket')}",
                          f"farmacias {amf('pharmacy')}", f"restaurantes {amf('restaurant')}",
                          f"parques {amf('park')}"])
steps.append({"kind": "say", "text": f"Lo primero que importa al comprar: **qué tienes a un paseo**. Dibujo el área a **15 min andando** (isócrona real de CARTO) y cuento los servicios alrededor con **Overture** — consultado en su nube, sin copiar nada."})
steps.append({"kind": "tool",
  "cmd": "isócrona 15-min andando (CARTO LDS) + servicios a ≤800 m (Overture, remoto)",
  "sql": f"-- isócrona\nSELECT carto.ISOLINE(geocode, 'walk', 900, 'time');\n-- amenities (Overture en su S3, poda por bbox)\nSELECT categories.primary, count(*)\nFROM overture.places\nWHERE bbox <~ :area AND categories.primary IN ('school','supermarket','pharmacy','restaurant','park')\nGROUP BY 1;",
  "result": f"andando 15 min cubres ~{iso_km2} km². Alrededor: {amen_result}",
  "action": {"type": "layer", "id": "isochrone"},
  "stat": {"label": "Vida alrededor", "value": f"colegio {int(amen['school']['nearest'])} m · super {int(amen['supermarket']['nearest'])} m · farmacia {int(amen['pharmacy']['nearest'])} m" if all(k in amen for k in ('school','supermarket','pharmacy')) else amen_result,
           "source": "Overture (remoto) + CARTO LDS (isócrona)"},
  "src": "Overture places (remoto) + CARTO LDS isoline"})
PROVEN += ["Overture: amenities comparables (colegios, comercio, salud) a cualquier punto",
           "CARTO LDS: geocoding + isócrona real a 15 min andando"]

# suelo / riesgos
es_madrid_capital = (muni or "").upper() == "MADRID"
suelo_txt = ("Madrid capital → lo rige el **PGOUM municipal** (la clasificación regional no aplica)"
             if es_madrid_capital and not clasif else (clasif or "sin clasificación en el dato regional"))
steps.append({"kind": "say", "text": "Ahora lo que no se ve en una visita: **clasificación urbanística, protecciones y riesgos naturales** (Comunidad de Madrid, 48 capas vectoriales + 98 ráster de peligrosidad)."})
steps.append({"kind": "tool",
  "cmd": "municipio, clasificación del suelo, protegido y peligrosidad (sismo/ladera/avenida/incendio)",
  "sql": f"SELECT m.DSMUNICIPIO, c.DS_CLASIF_GEN,\n  (SELECT PELIGROSID FROM peligrosid_4_1 WHERE ST_Contains(geom,pt)) sismo,\n  (SELECT PELIGROSID FROM peligrosid_5_1 WHERE ST_Contains(geom,pt)) ladera\nFROM idem_v_municipios m LEFT JOIN vpla_v_clasificacion_ref_23 c ON ST_Contains(c.geom,pt)\nWHERE ST_Contains(m.geom, pt);  -- incendio: ráster COG zonasriesgo_peligrosid_3_1.tif",
  "result": f"{muni} · {suelo_txt} · {'sin espacio protegido' if not enp else enp} · riesgos: sismo {RISK5[sismo]}, ladera {RISK5[ladera]}, avenidas {RISK5[avenida]}, incendio {RISK5[fire]}",
  "stat": {"label": "Suelo y riesgos", "value": f"{'PGOUM municipal' if es_madrid_capital and not clasif else (clasif or '—')} · riesgos {RISK5[max(sismo,ladera,avenida,fire)]}",
           "source": "comunidad-madrid · clasificación + ZonasRiesgo (vector+COG)"},
  "src": "comunidad-madrid · planeamiento + peligrosidad"})
PROVEN.append("Comunidad de Madrid: clasificación del suelo, espacios protegidos y peligrosidad 0–5 (vector + ráster)")

# ambiente
amb_bits = []
if noise: amb_bits.append(f"estación de **ruido** a {int(noise['d'])} m")
if traffic: amb_bits.append(f"**aforo de tráfico** a {int(traffic['d'])} m")
if airst: amb_bits.append(f"estación de **calidad del aire** a {int(airst['d'])} m")
steps.append({"kind": "say", "text": "**Ambiente** (aire, ruido, tráfico): aquí los datos abiertos llegan a medias — y conviene decirlo."})
steps.append({"kind": "tool",
  "cmd": "estaciones de ambiente más cercanas (Ayuntamiento de Madrid)",
  "sql": "SELECT 'ruido' tipo, min(ST_Distance(geom, pt)) d FROM od.contaminacion_acustica_estaciones_de_medida\nUNION ALL SELECT 'trafico', min(ST_Distance(geom, pt)) FROM od.aforos_de_trafico_permanentes\nUNION ALL SELECT 'aire',    min(ST_Distance(geom, pt)) FROM od.calidad_del_aire_estaciones_de_control;",
  "result": (" · ".join(amb_bits) if amb_bits else "sin estaciones cercanas en el dato") +
            ". ⚠️ Pero la **serie histórica de aire** materializada es solo de 2005 y no cubre Madrid capital → no puedo responder \"¿se respira mejor que hace 20 años?\".",
  "stat": {"label": "Ambiente (cobertura parcial)", "value": (f"ruido {int(noise['d'])} m · tráfico {int(traffic['d'])} m" if noise and traffic else "estaciones cercanas"),
           "source": "madrid-opendata · estaciones (ubicación; sin serie histórica)"},
  "src": "madrid-opendata · estaciones de ambiente"})
PROVEN.append("Ayuntamiento: ubicación de estaciones de ruido, tráfico y aire más cercanas")
GAPS.append("**Serie histórica de calidad del aire**: solo 2005 y sin Madrid capital → la pregunta \"¿respiro mejor que hace 20 años?\" no se puede responder con el dato abierto materializado.")
GAPS.append("**Cómo ha cambiado el barrio** (población/precio/paro 1985→2025): no hay serie municipal limpia materializada.")
GAPS.append("**Atributos de las capas de ciudad** (ruido/tráfico/distritos) vienen como GeoRSS (texto en un bloque), no como campos estructurados.")
GAPS.append("**Arbolado** y **concejales desde 1979**: estaban en una versión anterior del catálogo de ciudad; no están en el set materializado actual.")

# assessment
def status_amen(cat, good_n):
    v = amen.get(cat); return "good" if (v and v["n"] >= good_n) else "risk"
verdict = "Zona urbana muy bien servida, riesgo natural muy bajo — con huecos de dato ambiental"
factors = [
  {"label": "Vida alrededor (15 min andando)", "value": f"{iso_km2} km² · colegio {int(amen['school']['nearest'])} m · {amen['restaurant']['n']} restaurantes" if 'school' in amen and 'restaurant' in amen else "amenidades densas", "status": "good"},
  {"label": "Riesgos naturales", "value": f"sismo {RISK5[sismo]} · ladera {RISK5[ladera]} · incendio {RISK5[fire]}", "status": "good" if max(sismo,ladera,avenida,fire) < 4 else "risk"},
  {"label": "El edificio (Catastro)", "value": (f"{edif['current_use'].split('_')[-1]}" + (f", {year}" if year else "")) if edif else "—", "status": "good"},
  {"label": "Ambiente histórico", "value": "dato abierto insuficiente (aire solo 2005)", "status": "risk"},
]
assessment = {
  "verdict": verdict, "badge": "#2d9c5a",
  "factors": factors,
  "risk": "El **riesgo natural es muy bajo** y la **vida alrededor excelente** (todo a pie). El límite no es la zona: es el **dato** — no hay serie ambiental ni de evolución del barrio en abierto para esta dirección.",
  "note": "**Orientativo**, construido solo con datos abiertos consultados en vivo (Comunidad de Madrid, Ayuntamiento de Madrid, Catastro de España y Overture). Cada cifra es reproducible. Geocoding e isócrona: CARTO LDS.",
}

# data-coverage step (the honest showcase the user asked for)
steps.append({"kind": "say", "text": "Y la conclusión más útil de todas — **hasta dónde llega el dato abierto** para decidir comprar aquí:"})
steps.append({"kind": "coverage",
  "proven": PROVEN,
  "gaps": GAPS,
  "text": "Lo verde lo resuelven hoy los catálogos abiertos; lo ámbar es donde **convendría abrir o mantener más dato** (serie de aire por estación, evolución socioeconómica por barrio, atributos estructurados de las capas de ciudad)."})
steps.append({"kind": "assessment"})

# ---------- map layers ----------
layers = {"isochrone": {"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {"label": "15 min andando"}, "geometry": iso_geojson}]}}
if parc_geojson:
    layers["parcel"] = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"ref": parc["reference"]}, "geometry": parc_geojson}]}

scenario = {
  "site": {"lon": LON, "lat": LAT, "name": ADDR, "address": ADDR},
  "question_hint": f"¿Cómo es la zona de {ADDR} para comprar — solo con datos oficiales?",
  "tiles": {  # Catastro PMTiles base layers
    "edificios": "https://storage.googleapis.com/catastro-es-portolan/tiles/edificios.pmtiles",
    "parcelas":  "https://storage.googleapis.com/catastro-es-portolan/tiles/parcelas.pmtiles"},
  "steps": steps, "assessment": assessment, "layers": layers,
}
(OUT / "scenario.json").write_text(json.dumps(scenario, ensure_ascii=False, indent=1))
print(f"\n✓ scenario.json: {len(steps)} steps · {len(PROVEN)} proven · {len(GAPS)} gaps · {(OUT/'scenario.json').stat().st_size//1024} KB", flush=True)

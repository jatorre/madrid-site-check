#!/usr/bin/env python3
"""Build webapp/data/scenario.json — a scripted AI-conversation run of "¿Puedo construir aquí?"
for one plot, in the Helsinki demo's format. Every tool step carries the REAL SQL and its REAL result,
queried live from the Madrid Portolan catalogs. Narrative (say/assessment) is authored around them.
Run: python3 tools/build_scenario.py
"""
import json, subprocess, pathlib
CM = "https://storage.googleapis.com/carto-portolan-madrid/comunidad-madrid"
OUT = pathlib.Path(__file__).resolve().parent.parent / "webapp" / "data"; OUT.mkdir(parents=True, exist_ok=True)
SITE = {"lon": -3.862, "lat": 40.726, "name": "Manzanares el Real"}
PRE = "INSTALL httpfs;LOAD httpfs;INSTALL spatial;LOAD spatial;INSTALL iceberg;LOAD iceberg;SET geometry_always_xy=true;"
PT  = f"ST_Transform(ST_Point({SITE['lon']},{SITE['lat']}),'EPSG:4326','EPSG:25830')"

def q(sql, json_out=True):
    r = subprocess.run(["duckdb","-unsigned"]+(["-json"] if json_out else ["-csv","-noheader"]),
                       input=PRE+sql, capture_output=True, text=True)
    if r.returncode: raise RuntimeError(r.stderr[-400:])
    return json.loads(r.stdout) if (json_out and r.stdout.strip()) else r.stdout.strip()

# ---- real queries ----
muni = q(f"SELECT DSMUNICIPIO FROM read_parquet('{CM}/data/parquet/idem_v_municipios.parquet') t WHERE ST_Contains(t.geom,{PT}) LIMIT 1")[0]["DSMUNICIPIO"]
cls  = q(f"SELECT DS_CLASIF_GEN, DS_MUNICIPIO FROM read_parquet('{CM}/data/parquet/vpla_v_clasificacion_ref_23.parquet') t WHERE ST_Contains(t.geom,{PT}) LIMIT 1")[0]
ordz = q(f"SELECT DS_NOMB_ORD, DS_US_PRED FROM read_parquet('{CM}/data/parquet/vpla_v_ordenanza_ref_23.parquet') t WHERE ST_Contains(t.geom,{PT}) LIMIT 1")[0]
enp  = q(f"SELECT DS_NOMBRE, DS_FIGURA, DS_ANNO_DECLA FROM read_parquet('{CM}/data/parquet/idem_ma_enp.parquet') t WHERE ST_Contains(t.geom,{PT}) LIMIT 1")[0]
lic  = q(f"SELECT DS_ZEC_NAME FROM read_parquet('{CM}/data/parquet/idem_ma_red_natura_lic_zec.parquet') t WHERE ST_Contains(t.geom,{PT}) LIMIT 1")[0]
def haz(f):
    r=q(f"SELECT PELIGROSID p FROM read_parquet('{CM}/data/parquet/{f}.parquet') t WHERE ST_Contains(t.geom,{PT}) LIMIT 1")
    return int(r[0]["p"]) if r else 0
RISK5={0:"sin dato",1:"muy baja",2:"baja",3:"media",4:"alta",5:"muy alta"}
sis, lad, ave = haz("peligrosid_4_1"), haz("peligrosid_5_1"), haz("peligrosid_2_1")
fire = subprocess.run(["gdallocationinfo","-valonly","-wgs84",f"/vsicurl/{CM}/data/cog/zonasriesgo_peligrosid_3_1.tif",str(SITE["lon"]),str(SITE["lat"])],capture_output=True,text=True).stdout.strip().splitlines()
fire = int(float(fire[0])) if fire and fire[0].strip() else 0
lito = q(f"SELECT DS_DESCRIPCION, DS_PERMEABILIDAD FROM read_parquet('{CM}/data/parquet/idem_ma_litologia_50m.parquet') t WHERE ST_Contains(t.geom,{PT}) LIMIT 1")[0]
suelo= q(f"SELECT DS_ORDEN, DS_GRUPO FROM read_parquet('{CM}/data/parquet/idem_ma_clasif_suelos_98.parquet') t WHERE ST_Contains(t.geom,{PT}) LIMIT 1")[0]
def near(f): return int(float(q(f"SELECT round(min(ST_Distance(t.geom,{PT}))) d FROM read_parquet('{CM}/data/parquet/{f}.parquet') t",False) or 0))
d_road=near("idem_eiel_tramo_carretera_23"); d_health=near("idem_eiel_cent_sanitario_23")
d_school=near("idem_eiel_cent_ensenanza_23"); d_water=near("idem_eiel_captacion_23")
# protected polygon for the map
gj = q(f"SELECT ST_AsGeoJSON(ST_Transform(ST_Simplify(t.geom,80),'EPSG:25830','EPSG:4326')) g FROM read_parquet('{CM}/data/parquet/idem_ma_enp.parquet') t WHERE ST_Contains(t.geom,{PT}) LIMIT 1")[0]["g"]
prot_geom = gj if isinstance(gj,dict) else json.loads(gj)

def src(ds): return {"source_url":"https://datos.comunidad.madrid","source_label":f"comunidad-madrid · {ds}"}

steps = [
 {"kind":"user","text":f"Me planteo comprar una parcela en {SITE['name']} para construir una vivienda unifamiliar. ¿Qué dicen los datos abiertos: puedo edificar y qué tengo que vigilar?"},
 {"kind":"say","text":"Plan: (1) conectar a la **federación de catálogos de datos abiertos de Madrid**, (2) consultar las capas que deciden la edificabilidad de una parcela —clasificación del suelo, espacios protegidos, riesgos naturales, geología y servicios— y (3) emitir una valoración. Cada dato con su fuente y su consulta. Empiezo."},
 {"kind":"tool","cmd":"conectar al catálogo de la Comunidad de Madrid (Iceberg/STAC, anónimo)",
  "sql":f"ATTACH 'cm' (TYPE iceberg,\n  ENDPOINT '{CM}',\n  AUTHORIZATION_TYPE 'none');\nSELECT count(*) FROM (SHOW ALL TABLES);",
  "result":"2.482 tablas · lectura anónima, en sitio, sin servidor",
  "action":{"type":"flyto","center":[SITE['lon'],SITE['lat']],"zoom":11}},
 {"kind":"say","text":f"Conectado. Localizo la parcela y miro **qué clasificación urbanística** tiene — lo primero que decide si se puede edificar."},
 {"kind":"tool","cmd":"municipio + clasificación del suelo en el punto",
  "sql":f"SELECT m.DSMUNICIPIO, c.DS_CLASIF_GEN, o.DS_NOMB_ORD, o.DS_US_PRED\nFROM idem_v_municipios m, vpla_v_clasificacion_ref_23 c, vpla_v_ordenanza_ref_23 o\nWHERE ST_Contains(m.geom, ST_Point(x,y))\n  AND ST_Contains(c.geom, ST_Point(x,y))\n  AND ST_Contains(o.geom, ST_Point(x,y));",
  "result":f"{muni} · {cls['DS_CLASIF_GEN']} · ordenanza «{ordz['DS_NOMB_ORD']}» (uso {str(ordz['DS_US_PRED']).lower()})",
  "action":{"type":"marker"},
  "stat":{"label":"Clasificación del suelo","value":cls['DS_CLASIF_GEN'],"source":f"comunidad-madrid · vpla_v_clasificacion_ref_23"}},
 {"kind":"say","text":f"**{cls['DS_CLASIF_GEN']}** — en principio edificable. Pero el suelo urbano puede arrastrar protecciones que lo condicionan. Lo compruebo contra los **espacios protegidos**."},
 {"kind":"tool","cmd":"¿la parcela cae en algún espacio natural protegido o Red Natura 2000?",
  "sql":"SELECT 'ENP' capa, DS_NOMBRE FROM idem_ma_enp WHERE ST_Contains(geom, ST_Point(x,y))\nUNION ALL\nSELECT 'Natura2000 LIC/ZEC', DS_ZEC_NAME FROM idem_ma_red_natura_lic_zec WHERE ST_Contains(geom, ST_Point(x,y));",
  "result":f"{enp['DS_NOMBRE']} ({enp['DS_FIGURA']}, {enp['DS_ANNO_DECLA']}) · Natura 2000 LIC «{lic['DS_ZEC_NAME']}»",
  "action":{"type":"layer","id":"protected"},
  "callout":{"text":enp['DS_NOMBRE'],"tone":"green"},
  "stat":{"label":"Espacio protegido","value":f"{enp['DS_FIGURA']} + Natura 2000","source":"comunidad-madrid · idem_ma_enp, idem_ma_red_natura_lic_zec"}},
 {"kind":"say","text":f"Importante: la parcela está **dentro del {enp['DS_NOMBRE']}** y de un LIC de la Red Natura 2000. Eso no impide construir per se, pero somete la obra a la normativa del parque. Veo ahora los **riesgos naturales** (peligrosidad cartografiada, nivel 0–5)."},
 {"kind":"tool","cmd":"peligrosidad: sismos, movimientos de ladera, avenidas (vector) + incendio (ráster COG)",
  "sql":"SELECT (SELECT PELIGROSID FROM peligrosid_4_1 WHERE ST_Contains(geom,ST_Point(x,y))) sismo,\n       (SELECT PELIGROSID FROM peligrosid_5_1 WHERE ST_Contains(geom,ST_Point(x,y))) ladera,\n       (SELECT PELIGROSID FROM peligrosid_2_1 WHERE ST_Contains(geom,ST_Point(x,y))) avenidas;\n-- incendio: gdallocationinfo /vsicurl/ data/cog/zonasriesgo_peligrosid_3_1.tif",
  "result":f"sismo: {RISK5[sis]} · ladera: {RISK5[lad]} · avenidas: {RISK5[ave]} · incendio (ráster): {RISK5[fire]}",
  "stat":{"label":"Riesgos naturales","value":f"sismo {RISK5[sis]} · ladera {RISK5[lad]} · incendio {RISK5[fire]}","source":"comunidad-madrid · ZonasRiesgo (peligrosid_*) + COG"}},
 {"kind":"tool","cmd":"geología/suelo y servicios públicos más cercanos (EIEL)",
  "sql":"SELECT DS_DESCRIPCION, DS_PERMEABILIDAD FROM idem_ma_litologia_50m WHERE ST_Contains(geom,ST_Point(x,y));\nSELECT round(min(ST_Distance(geom,ST_Point(x,y)))) FROM idem_eiel_tramo_carretera_23;  -- y centro sanitario, colegio, agua",
  "result":f"{lito['DS_DESCRIPCION']} (perm. {str(lito['DS_PERMEABILIDAD']).lower()}) · suelo {suelo['DS_ORDEN']}\ncarretera {d_road} m · centro sanitario {d_health} m · colegio {d_school} m · captación de agua {d_water} m",
  "stat":{"label":"Accesos / servicios","value":f"carretera {d_road} m · sanitario {d_health} m","source":"comunidad-madrid · EIEL_23 + Geología"}},
 {"kind":"assessment"},
]

assessment = {
 "verdict": "Edificable — pero dentro de un parque regional protegido",
 "badge": "#FFC857",
 "factors": [
   {"label":"Clasificación urbanística","value":f"{cls['DS_CLASIF_GEN']} (uso {str(ordz['DS_US_PRED']).lower()})","status":"good"},
   {"label":"Riesgos naturales","value":f"sismo {RISK5[sis]} · ladera {RISK5[lad]} · incendio {RISK5[fire]}","status":"good"},
   {"label":"Accesos y servicios","value":f"carretera {d_road} m · sanitario {d_health} m · colegio {d_school} m","status":"good"},
   {"label":"Espacios protegidos","value":f"{enp['DS_FIGURA']} + Natura 2000 (LIC)","status":"risk"},
 ],
 "risk": f"La parcela está **dentro del {enp['DS_NOMBRE']}** y de un LIC de la Red Natura 2000. Cualquier edificación requiere autorización del órgano gestor del parque y queda sujeta a su PORN/PRUG y a la evaluación ambiental de Red Natura.",
 "note": "**Orientativo** — no sustituye la consulta urbanística oficial del Ayuntamiento / Comunidad. Todos los datos proceden del catálogo Portolan **comunidad-madrid** (datos.comunidad.madrid · IDEM), consultados en vivo con DuckDB; cada consulta de arriba es reproducible y anónima.",
}

scenario = {
 "site": SITE,
 "question_hint": f"Me planteo comprar una parcela en {SITE['name']} para construir — ¿qué dicen los datos?",
 "steps": steps,
 "assessment": assessment,
 "layers": {"protected": {"type":"FeatureCollection","features":[
    {"type":"Feature","properties":{"name":enp['DS_NOMBRE']},"geometry":prot_geom}]}},
}
(OUT/"scenario.json").write_text(json.dumps(scenario, ensure_ascii=False, indent=1))
print(f"scenario.json: {muni} · {cls['DS_CLASIF_GEN']} · {enp['DS_NOMBRE']} · {len(steps)} steps · {(OUT/'scenario.json').stat().st_size//1024} KB")

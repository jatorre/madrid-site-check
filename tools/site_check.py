#!/usr/bin/env python3
"""¿Puedo construir aquí? — plot due-diligence from the Madrid open-data Portolan catalogs.

Input:  a point (lat, lon) [+ optional label].  Output: a sourced "plot report" — for every line,
the catalog · dataset it came from, queried live & anonymously (DuckDB for vectors, GDAL for the
hazard COGs). No downloads, no server. This is the citizen/developer counterpart of a site screening:
land classification, protected areas, natural hazards, geology/soil, and nearest public services.

Usage:
    python3 tools/site_check.py <lat> <lon> ["label"]
    python3 tools/site_check.py --samples            # run the 3 demo plots

Orientativo — no sustituye la consulta urbanística oficial del Ayuntamiento / Comunidad.
"""
import json, subprocess, sys, os, pathlib
CM   = "https://storage.googleapis.com/carto-portolan-madrid/comunidad-madrid"
CITY = "https://storage.googleapis.com/carto-portolan-madrid/madrid-city"
ROOT = pathlib.Path(__file__).resolve().parent.parent
REPORTS = ROOT/"reports"; REPORTS.mkdir(exist_ok=True)

# 5-class hazard convention used by the Comunidad's risk rasters (Byte 1..5)
RISK5 = {0:"sin dato",1:"muy baja",2:"baja",3:"media",4:"alta",5:"muy alta"}

# ---- vector checks: (key, label, file, mode, dist_m, fields, catalog) ----
VEC = [
 ("municipio","Municipio","idem_v_municipios","contains",0,["DSMUNICIPIO"],"comunidad-madrid"),
 ("clasificacion","Clasificación del suelo (planeamiento)","vpla_v_clasificacion_ref_23","contains",0,["DS_CLASIF_GEN","DS_CLASIF_DET","DS_MUNICIPIO"],"comunidad-madrid"),
 ("ordenanza","Ordenanza / uso predominante","vpla_v_ordenanza_ref_23","contains",0,["DS_NOMB_ORD","DS_US_PRED","DS_TIPO_VIV"],"comunidad-madrid"),
 ("enp","Espacio Natural Protegido","idem_ma_enp","contains",0,["DS_NOMBRE","DS_FIGURA"],"comunidad-madrid"),
 ("natura_lic","Natura 2000 — LIC/ZEC (hábitats)","idem_ma_red_natura_lic_zec","contains",0,["DS_ZEC_NAME"],"comunidad-madrid"),
 ("natura_zepa","Natura 2000 — ZEPA (aves)","idem_ma_red_natura_zepa","contains",0,["DS_ZEPA"],"comunidad-madrid"),
 ("monte_up","Monte de Utilidad Pública","idem_ma_montes_up","contains",0,["DS_NOMBRE","DS_NOM_PROPIETARIO"],"comunidad-madrid"),
 ("monte_pres","Monte Preservado (Ley 16/1995)","idem_ma_montes_preservados","contains",0,[],"comunidad-madrid"),
 ("via_pecuaria","Vía pecuaria (≤50 m)","idem_ma_vias_pecuarias","within",50,["DS_NOMBRE","DS_TIPO"],"comunidad-madrid"),
 ("humedal","Humedal catalogado","idem_ma_ceh_humedales","contains",0,[],"comunidad-madrid"),
 ("flood_aven","Peligrosidad por avenidas y crecidas","peligrosid_2_1","contains",0,["PELIGROSID"],"comunidad-madrid"),
 ("flood_torr","Peligrosidad por torrencialidad en cauces","peligrosid_2_2","contains",0,["PELIGROSID"],"comunidad-madrid"),
 ("presa","Peligrosidad por rotura de presas","peligrosid_2_3","contains",0,["PELIGROSID"],"comunidad-madrid"),
 ("seismic","Peligrosidad por sismos","peligrosid_4_1","contains",0,["PELIGROSID"],"comunidad-madrid"),
 ("landslide","Peligrosidad por movimientos de ladera","peligrosid_5_1","contains",0,["PELIGROSID"],"comunidad-madrid"),
 ("subsid","Peligrosidad por subsidencias","peligrosid_5_4","contains",0,["PELIGROSID"],"comunidad-madrid"),
 ("expans","Peligrosidad por terrenos expansivos","peligrosid_5_5","contains",0,["PELIGROSID"],"comunidad-madrid"),
 ("litologia","Litología","idem_ma_litologia_50m","contains",0,["DS_DESCRIPCION","DS_CLASE","DS_PERMEABILIDAD"],"comunidad-madrid"),
 ("suelo","Tipo de suelo (Soil Taxonomy)","idem_ma_clasif_suelos_98","contains",0,["DS_ORDEN","DS_GRUPO"],"comunidad-madrid"),
]
# ---- nearest-service checks (EIEL infrastructure) ----
SVC = [
 ("agua","Captación / abastecimiento de agua","idem_eiel_captacion_23"),
 ("depuradora","Depuradora (saneamiento)","idem_eiel_depuradora_23"),
 ("carretera","Tramo de carretera","idem_eiel_tramo_carretera_23"),
 ("ensenanza","Centro de enseñanza","idem_eiel_cent_ensenanza_23"),
 ("sanitario","Centro sanitario","idem_eiel_cent_sanitario_23"),
]
# ---- raster hazard COGs (sampled at the point) ----
RAS = [
 ("r_incendio","Peligrosidad de incendio forestal","zonasriesgo_peligrosid_3_1"),
 ("r_sismico","Riesgo sísmico","zonasriesgo_riesgo_4_1"),
 ("r_ladera","Riesgo por movimientos de ladera","zonasriesgo_riesgo_5_1"),
 ("r_avenidas","Riesgo por avenidas y crecidas","zonasriesgo_riesgo_2_1"),
]

def duck_json(sql):
    r = subprocess.run(["duckdb","-unsigned","-json","-c",
        "INSTALL httpfs;LOAD httpfs;INSTALL spatial;LOAD spatial;SET geometry_always_xy=true;"+sql],
        capture_output=True, text=True)
    if r.returncode: raise RuntimeError(r.stderr[-500:])
    return json.loads(r.stdout) if r.stdout.strip() else []

def to_utm(lat, lon):
    row = duck_json(f"SELECT ST_X(g) x, ST_Y(g) y FROM (SELECT ST_Transform(ST_Point({lon},{lat}),'EPSG:4326','EPSG:25830') g)")[0]
    return row["x"], row["y"]

def vec_check(x, y, cfg):
    key,label,fil,mode,dist,fields,cat = cfg
    flds = (", "+", ".join(f'"{f}"' for f in fields)) if fields else ""
    pred = f"ST_Contains(t.geom, ST_Point({x},{y}))" if mode=="contains" else f"ST_DWithin(t.geom, ST_Point({x},{y}), {dist})"
    bbox = f"t.bbox.xmin<={x} AND t.bbox.xmax>={x} AND t.bbox.ymin<={y+dist} AND t.bbox.ymax>={y-dist}" if mode=="within" \
           else f"t.bbox.xmin<={x} AND t.bbox.xmax>={x} AND t.bbox.ymin<={y} AND t.bbox.ymax>={y}"
    sql = f"SELECT TRUE hit{flds} FROM read_parquet('{CM}/data/parquet/{fil}.parquet') t WHERE {bbox} AND {pred} LIMIT 1;"
    try:
        rows = duck_json(sql)
    except RuntimeError:  # field missing -> presence only
        rows = duck_json(f"SELECT TRUE hit FROM read_parquet('{CM}/data/parquet/{fil}.parquet') t WHERE {bbox} AND {pred} LIMIT 1;")
    hit = bool(rows)
    detail = {f: rows[0].get(f) for f in fields} if hit and fields else {}
    return {"key":key,"label":label,"hit":hit,"detail":detail,
            "source":{"catalog":cat,"dataset":fil,"check":mode + (f" {dist}m" if mode=="within" else "")}}

OD = "https://storage.googleapis.com/carto-portolan-madrid/madrid-opendata"  # city open-data catalog (EPSG:4326)
# city layers, queried only when the plot is in Madrid municipality. (geom col 'geometry', CRS 4326)
OD_NEAR = [
 ("od_parque","Parque/jardín municipal (0 m = dentro)","principales_parques_y_jardines_municipales"),
 ("od_aire","Estación de calidad del aire","calidad_del_aire_estaciones_de_control"),
 ("od_ruido","Estación de medida de ruido","contaminacion_acustica_estaciones_de_medida"),
]
def od_nearest(lon, lat, cfg):
    key,label,fil = cfg
    # distance in metres: transform both to EPSG:25830
    sql = (f"SELECT round(min(ST_Distance("
           f"ST_Transform(t.geometry,'EPSG:4326','EPSG:25830'),"
           f"ST_Transform(ST_Point({lon},{lat}),'EPSG:4326','EPSG:25830')))) d "
           f"FROM read_parquet('{OD}/data/parquet/{fil}.parquet') t;")
    try:
        rows = duck_json(sql); d = rows[0]["d"] if rows else None
    except RuntimeError:
        d = None
    return {"key":key,"label":label,"nearest_m":d,"source":{"catalog":"madrid-opendata","dataset":fil,"check":"nearest"}}

def svc_check(x, y, cfg):
    key,label,fil = cfg
    try:
        rows = duck_json(f"SELECT round(min(ST_Distance(t.geom, ST_Point({x},{y})))) d FROM read_parquet('{CM}/data/parquet/{fil}.parquet') t;")
        d = rows[0]["d"] if rows else None
    except RuntimeError:
        d = None
    return {"key":key,"label":label,"nearest_m":d,"source":{"catalog":"comunidad-madrid","dataset":fil,"check":"nearest"}}

def ras_check(lat, lon, cfg):
    key,label,fil = cfg
    try:
        r = subprocess.run(["gdallocationinfo","-valonly","-wgs84",f"/vsicurl/{CM}/data/cog/{fil}.tif",str(lon),str(lat)],
                           capture_output=True, text=True, timeout=120)
        v = r.stdout.strip().splitlines()
        val = int(float(v[0])) if v and v[0].strip() not in ("","nan") else None
    except Exception:
        val = None
    return {"key":key,"label":label,"class":val,"class_label":RISK5.get(val,"—"),
            "source":{"catalog":"comunidad-madrid","dataset":f"data/cog/{fil}.tif","check":"raster sample"}}

HAZARD_VEC = ("flood_aven","flood_torr","presa","seismic","landslide","subsid","expans")
PROT_KEYS  = ("enp","natura_lic","natura_zepa","monte_up","monte_pres","humedal")
def haz_level(c): return int(c["detail"].get("PELIGROSID") or 0) if c.get("hit") else 0

def verdict(rep):
    cls = (rep["checks"]["clasificacion"]["detail"].get("DS_CLASIF_GEN") or "").lower()
    prot = [c["label"] for c in rep["checks"].values() if isinstance(c,dict) and c.get("hit") and c["key"] in PROT_KEYS]
    # only flag a hazard as a condicionante when its mapped level is alta/muy alta (>=4)
    haz_v = [f'{rep["checks"][k]["label"]} ({RISK5[haz_level(rep["checks"][k])]})'
             for k in HAZARD_VEC if haz_level(rep["checks"][k]) >= 4]
    haz_r = [f'{c["label"]} ({c["class_label"]})' for c in rep["rasters"] if (c["class"] or 0) >= 4]
    if "no urbanizable" in cls: base="⛔ Suelo NO URBANIZABLE — sin uso residencial general (edificación muy restringida)."
    elif "urbanizable" in cls: base="🟡 Suelo URBANIZABLE — desarrollable previa gestión urbanística."
    elif "urbano" in cls: base="✅ Suelo URBANO — edificable en principio."
    elif cls: base=f"Clasificación: {cls}."
    elif (rep["checks"]["municipio"]["detail"].get("DSMUNICIPIO") or "").upper()=="MADRID":
        base="ℹ️ Municipio de Madrid — rige el planeamiento municipal (PGOUM); la clasificación regional no cubre la capital (consúltese el Geoportal del Ayuntamiento)."
    else: base="❔ Sin clasificación de planeamiento digitalizada en este punto (planeamiento municipal no incorporado al refundido regional)."
    return {"base":base,"protecciones":prot,"peligros_vector":haz_v,"riesgos_altos_raster":haz_r,
            "resumen": base + (" Con condicionantes: " + "; ".join(prot+haz_v+haz_r) if (prot or haz_v or haz_r) else " Sin condicionantes detectados en las capas consultadas.")}

def screen(lat, lon, label=None):
    x, y = to_utm(lat, lon)
    rep = {"input":{"label":label,"lat":lat,"lon":lon,"x_25830":round(x,1),"y_25830":round(y,1)},
           "crs":"EPSG:25830","catalogs":{"comunidad":CM,"city":CITY},
           "checks":{}, "rasters":[], "services":[]}
    for cfg in VEC:
        c = vec_check(x,y,cfg); rep["checks"][c["key"]]=c
    rep["rasters"] = [ras_check(lat,lon,cfg) for cfg in RAS]
    rep["services"]= [svc_check(x,y,cfg) for cfg in SVC]
    # federate the City of Madrid open-data catalog when the plot is in Madrid municipality
    muni = (rep["checks"]["municipio"]["detail"].get("DSMUNICIPIO") or "").upper()
    if muni == "MADRID":
        rep["ciudad"] = [od_nearest(lon,lat,cfg) for cfg in OD_NEAR]
    rep["verdict"] = verdict(rep)
    return rep

def to_markdown(rep):
    L=[]; v=rep["verdict"]; i=rep["input"]
    title = i.get("label") or f"{i['lat']}, {i['lon']}"
    L.append(f"# ¿Puedo construir aquí? — {title}")
    L.append(f"\n**{v['resumen']}**\n")
    L.append(f"_Punto {i['lat']}, {i['lon']} (EPSG:25830 {i['x_25830']}, {i['y_25830']}). "
             f"Fuente: catálogos Portolan Comunidad de Madrid + Ciudad de Madrid, consultados en vivo. "
             f"Orientativo — no sustituye la consulta urbanística oficial._\n")
    def src(c): return f"`{c['source']['catalog']}·{c['source']['dataset']}`"
    ch=rep["checks"]
    L.append("## Ubicación y planeamiento")
    for k in ("municipio","clasificacion","ordenanza"):
        c=ch[k]; det=" — ".join(str(x) for x in c["detail"].values() if x) if c["detail"] else ("sí" if c["hit"] else "—")
        L.append(f"- **{c['label']}:** {det if c['hit'] else '—'}  {src(c)}")
    L.append("\n## Espacios protegidos")
    for k in ("enp","natura_lic","natura_zepa","monte_up","monte_pres","via_pecuaria","humedal"):
        c=ch[k]
        if c["hit"]:
            det=" — ".join(str(x) for x in c["detail"].values() if x) if c["detail"] else "sí"
            L.append(f"- ⚠️ **{c['label']}:** {det}  {src(c)}")
    if not any(ch[k]["hit"] for k in ("enp","natura_lic","natura_zepa","monte_up","monte_pres","via_pecuaria","humedal")):
        L.append("- ✅ Ninguno detectado.")
    L.append("\n## Riesgos naturales")
    L.append("_Nivel cartografiado de peligrosidad (0 sin dato · 1 muy baja · 2 baja · 3 media · 4 alta · 5 muy alta); ⚠️ = alta/muy alta._")
    for k in HAZARD_VEC:
        c=ch[k]
        if c["hit"]:
            lvl=int(c["detail"].get("PELIGROSID") or 0); mark="⚠️ " if lvl>=4 else ""
            L.append(f"- {mark}**{c['label']}:** {lvl} ({RISK5.get(lvl,'—')})  {src(c)}")
    for c in rep["rasters"]:
        if c["class"] is not None:
            mark="⚠️ " if (c["class"] or 0)>=4 else ""
            L.append(f"- {mark}**{c['label']}:** clase {c['class']} ({c['class_label']})  `{c['source']['catalog']}·{c['source']['dataset']}`")
    L.append("\n## Geología y suelo")
    for k in ("litologia","suelo"):
        c=ch[k]; det=" — ".join(str(x) for x in c["detail"].values() if x) if c["detail"] else ("sí" if c["hit"] else "—")
        L.append(f"- **{c['label']}:** {det if c['hit'] else '—'}  {src(c)}")
    L.append("\n## Servicios públicos más cercanos (EIEL)")
    for c in rep["services"]:
        d=c["nearest_m"]; L.append(f"- **{c['label']}:** {f'{int(d)} m' if d is not None else '—'}  `{c['source']['catalog']}·{c['source']['dataset']}`")
    if rep.get("ciudad"):
        L.append("\n## Ciudad de Madrid (catálogo open-data) — federado")
        L.append("_Dentro del municipio de Madrid rige el planeamiento municipal (PGOUM); la clasificación regional puede no aplicar. Capas de la ciudad:_")
        for c in rep["ciudad"]:
            d=c["nearest_m"]
            extra=" — **dentro del recinto**" if (c["key"]=="od_parque" and d==0) else ""
            L.append(f"- **{c['label']}:** {f'{int(d)} m' if d is not None else '—'}{extra}  `{c['source']['catalog']}·{c['source']['dataset']}`")
    return "\n".join(L)

SAMPLES = [
 (40.23603, -3.7665,  "Parla — casco urbano (sur metropolitano)"),
 (40.726,   -3.862,   "Manzanares el Real — casco urbano dentro del Parque Regional"),
 (40.77069, -4.0447,  "Cercedilla — suelo no urbanizable protegido (sierra)"),
 (40.4257,  -3.7038,  "Madrid — Malasaña (federación con catálogo de ciudad)"),
]

def run(lat, lon, label):
    rep = screen(lat, lon, label)
    slug = (label or f"{lat}_{lon}").split("—")[0].strip().lower().replace(" ","_")
    slug = "".join(ch for ch in slug if ch.isalnum() or ch=="_")[:40]
    (REPORTS/f"{slug}.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1))
    (REPORTS/f"{slug}.md").write_text(to_markdown(rep))
    print(to_markdown(rep)); print(f"\n[wrote reports/{slug}.json + .md]\n"+"="*70)
    return rep

if __name__=="__main__":
    if len(sys.argv)>1 and sys.argv[1]=="--samples":
        for lat,lon,lab in SAMPLES: run(lat,lon,lab)
    elif len(sys.argv)>=3:
        run(float(sys.argv[1]), float(sys.argv[2]), sys.argv[3] if len(sys.argv)>3 else None)
    else:
        print(__doc__)

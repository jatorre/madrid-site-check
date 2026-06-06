#!/usr/bin/env python3
"""Informe de mi dirección (prototipo) — dirección → punto → datos oficiales + Overture, con fuente.
Geocoder: OSM/Nominatim DE RELLENO solo para la entrada (en producción: CARTO LDS geocode/isolines).
Federado en vivo: comunidad-madrid (suelo, riesgos) + Overture (amenities, remoto) + madrid-opendata (aire).
Uso: python3 tools/address_report.py "Calle de Alcalá 100, Madrid"
"""
import json, subprocess, sys, urllib.parse, urllib.request, time
CM="https://storage.googleapis.com/carto-portolan-madrid/comunidad-madrid"
OD="https://storage.googleapis.com/carto-portolan-madrid/madrid-opendata"
OVT="s3://overturemaps-us-west-2/release/2026-05-20.0/theme=places/type=place/*.parquet"
RISK5={0:"sin dato",1:"muy baja",2:"baja",3:"media",4:"alta",5:"muy alta"}

def geocode(addr):
    q=urllib.parse.urlencode({"q":addr,"format":"json","limit":1,"countrycodes":"es","addressdetails":1})
    req=urllib.request.Request("https://nominatim.openstreetmap.org/search?"+q,
        headers={"User-Agent":"madrid-site-check/0.1 (jatorre@cartodb.com)"})
    try:
        d=json.load(urllib.request.urlopen(req,timeout=30))
    except Exception: d=None
    if not d: return None
    r=d[0]; return float(r["lat"]), float(r["lon"]), r["display_name"]

def duck(sql, secret=False):
    pre=("INSTALL httpfs;LOAD httpfs;INSTALL spatial;LOAD spatial;SET geometry_always_xy=true;"
         +("CREATE SECRET ov (TYPE s3, PROVIDER config, REGION 'us-west-2');" if secret else ""))
    r=subprocess.run(["duckdb","-unsigned","-json","-c",pre+sql],capture_output=True,text=True)
    out=r.stdout; i=out.rfind('\n[') if secret else -1
    txt=(out[i:] if i!=-1 else out).strip()
    try: return json.loads(txt) if txt else []
    except Exception: return []

def comunidad(lat,lon):
    PT=f"ST_Transform(ST_Point({lon},{lat}),'EPSG:4326','EPSG:25830')"
    def one(f,fld):
        r=duck(f"SELECT {fld} v FROM read_parquet('{CM}/data/parquet/{f}.parquet') t WHERE ST_Contains(t.geom,{PT}) LIMIT 1")
        return r[0]["v"] if r else None
    def haz(f):
        r=duck(f"SELECT PELIGROSID p FROM read_parquet('{CM}/data/parquet/{f}.parquet') t WHERE ST_Contains(t.geom,{PT}) LIMIT 1")
        return int(r[0]["p"]) if r and r[0]["p"] is not None else 0
    return {"municipio":one("idem_v_municipios","DSMUNICIPIO"),
            "clasificacion":one("vpla_v_clasificacion_ref_23","DS_CLASIF_GEN"),
            "enp":one("idem_ma_enp","DS_NOMBRE"),
            "sismo":haz("peligrosid_4_1"),"ladera":haz("peligrosid_5_1"),"avenidas":haz("peligrosid_2_1")}

def overture(lat,lon,rad=800):
    cats=['school','supermarket','pharmacy','hospital','restaurant','park','bus_stop','metro_station']
    rows=duck(f"""
    WITH p AS (SELECT ST_Transform(ST_Point({lon},{lat}),'EPSG:4326','EPSG:25830') g)
    SELECT cat, count(*) n, round(min(d)) cerca FROM (
      SELECT pl.categories.primary cat,
             ST_Distance(ST_Transform(pl.geometry,'EPSG:4326','EPSG:25830'),p.g) d
      FROM read_parquet('{OVT}') pl, p
      WHERE pl.bbox.xmin BETWEEN {lon}-0.02 AND {lon}+0.02 AND pl.bbox.ymin BETWEEN {lat}-0.015 AND {lat}+0.015
        AND pl.categories.primary IN ({','.join("'"+c+"'" for c in cats)}))
    WHERE d<={rad} GROUP BY 1 ORDER BY 3;""", secret=True)
    return rows

def air_station(lat,lon):
    for col in ("geom","geometry"):
        r=duck(f"""SELECT title, round(ST_Distance(ST_Transform({col},'EPSG:4326','EPSG:25830'),
                   ST_Transform(ST_Point({lon},{lat}),'EPSG:4326','EPSG:25830'))) d
                   FROM read_parquet('{OD}/data/parquet/calidad_del_aire_estaciones_de_control.parquet')
                   ORDER BY d LIMIT 1""")
        if r: return r[0]
    return None

def report(addr):
    g=geocode(addr)
    if not g: return f"# Informe de mi dirección — {addr}\n\nNo se pudo geocodificar (geocoder de relleno OSM). Prueba una dirección más precisa o coordenadas."
    lat,lon,disp=g
    c=comunidad(lat,lon); ov=overture(lat,lon); air=air_station(lat,lon)
    L=[f"# Informe de mi dirección — {addr}",
       f"\n_{disp}_  ·  punto {lat:.5f}, {lon:.5f}",
       "_(geocoder OSM/Nominatim **de relleno**; en producción: CARTO LDS)_\n"]
    es_madrid=(c.get("municipio") or "").upper()=="MADRID"
    # Ubicación / suelo
    L.append("## Ubicación y suelo")
    L.append(f"- **Municipio:** {c['municipio'] or '—'}  `comunidad-madrid·idem_v_municipios`")
    if c["clasificacion"]:
        L.append(f"- **Clasificación del suelo:** {c['clasificacion']}  `comunidad-madrid·vpla_v_clasificacion_ref_23`")
    elif es_madrid:
        L.append("- **Suelo:** municipio de Madrid → rige el PGOUM municipal (clasificación regional no cubre la capital)")
    if c["enp"]:
        L.append(f"- ⚠️ **Espacio protegido:** {c['enp']}  `comunidad-madrid·idem_ma_enp`")
    # Riesgos
    L.append("\n## Riesgos naturales (nivel 0–5)")
    L.append(f"- Sismo: {RISK5[c['sismo']]} · ladera: {RISK5[c['ladera']]} · avenidas: {RISK5[c['avenidas']]}  `comunidad-madrid·peligrosid_*`")
    # Qué tengo cerca (Overture)
    L.append("\n## Qué tengo cerca (≤800 m)  🌍 `overture·places` (remoto)")
    NAMES={'school':'Colegios','supermarket':'Supermercados','pharmacy':'Farmacias','hospital':'Centros sanitarios',
           'restaurant':'Restaurantes','park':'Parques','bus_stop':'Paradas de bus','metro_station':'Metro'}
    for r in sorted(ov,key=lambda r:r["cerca"]):
        L.append(f"- **{NAMES.get(r['cat'],r['cat'])}:** {r['n']} en 800 m · el más cercano a **{int(r['cerca'])} m**")
    if not ov: L.append("- (sin amenities en 800 m)")
    # Aire
    if air:
        L.append(f"\n## Medio ambiente")
        L.append(f"- **Estación de calidad del aire más cercana:** {int(air['d'])} m — {air.get('title','')[:60]}  `madrid-opendata·calidad_del_aire_estaciones`")
    L.append("\n_Orientativo · cada dato con su fuente · consultado en vivo. Aire histórico (2001→hoy), ruido, tráfico, perfil de barrio (padrón) y rutas/isócronas: siguientes piezas._")
    return "\n".join(L)

if __name__=="__main__":
    addr=sys.argv[1] if len(sys.argv)>1 else "Calle de Alcalá 100, Madrid"
    print(report(addr))

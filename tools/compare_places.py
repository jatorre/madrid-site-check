#!/usr/bin/env python3
# Comparador de localizaciones: oficial (comunidad-madrid) + amenities Overture (GeoParquet remoto, sin copia).
# Consulta federada Overture-S3  X  comunidad-GCS con point-in-polygon. python3 tools/compare_places.py
import subprocess, json
CM="https://storage.googleapis.com/carto-portolan-madrid/comunidad-madrid"
OVT="s3://overturemaps-us-west-2/release/2026-05-20.0/theme=places/type=place/*.parquet"
PRE=("INSTALL httpfs;LOAD httpfs;INSTALL spatial;LOAD spatial;SET geometry_always_xy=true;"
     "CREATE SECRET ov (TYPE s3, PROVIDER config, REGION 'us-west-2');")
CATS=['school','primary_school','supermarket','pharmacy','hospital','restaurant','park']
sql=f"""
WITH munis AS (
  SELECT DSMUNICIPIO nombre, ST_Transform(geom,'EPSG:25830','EPSG:4326') g
  FROM read_parquet('{CM}/data/parquet/idem_v_municipios.parquet')
  WHERE DSMUNICIPIO IN ('GETAFE','RIVAS-VACIAMADRID','ALCALA DE HENARES','POZUELO DE ALARCON')),
ext AS (SELECT min(ST_XMin(g)) x0, max(ST_XMax(g)) x1, min(ST_YMin(g)) y0, max(ST_YMax(g)) y1 FROM munis),
poi AS (
  SELECT p.geometry geom, p.categories.primary cat
  FROM read_parquet('{OVT}') p, ext
  WHERE p.bbox.xmin BETWEEN ext.x0 AND ext.x1 AND p.bbox.ymin BETWEEN ext.y0 AND ext.y1
    AND p.categories.primary IN ({','.join("'"+c+"'" for c in CATS)}))
SELECT m.nombre, poi.cat, count(*) n
FROM poi JOIN munis m ON ST_Within(poi.geom, m.g)
GROUP BY 1,2 ORDER BY 1,2;
"""
r=subprocess.run(["duckdb","-json","-c",PRE+sql],capture_output=True,text=True)
out=r.stdout
i=out.rfind('\n[')
rows=json.loads((out[i:] if i!=-1 else out).strip() or "[]")
agg={}
for row in rows:
    agg.setdefault(row["nombre"],{}).setdefault(row["cat"],0)
    agg[row["nombre"]][row["cat"]]=row["n"]
res=[]
for nom,d in agg.items():
    res.append({"municipio":nom,"colegios":d.get('school',0)+d.get('primary_school',0),
       "supermercados":d.get('supermarket',0),"farmacias":d.get('pharmacy',0),
       "hospitales":d.get('hospital',0),"restaurantes":d.get('restaurant',0),"parques":d.get('park',0)})
print(json.dumps(res,ensure_ascii=False,indent=1))

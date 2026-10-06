"""Prépare data/*.csv pour app.py à partir de sources RÉELLES (aucune valeur aléatoire).
Fichiers attendus dans le dossier courant ou dans data_raw/ :
  iter_19_cpv2020_csv.zip · 2025_escuelas_tcja.csv · RNID-Delitos_Municipal-*.csv|.zip · RNID-Víctimas_Municipal-*.csv|.zip
Optionnels : CNCT de la SEP pour Nuevo León (cct19.csv ou cnct*.csv) · DENUE (token INEGI dans DENUE_TOKEN, ou CSV denue*.csv)
"""
import glob, os, re, sys, unicodedata, zipfile
import numpy as np, pandas as pd

os.makedirs("data", exist_ok=True)
MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]

def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().upper().strip()
    return re.sub(r"\s+", " ", s)

def find(pattern):
    hits = [h for d in (".", "data_raw") for h in glob.glob(os.path.join(d, pattern))]
    return sorted(hits)[-1] if hits else None

def read_csv_any(path, **kw):
    if path.endswith(".zip"):
        z = zipfile.ZipFile(path); name = [n for n in z.namelist() if n.lower().endswith(".csv")][0]
        src = z.open(name)
    else:
        src = path
    for enc in ("utf-8-sig", "latin1"):
        try:
            if hasattr(src, "seek"): src.seek(0)
            return pd.read_csv(src, encoding=enc, low_memory=False, **kw)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"Encodage illisible : {path}")

def dms_to_dd(v):
    if isinstance(v, (int, float)): return float(v)
    m = re.findall(r"(\d+)[°\s]+(\d+)['\s]+([\d.]+)\"?\s*([NSEWnsew]?)", str(v))
    if not m:
        try: return float(v)
        except Exception: return np.nan
    d, mi, s, h = m[0]
    dd = float(d) + float(mi) / 60 + float(s) / 3600
    return -dd if h.upper() in "SW" and h else dd

# ---------- 1. ITER 2020 : localités + municipalités ----------
p = find("iter_19*.zip")
z = zipfile.ZipFile(p)
it = pd.read_csv(z.open([n for n in z.namelist() if n.endswith("conjunto_de_datos_iter_19CSV20.csv")][0]), low_memory=False)
num = ["POBTOT", "P_15A17", "P_15A17_F", "P_15A17_M", "P15A17A", "P15A17A_F", "P15A17A_M"]
for c in num: it[c] = pd.to_numeric(it[c], errors="coerce")   # '*' = confidentiel -> NaN
def no_asiste(df, s=""):  # % des 15-17 ans qui NE fréquentent PAS l'école
    return (100 * (1 - df["P15A17A" + s] / df["P_15A17" + s])).round(1)
for s in ("", "_F", "_M"): it["no_asiste" + s] = no_asiste(it, s)

mun = it[(it.LOC == 0) & (it.MUN > 0)].copy()
loc = it[it.LATITUD.notna() & it.LONGITUD.notna()].copy()
loc["lat"], loc["lon"] = loc.LATITUD.map(dms_to_dd), loc.LONGITUD.map(dms_to_dd)
loc = loc[loc.lat.between(23, 28) & loc.lon.between(-102, -98)]
w = loc.POBTOT.fillna(1).clip(lower=1)   # centro de cada municipio ponderado por población (compatible con pandas antiguos)
g = pd.DataFrame({"MUN": loc.MUN, "w": w, "wl": loc.lat * w, "wo": loc.lon * w}).groupby("MUN").sum()
cent = pd.DataFrame({"lat": g.wl / g.w, "lon": g.wo / g.w})
mun = mun.merge(cent, left_on="MUN", right_index=True, how="left")
municipios = pd.DataFrame({"mun_cve": 19000 + mun.MUN, "municipio": mun.NOM_MUN.values, "key": mun.NOM_MUN.map(norm).values,
    "lat": mun.lat.values, "lon": mun.lon.values, "pobtot": mun.POBTOT.values, "pob_15_17": mun.P_15A17.values,
    "no_asiste_15_17_pct": mun.no_asiste.values, "no_asiste_15_17_mujeres_pct": mun.no_asiste_F.values,
    "no_asiste_15_17_hombres_pct": mun.no_asiste_M.values})
municipios.to_csv("data/municipios.csv", index=False)

loc = loc.reset_index(drop=True)
pd.DataFrame({"colonia_id": loc.index + 1, "localidad": loc.NOM_LOC, "municipio": loc.NOM_MUN, "mun_cve": 19000 + loc.MUN,
              "lat": loc.lat, "lon": loc.lon, "pob_15_17": loc.P_15A17, "no_asiste_15_17_pct": loc.no_asiste}).to_csv("data/colonias.csv", index=False)

# ---------- 2. Écoles (CCT + coordonnées CNCT si disponible) ----------
esc = read_csv_any(find("*escuelas*.csv"))
esc.columns = [c.strip() for c in esc.columns]
esc = esc.drop_duplicates("CCT").copy()          # une ligne par CCT (plusieurs tours = doublons)
esc["key"] = esc.Municipio.map(norm)
esc = esc.merge(municipios[["key", "mun_cve", "lat", "lon", "no_asiste_15_17_pct"]].rename(
    columns={"lat": "mlat", "lon": "mlon"}), on="key", how="left")
esc["lat"], esc["lon"], esc["coord_aprox"] = np.nan, np.nan, True

CCT_RE = re.compile(r"^\d{2}[A-Z]{3}\d{4}[A-Z0-9]$")
def read_cnct(path):
    """CNCT -> DataFrame(_cct,_lat,_lon). Gère le format SEP SANS en-tête (92 champs, ligne entière entre guillemets :
    champ 0 = CCT, 32 = latitude, 33 = longitude) et un CSV classique avec en-têtes."""
    import csv
    unwrap = lambda x: x[1:-1].replace('""', '"') if x.startswith('"') and x.endswith('"') else x
    with open(path, encoding="utf-8-sig", newline="") as fh:
        first = next(csv.reader([unwrap(fh.readline().rstrip("\r\n"))]))
    if CCT_RE.match(first[0].strip().upper()):
        rows = []
        with open(path, encoding="utf-8-sig", newline="") as fh:
            for line in fh:
                r = next(csv.reader([unwrap(line.rstrip("\r\n"))]))
                if len(r) > 33: rows.append((r[0].strip().upper(), r[32], r[33]))
        c = pd.DataFrame(rows, columns=["_cct", "_lat", "_lon"])
    else:
        c = read_csv_any(path); c.columns = [norm(x).lower().replace(" ", "_") for x in c.columns]
        ccol = next((x for x in c.columns if x in ("clavecct", "cct", "clave_cct", "clave_centro_trabajo", "clave_ct")), None)
        la = next((x for x in c.columns if "lat" in x), None); lo = next((x for x in c.columns if "lon" in x), None)
        if not (ccol and la and lo):
            print("CNCT : colonnes non reconnues :", list(c.columns)[:15]); return None
        c = pd.DataFrame({"_cct": c[ccol].astype(str).str.strip().str.upper(), "_lat": c[la], "_lon": c[lo]})
    c["_lat"], c["_lon"] = c._lat.map(dms_to_dd), c._lon.map(dms_to_dd)
    return c[c._lat.between(23, 28) & c._lon.between(-102, -98)].drop_duplicates("_cct").set_index("_cct")   # écarte 0,0 et autres États

cn = find("cct_nl*.csv") or find("cnct*.csv") or find("cct19*.csv") or find("cct_19*.csv")
c = read_cnct(cn) if cn else None
if c is not None:
    k = esc.CCT.astype(str).str.strip().str.upper()
    esc["lat"], esc["lon"] = k.map(c._lat), k.map(c._lon)
    esc["coord_aprox"] = esc.lat.isna()
    print(f"CNCT : {int((~esc.coord_aprox).sum())}/{len(esc)} écoles avec coordonnées réelles ({cn})")
elif not cn:
    print("CNCT absent -> écoles placées à l'approximation (centre pondéré de leur municipalité) et marquées coord_aprox=True")
rng = np.random.default_rng(1)   # jitter VISUEL uniquement pour les écoles sans coordonnées
m = esc.coord_aprox
esc.loc[m, "lat"] = esc.mlat[m] + rng.normal(0, .008, m.sum()); esc.loc[m, "lon"] = esc.mlon[m] + rng.normal(0, .008, m.sum())
esc = esc.dropna(subset=["lat", "lon"])
esc.rename(columns={"Nivel": "nivel", "Nombre_escuela": "escuela_nombre", "Municipio": "municipio", "Colonia": "colonia", "Turno": "turno"})[
    ["CCT", "escuela_nombre", "nivel", "turno", "municipio", "mun_cve", "colonia", "lat", "lon", "coord_aprox", "no_asiste_15_17_pct"]
].to_csv("data/escuelas.csv", index=False)

# ---------- 3 et 4. RNID (agrégé par municipalité × mois : valeurs réelles) ----------
def rnid(pattern, dims, out):
    d = read_csv_any(find(pattern)); d.columns = [c.strip() for c in d.columns]
    d = d[d.Clave_Ent == 19]
    L = d.melt(id_vars=["Cve. Municipio", "Municipio"] + dims, value_vars=[m_ for m_ in MESES if m_ in d.columns], var_name="mes", value_name="casos")
    L = L[L.casos.fillna(0) > 0].rename(columns={"Cve. Municipio": "mun_cve", "Municipio": "municipio", "Tipo de delito": "tipo",
                                                  "Sexo": "sexo", "Rango de edad": "edad", "Subtipo de delito": "subtipo"})
    L["casos"] = L.casos.astype(int); L["mes_n"] = L.mes.map({m_: i + 1 for i, m_ in enumerate(MESES)})
    L.groupby([c for c in L.columns if c != "casos"], as_index=False).casos.sum().to_csv(out, index=False)
    print(out, int(L.casos.sum()), "cas")
rnid("RNID-Delitos*", ["Tipo de delito", "Subtipo de delito"], "data/delitos.csv")
# Delitos priorizados (equivalente disponible en SESNSP de los "7 delitos de Palermo" + proxies REDIM).
# No existen en esta tabla: portación de armas y asociación delictuosa.
_dl = pd.read_csv("data/delitos.csv")
PRIO_TIPO = {"Extorsión", "Narcomenudeo", "Feminicidio", "Secuestro", "Privación ilegal de la libertad", "Trata de personas"}
PRIO_SUB = {"Homicidio doloso", "Tentativa de homicidio doloso", "Lesiones dolosas"}
_dl["prioritario"] = _dl.tipo.isin(PRIO_TIPO) | _dl.subtipo.isin(PRIO_SUB) | _dl.subtipo.astype(str).str.startswith("Robo de vehículo automotor")
_dl.to_csv("data/delitos.csv", index=False)
rnid("RNID-V*ctimas*", ["Tipo de delito", "Sexo", "Rango de edad"], "data/victimas.csv")

# ---------- 5. Espacios para jóvenes (DENUE) ----------
# La API busca el texto en nombre, razón social, colonia y clase: "parque" trae también "Parque Industrial".
# Por eso se guarda la CLASE DE ACTIVIDAD y se filtra por ella (INCLUIR / EXCLUIR se pueden ajustar).
TERMS = ["parque", "unidad deportiva", "deportivo", "cancha", "biblioteca", "centro comunitario", "casa de la cultura",
         "centro cultural", "juventud", "museo", "bibliotecas", "clubes deportivos"]
INCLUIR = r"parque|deportiv|biblioteca|cultur|juventud|comunitari|recreativ|acondicionamiento|museo|canch|esparcimiento"
EXCLUIR = r"comercio|alquiler|restaurante|hotel|motel|industri|inmobili|fabricaci|escuelas|educaci|venta|casas de empe"
rows = []
token = os.environ.get("DENUE_TOKEN")
dn = find("denue*.csv")
if dn:   # descarga manual del INEGI
    d = read_csv_any(dn); d.columns = [c.lower() for c in d.columns]
    rows = [dict(nombre=r.get("nom_estab"), clase=r.get("nombre_act"), municipio=r.get("municipio"), lat=r.get("latitud"), lon=r.get("longitud"), id=r.get("id"))
            for r in d.to_dict("records")]
elif token:
    import requests
    for t in TERMS:
        for start in range(1, 4001, 200):
            url = f"https://www.inegi.org.mx/app/api/denue/v1/consulta/BuscarEntidad/{requests.utils.quote(t)}/19/{start}/{start+199}/{token}"
            try:
                r = requests.get(url, timeout=60); r.raise_for_status(); js = r.json()
            except Exception as e:
                print("DENUE :", t, start, "->", str(e).replace(token, "***")); break
            if not isinstance(js, list) or not js: break
            rows += [dict(nombre=j.get("Nombre"), clase=j.get("Clase_actividad"), municipio=j.get("Ubicacion", ""),
                          lat=j.get("Latitud"), lon=j.get("Longitud"), id=j.get("Id")) for j in js]
            if len(js) < 200: break
        print(f"DENUE : '{t}' -> {len(rows)} registros acumulados")
else:
    print("DENUE : ni token (DENUE_TOKEN) ni CSV -> espacios_juveniles.csv vacío")
sp = pd.DataFrame(rows, columns=["nombre", "clase", "municipio", "lat", "lon", "id"]).drop_duplicates("id")
sp["lat"], sp["lon"] = pd.to_numeric(sp.lat, errors="coerce"), pd.to_numeric(sp.lon, errors="coerce")
sp = sp[sp.lat.between(23, 28) & sp.lon.between(-102, -98)]
cl = sp.clase.astype(str)
keep = cl.str.contains(INCLUIR, case=False, regex=True) & ~cl.str.contains(EXCLUIR, case=False, regex=True)
if len(sp):
    print("Clases conservadas:\n", cl[keep].value_counts().head(15).to_string())
    print("Clases descartadas (muestra):\n", cl[~keep].value_counts().head(8).to_string())
sp = sp[keep].assign(tipo=cl[keep])[["nombre", "tipo", "municipio", "lat", "lon"]]
sp.to_csv("data/espacios_juveniles.csv", index=False)
print("espacios :", len(sp), "| terminé")

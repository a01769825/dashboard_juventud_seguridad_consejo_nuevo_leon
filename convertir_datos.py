"""Prépare data/*.csv pour app.py à partir de sources RÉELLES (aucune valeur aléatoire).
Fichiers attendus dans le dossier courant ou dans data_raw/ :
  iter_19_cpv2020_csv.zip · 2025_escuelas_tcja.csv · RNID-Delitos_Municipal-*.csv|.zip · RNID-Víctimas_Municipal-*.csv|.zip
Optionnels : CNCT de la SEP pour Nuevo León (cct19.csv ou cnct*.csv) · DENUE (token INEGI dans DENUE_TOKEN, ou CSV denue*.csv)
Sorties (data/) : municipios · localidades · escuelas · delitos · victimas · espacios_juveniles (.csv) + meta.json (date de mise à jour)
"""
import datetime, glob, json, os, re, sys, unicodedata, zipfile
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

# ---------- Classification des écoles (capa de escuelas) ----------
# La capa conserve : secundarias + media superior técnica (marcada "transición"). Preescolar, primaria, educación especial, etc. se descartan.
# CCT = 2 chiffres d'État + 1 lettre de sostenimiento (D/E = público, P = privado) + 2 lettres de service + 4 chiffres + 1 caractère de contrôle.
TIPO_SECUNDARIA = {"ES": "General", "ST": "Técnica", "TV": "Telesecundaria"}   # lettres 4-5 de la clave
RE_MEDIA_SUP = re.compile(r"MEDIA SUPERIOR|BACHILLER|PROFESIONAL TECNICO|PREPARATORIA")
RE_TECNICA = re.compile(r"TECNIC|TECNOLOG|CBTIS|CBTA|CBTF|CBTI\b|CETIS|CONALEP|CECYT|CEBETIS|DGETI|CETMAR|CBETA")

def sostenimiento_cct(cct):
    return {"D": "Público", "E": "Público", "P": "Privado"}.get(str(cct).strip().upper()[2:3], "No determinado")

def clasificar_escuela(nivel, nombre, cct, servicio=""):
    """-> (rol_capa, tipo). rol_capa vaut None si l'école n'entre pas dans la capa."""
    n, nm, sv = norm(nivel), norm(nombre), norm(servicio)
    txt = f"{n} {sv}"
    cod = str(cct).strip().upper()[3:5]
    if cod in TIPO_SECUNDARIA or "SECUNDARIA" in txt:
        if cod in TIPO_SECUNDARIA: tipo = TIPO_SECUNDARIA[cod]
        elif "TELESECUNDARIA" in f"{txt} {nm}": tipo = "Telesecundaria"
        elif "TECNIC" in f"{txt} {nm}": tipo = "Técnica"
        elif "GENERAL" in f"{txt} {nm}": tipo = "General"
        else: tipo = "No determinado"
        return "Secundaria", tipo
    if RE_MEDIA_SUP.search(txt) and RE_TECNICA.search(f"{txt} {nm}"):
        return "Media superior técnica (transición)", "Técnica"
    return None, None

def col_like(df, *pats):
    for c in df.columns:
        if any(re.search(p, norm(c)) for p in pats): return c
    return None

# ---------- 1. ITER 2020 : localités + municipalités ----------
p = find("iter_19*.zip")
z = zipfile.ZipFile(p)
it = pd.read_csv(z.open([n for n in z.namelist() if n.endswith("conjunto_de_datos_iter_19CSV20.csv")][0]), low_memory=False)
num = ["POBTOT", "P_15A17", "P_15A17_F", "P_15A17_M", "P15A17A", "P15A17A_F", "P15A17A_M"]
POB_1214, NOA_1214 = "P_12A14", "P12A14_NOA"   # ITER 2020 : población de 12 a 14 años / de 12 a 14 años que no asiste a la escuela
tiene_1214 = {POB_1214, NOA_1214} <= set(it.columns)
if tiene_1214: num += [POB_1214, NOA_1214]
else: print(f"ITER : colonnes {POB_1214} / {NOA_1214} absentes -> pas de 12-14 ans (l'appli le documente dans Metodología)")
for c in num: it[c] = pd.to_numeric(it[c], errors="coerce")   # '*' = confidentiel -> NaN
def no_asiste(df, s=""):  # % des 15-17 ans qui NE fréquentent PAS l'école
    return (100 * (1 - df["P15A17A" + s] / df["P_15A17" + s])).round(1)
for s in ("", "_F", "_M"): it["no_asiste" + s] = no_asiste(it, s)
it["no_asisten_15_17"] = it.P_15A17 - it.P15A17A   # volumen absoluto
if tiene_1214:
    it["pob_12_14"], it["no_asisten_12_14"] = it[POB_1214], it[NOA_1214]
    it["no_asiste_12_14"] = (100 * it.no_asisten_12_14 / it.pob_12_14).round(1)
else:
    it["pob_12_14"] = it["no_asisten_12_14"] = it["no_asiste_12_14"] = np.nan

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
    "no_asiste_15_17_hombres_pct": mun.no_asiste_M.values, "no_asisten_15_17": mun.no_asisten_15_17.values,
    "pob_12_14": mun.pob_12_14.values, "no_asiste_12_14_pct": mun.no_asiste_12_14.values, "no_asisten_12_14": mun.no_asisten_12_14.values})
municipios.to_csv("data/municipios.csv", index=False)

loc = loc.reset_index(drop=True)
pd.DataFrame({"localidad_id": loc.index + 1, "localidad": loc.NOM_LOC, "municipio": loc.NOM_MUN, "mun_cve": 19000 + loc.MUN,
              "lat": loc.lat, "lon": loc.lon, "pob_15_17": loc.P_15A17, "no_asiste_15_17_pct": loc.no_asiste,
              "pob_12_14": loc.pob_12_14, "no_asiste_12_14_pct": loc.no_asiste_12_14}).to_csv("data/localidades.csv", index=False)
if os.path.exists("data/colonias.csv"): os.remove("data/colonias.csv")   # nom d'une version précédente (ces données sont des localités, pas des colonias)

# ---------- 2. Écoles : secundarias + media superior técnica (CCT + coordonnées CNCT si disponible) ----------
esc = read_csv_any(find("*escuelas*.csv"))
esc.columns = [c.strip() for c in esc.columns]
print("Directorio de escuelas, columnas:", list(esc.columns))
esc = esc.drop_duplicates("CCT").copy()          # une ligne par CCT (plusieurs tours = doublons)

col_sost = col_like(esc, r"SOSTEN", r"CONTROL", r"PUBLIC")
col_serv = col_like(esc, r"SERVICIO", r"MODALIDAD", r"^TIPO")
servicio = esc[col_serv].astype(str) if col_serv else pd.Series([""] * len(esc), index=esc.index)
cl = [clasificar_escuela(a, b, c, d) for a, b, c, d in zip(esc.Nivel, esc.Nombre_escuela, esc.CCT, servicio)]
esc["rol_capa"], esc["tipo"] = [x[0] for x in cl], [x[1] for x in cl]
esc["sostenimiento"] = esc[col_sost].astype(str) if col_sost else esc.CCT.map(sostenimiento_cct)
print(f"Sostenimiento : {'columna ' + col_sost if col_sost else 'inferido de la clave CCT (Público/Privado)'} | tipo/servicio : {'columna ' + col_serv if col_serv else 'solo clave CCT y nombre'}")
print("Niveles del directorio (conservados -> rol_capa):")
print(esc.groupby("Nivel", dropna=False).rol_capa.agg(lambda s: f"{int(s.notna().sum())} de {len(s)} conservadas").to_string())
print("Capa final:", esc.rol_capa.value_counts().to_dict(), "| tipo:", esc.tipo.value_counts().to_dict())
esc = esc[esc.rol_capa.notna()].copy()

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
    print(f"CNCT : {int((~esc.coord_aprox).sum())}/{len(esc)} écoles de la capa avec coordonnées réelles ({cn})")
elif not cn:
    print("CNCT absent -> écoles placées à l'approximation (centre pondéré de leur municipalité) et marquées coord_aprox=True")
rng = np.random.default_rng(1)   # jitter VISUEL uniquement pour les écoles sans coordonnées
m = esc.coord_aprox
esc.loc[m, "lat"] = esc.mlat[m] + rng.normal(0, .008, m.sum()); esc.loc[m, "lon"] = esc.mlon[m] + rng.normal(0, .008, m.sum())
esc = esc.dropna(subset=["lat", "lon"])
print(f"Escuelas con ubicación aproximada (capa final): {int(esc.coord_aprox.sum())} de {len(esc)}")
# Le mot "colonia" n'est volontairement pas exporté : il n'y a pas de données par colonia.
esc.rename(columns={"Nivel": "nivel", "Nombre_escuela": "escuela_nombre", "Municipio": "municipio", "Turno": "turno"})[
    ["CCT", "escuela_nombre", "rol_capa", "nivel", "tipo", "sostenimiento", "turno", "municipio", "mun_cve", "lat", "lon", "coord_aprox", "no_asiste_15_17_pct"]
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

# ---------- 5. Espacios públicos de acceso libre (DENUE) ----------
# Solo: parques, deportivos, bibliotecas, centros comunitarios y casas de cultura. Se excluyen privados, albercas, balnearios y parques acuáticos.
# La API busca el texto en nombre, razón social, colonia y clase: "parque" trae también "Parque Industrial".
# Por eso se guarda la CLASE DE ACTIVIDAD y se filtra por ella (INCLUIR / EXCLUIR se pueden ajustar mirando las tablas impresas al final).
TERMS = ["parque", "unidad deportiva", "deportivo", "biblioteca", "centro comunitario", "casa de la cultura", "centro cultural"]
INCLUIR = r"PARQUE|DEPORTIV|BIBLIOTECA|CULTUR|COMUNITARI|RECREATIV"
EXCLUIR_CLASE = (r"PRIVAD|ACUATIC|BALNEARIO|DIVERSION|TEMATIC|ACONDICIONAMIENTO|COMERCIO|ALQUILER|RESTAURANTE|HOTEL|MOTEL|INDUSTRI|INMOBILI|"
                 r"FABRICACI|ESCUELAS|EDUCACI|VENTA|CASAS DE EMPE|ESPECTACULO|PROMOTOR")
EXCLUIR_NOMBRE = r"ALBERCA|PISCINA|BALNEARIO|ACUATIC|AQUA|SPLASH|WATER ?PARK|PARQUE INDUSTRIAL|GIMNASIO|\bGYM\b|\bSPA\b|SALON|JARDIN DE EVENTOS|QUINTA"

def categoria_espacio(clase, nombre):
    t = f"{norm(clase)} {norm(nombre)}"
    if "BIBLIOTECA" in t: return "Biblioteca"
    if "CULTUR" in t: return "Casa de cultura"
    if "COMUNITARI" in t: return "Centro comunitario"
    if "DEPORTIV" in t: return "Deportivo"
    if "PARQUE" in t: return "Parque"
    return "Otro espacio"

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
sp = sp[sp.lat.between(23, 28) & sp.lon.between(-102, -98)].copy()
if len(sp):
    cl_, nm_ = sp.clase.astype(str).map(norm), sp.nombre.astype(str).map(norm)
    sp["tipo"] = [categoria_espacio(a, b) for a, b in zip(sp.clase, sp.nombre)]
    keep = (cl_.str.contains(INCLUIR, regex=True) & ~cl_.str.contains(EXCLUIR_CLASE, regex=True)
            & ~nm_.str.contains(EXCLUIR_NOMBRE, regex=True) & (sp.tipo != "Otro espacio"))
    print("Clases conservadas:\n", sp.clase[keep].value_counts().head(15).to_string())
    print("Clases descartadas (muestra):\n", sp.clase[~keep].value_counts().head(10).to_string())
    print("Espacios por tipo:\n", sp.tipo[keep].value_counts().to_string())
    sp = sp[keep]
else:
    sp["tipo"] = []
sp[["nombre", "tipo", "clase", "municipio", "lat", "lon"]].rename(columns={"clase": "clase_denue"}).to_csv("data/espacios_juveniles.csv", index=False)
print("espacios :", len(sp))

# ---------- 6. Fecha de actualización (se muestra en el pie de la app) ----------
with open("data/meta.json", "w", encoding="utf-8") as fh:
    json.dump({"fecha_actualizacion": datetime.date.today().isoformat()}, fh)
print("terminé")

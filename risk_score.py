"""Prioridad territorial RELATIVA por municipio (datos públicos) · Mapa de Entornos de Riesgo y Protección · A Tiempo.

    prioridad = 0.50 * no_asistencia_n + 0.50 * incidencia_n      (cada componente = percentil 0-1; resultado 0-100)

- no_asistencia: % de jóvenes de 15-17 años que NO asiste a la escuela (Censo 2020). No es rezago educativo (CONEVAL)
  ni abandono escolar (SEP): ver Metodología en la app.
- incidencia: delitos priorizados registrados (SESNSP, ene-ago 2026) por 100 mil habitantes. Son 8 meses SIN anualizar.
- espacios: espacios públicos de acceso libre (DENUE) por 10 mil jóvenes de 15-17 años. DECISIÓN DE MÉTODO: por defecto
  solo DESCRIBEN (peso 0). Para que vuelvan a restar (0.40 / 0.40 / -0.20) cambia ESPACIOS_RESTAN a True.
El nivel (Alta / Media / Baja) usa los cortes CORTES sobre el score 0-100: es RELATIVO (compara municipios entre sí),
no un nivel absoluto de riesgo y nunca puntúa a una persona.

BRECHA DE VICTIMIZACIÓN POR SEXO (13-17): indicador separado de la prioridad. Razón mujeres/hombres de víctimas de
13 a 17 años (SESNSP) >= UMBRAL_BRECHA con al menos MIN_VICTIMAS casos. Refleja sobre todo violencia familiar y sexual;
NO es una medida de riesgo de reclutamiento. Parámetros ajustables aquí.
"""
import re, unicodedata
import numpy as np
import pandas as pd

UMBRAL_BRECHA, MIN_VICTIMAS = 2.0, 10
CORTES = (34, 67)   # Baja < 34 <= Media < 67 <= Alta
NIVELES = ["Baja", "Media", "Alta"]

ESPACIOS_RESTAN = False   # False = los espacios solo describen (decisión por defecto); True = restan al score
PESOS_SIN_ESPACIOS = {"no_asistencia": 0.50, "incidencia": 0.50, "espacios": 0.0}
PESOS_CON_ESPACIOS = {"no_asistencia": 0.40, "incidencia": 0.40, "espacios": 0.20}
PESOS_BASE = PESOS_CON_ESPACIOS if ESPACIOS_RESTAN else PESOS_SIN_ESPACIOS

# Escenarios de sensibilidad (se comparan contra la base en la pestaña Metodología)
ESCENARIOS = {"Base": {}}
_alt = PESOS_SIN_ESPACIOS if ESPACIOS_RESTAN else PESOS_CON_ESPACIOS
ESCENARIOS[("Espacios sin peso (50/50)" if ESPACIOS_RESTAN else "Espacios restan (40/40/−20)")] = {"pesos": _alt}
ESCENARIOS["Más peso a no asistencia (60/40)"] = {"pesos": {"no_asistencia": 0.60, "incidencia": 0.40, "espacios": 0.0}}
ESCENARIOS["Más peso a incidencia (40/60)"] = {"pesos": {"no_asistencia": 0.40, "incidencia": 0.60, "espacios": 0.0}}
ESCENARIOS["Sin posesión simple"] = {"excluir_posesion_simple": True}


def _norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().upper()
    return re.sub(r"[^A-Z ]", " ", s)


def _es_posesion_simple(d):
    """True en las filas de delitos cuyo tipo/subtipo corresponde a posesión simple (narcomenudeo)."""
    txt = (d.tipo.astype(str) + " " + d.subtipo.astype(str)).map(_norm)
    return txt.str.contains("POSESION") & txt.str.contains("SIMPLE")


def resumen_posesion_simple(delitos):
    """Peso de la posesión simple dentro del narcomenudeo y dentro de los delitos priorizados (NaN si no se puede calcular)."""
    ps = _es_posesion_simple(delitos)
    narco = delitos.tipo.astype(str).map(_norm).str.contains("NARCOMENUDEO")
    prio = delitos.prioritario.astype(bool)

    def share(den):
        t = delitos.casos[den].sum()
        return float(delitos.casos[ps & den].sum() / t) if t else np.nan
    return {"narcomenudeo": share(narco), "priorizados": share(prio)}


def _espacios_por_municipio(esp, mun):
    """Asigna cada espacio a un municipio: por nombre si aparece en el texto; si no, por el centro más cercano."""
    if esp is None or esp.empty:
        return pd.Series(dtype=float)
    keys = sorted(zip(mun.key, mun.mun_cve), key=lambda t: -len(t[0]))
    out = []
    for r in esp.itertuples():
        txt = _norm(getattr(r, "municipio", ""))
        hit = next((c for k, c in keys if k and k in txt), None)
        if hit is None:
            hit = mun.mun_cve.iloc[((mun.lat - r.lat) ** 2 + (mun.lon - r.lon) ** 2).argmin()]
        out.append(hit)
    return pd.Series(out).value_counts()


def calcular_riesgo(municipios, delitos, victimas, espacios, solo_prioritarios=True, pesos=None, excluir_posesion_simple=False):
    df = municipios.copy().set_index("mun_cve")
    for col in ("no_asisten_15_17", "no_asisten_12_14", "pob_12_14", "no_asiste_12_14_pct"):   # CSV antiguos sin 12-14
        if col not in df:
            df[col] = np.nan
    d = delitos[delitos.prioritario] if solo_prioritarios else delitos
    if excluir_posesion_simple:
        d = d[~_es_posesion_simple(d)]
    df["delitos"] = d.groupby("mun_cve").casos.sum().reindex(df.index).fillna(0).astype(int)
    df["delitos_100k"] = (df.delitos / df.pobtot * 1e5).round(0)   # 8 meses (ene-ago), SIN anualizar
    df["espacios"] = _espacios_por_municipio(espacios, municipios).reindex(df.index).fillna(0).astype(int)
    df["espacios_10k_jovenes"] = (df.espacios / df.pob_15_17.replace(0, np.nan) * 1e4).fillna(0).round(1)
    hay_esp = bool(df.espacios.sum() > 0)
    df["espacios_disponibles"] = hay_esp
    df["pob_pequena"] = df.pobtot < 10000   # tasas muy inestables: interpretar con cautela

    w = dict(pesos or PESOS_BASE)
    if w["espacios"] > 0 and not hay_esp:   # sin DENUE: el peso de espacios se reparte entre los otros dos componentes
        s = w["no_asistencia"] + w["incidencia"]
        w = {"no_asistencia": w["no_asistencia"] / s, "incidencia": w["incidencia"] / s, "espacios": 0.0}
    df["espacios_en_score"] = w["espacios"] > 0

    pct = lambda s: s.rank(pct=True)   # percentil: robusto a municipios muy pequeños / atípicos
    score = w["no_asistencia"] * pct(df.no_asiste_15_17_pct.fillna(df.no_asiste_15_17_pct.median())) + w["incidencia"] * pct(df.delitos_100k)
    if w["espacios"] > 0:
        score = score - w["espacios"] * pct(df.espacios_10k_jovenes)
    lo, hi = -w["espacios"], w["no_asistencia"] + w["incidencia"]
    df["prioridad_score"] = ((score - lo) / (hi - lo) * 100).clip(0, 100).round(1)
    df["prioridad"] = pd.cut(df.prioridad_score, [-1, CORTES[0] - 1e-9, CORTES[1] - 1e-9, 101], labels=NIVELES).astype(str)

    v = victimas[victimas.edad == "13 a 17 años"]
    for sx, col in (("Mujer", "vic_13_17_mujeres"), ("Hombre", "vic_13_17_hombres")):
        df[col] = v[v.sexo == sx].groupby("mun_cve").casos.sum().reindex(df.index).fillna(0).astype(int)
    tot = df.vic_13_17_mujeres + df.vic_13_17_hombres
    razon = df.vic_13_17_mujeres / df.vic_13_17_hombres.replace(0, np.nan)
    df["razon_mujeres_hombres"] = razon.round(2)
    # sin hombres víctimas pero con mujeres víctimas la razón no existe (÷0): cuenta como brecha alta
    brecha = (razon >= UMBRAL_BRECHA) | ((df.vic_13_17_hombres == 0) & (df.vic_13_17_mujeres > 0))
    df["brecha_sexo"] = np.where(tot < MIN_VICTIMAS, "n insuficiente", np.where(brecha, "Brecha alta", "Sin brecha alta"))
    return df.reset_index()


def sensibilidad(municipios, delitos, victimas, espacios, solo_prioritarios=True):
    """Compara cada escenario de ESCENARIOS contra la base: cuántos municipios cambian de nivel y cuánto se parece el orden."""
    base = calcular_riesgo(municipios, delitos, victimas, espacios, solo_prioritarios)
    alta_base = set(base.mun_cve[base.prioridad == "Alta"])
    filas = []
    for nombre, kw in ESCENARIOS.items():
        r = calcular_riesgo(municipios, delitos, victimas, espacios, solo_prioritarios, **kw)
        alta = set(r.mun_cve[r.prioridad == "Alta"])
        filas.append({"escenario": nombre,
                      "municipios que cambian de nivel": int((r.prioridad.values != base.prioridad.values).sum()),
                      "municipios en prioridad alta": len(alta),
                      "de ellos, ya eran alta en la base": len(alta & alta_base),
                      "correlación de orden (Spearman)": round(float(base.prioridad_score.rank().corr(r.prioridad_score.rank())), 3)})
    return pd.DataFrame(filas)

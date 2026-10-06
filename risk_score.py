"""Score de riesgo TERRITORIAL por municipio con datos REALES (misma lógica que el MVP v2, adaptada a lo que existe públicamente).

    riesgo = 0.40 * rezago_educativo_n + 0.40 * incidencia_n - 0.20 * espacios_n      (cada componente = percentil 0-1)

- rezago_educativo: % de jóvenes de 15-17 años que NO asiste a la escuela (Censo 2020). Es un PROXY del abandono escolar.
- incidencia: delitos priorizados (SESNSP, ene-ago 2026) por 100 mil habitantes.
- espacios: espacios para jóvenes (DENUE) por 10 mil jóvenes de 15-17 años (factor protector). Si no hay datos DENUE,
  los pesos pasan a 0.50 / 0.50 y se indica en la tabla (espacios_disponibles = False).
El semáforo usa PERCENTILES: es RELATIVO (compara municipios entre sí), no un nivel absoluto de riesgo.

ALERTA DE GÉNERO: indicador separado del semáforo (para no esconder el riesgo de mujeres dentro de un promedio).
Con los datos públicos no hay desapariciones por municipio; se usa un proxy real: víctimas de 13 a 17 años (SESNSP),
razón mujeres/hombres >= UMBRAL_GENERO y al menos MIN_VICTIMAS casos. Ambos parámetros se pueden ajustar aquí.
"""
import re, unicodedata
import numpy as np
import pandas as pd

UMBRAL_GENERO, MIN_VICTIMAS = 2.0, 10
PESOS = {"rezago": 0.40, "incidencia": 0.40, "espacios": 0.20}
CORTES = (34, 67)   # Verde < 34 <= Amarillo < 67 <= Rojo


def _norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().upper()
    return re.sub(r"[^A-Z ]", " ", s)


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


def calcular_riesgo(municipios, delitos, victimas, espacios, solo_prioritarios=True):
    df = municipios.copy().set_index("mun_cve")
    d = delitos[delitos.prioritario] if solo_prioritarios else delitos
    df["delitos"] = d.groupby("mun_cve").casos.sum().reindex(df.index).fillna(0).astype(int)
    df["delitos_100k"] = (df.delitos / df.pobtot * 1e5).round(0)
    df["rezago_pct"] = df.no_asiste_15_17_pct
    df["espacios"] = _espacios_por_municipio(espacios, municipios).reindex(df.index).fillna(0).astype(int)
    df["espacios_10k_jovenes"] = (df.espacios / df.pob_15_17.replace(0, np.nan) * 1e4).fillna(0).round(1)
    hay_esp = bool(df.espacios.sum() > 0)
    df["espacios_disponibles"] = hay_esp
    df["pob_pequena"] = df.pobtot < 10000   # tasas muy inestables: interpretar con cautela

    w = PESOS if hay_esp else {"rezago": .5, "incidencia": .5, "espacios": 0.0}
    pct = lambda s: s.rank(pct=True)   # percentil: robusto a municipios muy pequeños / atípicos
    score = w["rezago"] * pct(df.rezago_pct.fillna(df.rezago_pct.median())) + w["incidencia"] * pct(df.delitos_100k) \
            - (w["espacios"] * pct(df.espacios_10k_jovenes) if hay_esp else 0)
    lo, hi = -w["espacios"], w["rezago"] + w["incidencia"]
    df["riesgo_score"] = ((score - lo) / (hi - lo) * 100).clip(0, 100).round(1)
    df["semaforo"] = pd.cut(df.riesgo_score, [-1, CORTES[0] - 1e-9, CORTES[1] - 1e-9, 101], labels=["Verde", "Amarillo", "Rojo"]).astype(str)

    v = victimas[victimas.edad == "13 a 17 años"]
    for sx, col in (("Mujer", "vic_13_17_mujeres"), ("Hombre", "vic_13_17_hombres")):
        df[col] = v[v.sexo == sx].groupby("mun_cve").casos.sum().reindex(df.index).fillna(0).astype(int)
    tot = df.vic_13_17_mujeres + df.vic_13_17_hombres
    razon = df.vic_13_17_mujeres / df.vic_13_17_hombres.replace(0, np.nan)
    df["razon_mujeres_hombres"] = razon.round(2)
    df["alerta_genero"] = np.where(tot < MIN_VICTIMAS, "n insuficiente", np.where(razon >= UMBRAL_GENERO, "⚠️ Sí", "No"))
    df["rezago_mujeres_pct"], df["rezago_hombres_pct"] = df.no_asiste_15_17_mujeres_pct, df.no_asiste_15_17_hombres_pct
    return df.reset_index()

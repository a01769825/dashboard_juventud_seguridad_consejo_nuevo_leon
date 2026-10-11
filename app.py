"""Mapa de Entornos de Riesgo y Protección · A Tiempo (MVP1) · componente territorial · identidad visual Consejo Nuevo León.
Datos públicos (SESNSP, Censo 2020, SEP/CNCT, DENUE). Ejecutar: streamlit run app.py
Nunca puntúa a una persona: la unidad de análisis es el municipio."""
import json, os
import pandas as pd, plotly.express as px, pydeck as pdk, streamlit as st
from risk_score import (calcular_riesgo, sensibilidad, resumen_posesion_simple, CORTES, PESOS_BASE,
                        UMBRAL_BRECHA, MIN_VICTIMAS)

VERSION = "v0.2"
# Referencias citadas en Metodología (confirmar fuente, año y ámbito -nacional o Nuevo León- antes de publicar)
REF_CONEVAL, REF_ABANDONO = "13.3 %", "8.7 %"
ORIGEN_DIRECTORIO = "Directorio de escuelas 2025 (archivo 2025_escuelas_tcja.csv) + coordenadas del CNCT de la SEP"   # completar nombre oficial

PRUNE, ANTHRACITE, AMBRE = "#5B2245", "#232A33", "#FFC20E"      # colores estimados de conl.mx: ajustar aquí
CYAN, JAUNE, ROSE, LAVANDE, LIME, TURQ = "#22E0F5", "#FFE04A", "#F7A8F0", "#A68CFF", "#A6F25C", "#00A9A5"
# Prioridad territorial relativa: escala de intensidad (coral > ámbar > gris). Sin colores de semáforo.
PRIO = {"Alta": [255, 122, 89, 190], "Media": [255, 194, 14, 190], "Baja": [138, 148, 160, 190]}
PRIOC = {"Alta": "#FF7A59", "Media": AMBRE, "Baja": "#8A94A0", "": "#999"}
ORDEN_PRIO = ["Alta", "Media", "Baja"]

st.set_page_config(page_title="Mapa de Entornos de Riesgo y Protección · A Tiempo", page_icon="🧭", layout="wide")
st.markdown(f"""<style>
@import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;800&display=swap');
html, body, [class*="css"], .stApp {{ font-family:'Poppins',sans-serif; }}
.hero {{ background:{PRUNE}; color:#fff; padding:1.8rem 2.2rem; border-radius:18px; margin-bottom:1rem; }}
.hero h1 {{ color:#fff; font-weight:800; font-size:2.1rem; margin:0 0 .2rem 0; }} .hero p {{ color:#f1e4ec; margin:0; font-size:.9rem; }}
.hero .sub {{ color:{AMBRE}; font-weight:600; font-size:1.05rem; margin:0 0 .6rem 0; }}
.tag {{ display:inline-block; background:{ANTHRACITE}; color:#fff; font-size:.7rem; padding:2px 8px; border-radius:4px; margin-bottom:.5rem; }}
.kpi {{ background:{ANTHRACITE}; border-radius:16px; padding:.9rem 1.1rem; }} .kpi .n {{ color:{AMBRE}; font-size:1.9rem; font-weight:800; line-height:1.1; }}
.kpi .l {{ color:#fff; font-size:.78rem; }}
.bar {{ height:10px; border-radius:6px; margin:.5rem 0 1.2rem 0; background:linear-gradient(90deg,{CYAN} 0 16%,{JAUNE} 16% 33%,{ROSE} 33% 50%,{LAVANDE} 50% 66%,{LIME} 66% 83%,{TURQ} 83%); }}
section[data-testid="stSidebar"] {{ background:{ANTHRACITE}; }} section[data-testid="stSidebar"] * {{ color:#fff; }} h2,h3 {{ font-weight:800; }}
</style>""", unsafe_allow_html=True)

ARCHIVOS = ["municipios", "localidades", "escuelas", "delitos", "victimas", "espacios_juveniles"]
if [n for n in ARCHIVOS if not os.path.exists(f"data/{n}.csv")]:
    st.error("Faltan archivos en data/. Ejecuta: python convertir_datos.py"); st.stop()

@st.cache_data(show_spinner=False)
def cargar():
    return {n: pd.read_csv(f"data/{n}.csv") for n in ARCHIVOS}
D = cargar()
if "no_asisten_15_17" not in D["municipios"].columns or "rol_capa" not in D["escuelas"].columns:
    st.error("Los CSV de data/ son de una versión anterior. Ejecuta de nuevo: python convertir_datos.py"); st.stop()

def _meta():
    try:
        with open("data/meta.json", encoding="utf-8") as f: return json.load(f)
    except Exception: return {}
FECHA = _meta().get("fecha_actualizacion", "s/d")

@st.cache_data(show_spinner=False)
def _calc(solo_prio):
    return calcular_riesgo(D["municipios"], D["delitos"], D["victimas"], D["espacios_juveniles"], solo_prio)

@st.cache_data(show_spinner=False)
def _sens(solo_prio):
    return sensibilidad(D["municipios"], D["delitos"], D["victimas"], D["espacios_juveniles"], solo_prio)

def _pct(x): return "s/d" if pd.isna(x) else f"{x * 100:.0f} %"

N_MUN = len(D["municipios"])
HAY_1214 = bool(D["municipios"].no_asiste_12_14_pct.notna().any())

# ---------- Barra lateral ----------
st.sidebar.header("Filtros")
munis = sorted(D["municipios"].municipio)
sel = st.sidebar.multiselect("Municipio", munis, default=munis)
solo_prio = st.sidebar.checkbox("Solo delitos priorizados (asociados a delincuencia organizada)", value=True,
    help="Afecta el conteo de delitos y la prioridad territorial. NO afecta la pestaña «Victimización de adolescentes 13–17» ni la brecha por sexo, "
         "que usan todos los delitos con víctimas de esa edad. "
         "Priorizados: extorsión, narcomenudeo, homicidio y lesiones dolosas, feminicidio, secuestro y privación de la libertad, trata y robo de vehículo. "
         "Portación de armas y asociación delictuosa no existen en la tabla municipal SESNSP.")
edad = st.sidebar.radio("Grupo de edad (capa de asistencia escolar y vista de volumen)", ["15–17 años", "12–14 años"]) if HAY_1214 else "15–17 años"
EDAD = edad.split(" ")[0]
st.sidebar.markdown("---"); st.sidebar.subheader("Capas del mapa")
c_prio = st.sidebar.checkbox("Prioridad territorial por municipio", True)
c_esc = st.sidebar.checkbox("Escuelas (secundarias y media superior técnica)", True)
c_aprox = st.sidebar.checkbox("Incluir escuelas con ubicación aproximada", False,
    help="Escuelas que no están en el CNCT. Se dibujan en gris en el centro de su municipio con un desplazamiento aleatorio solo visual: no son su ubicación real.")
c_loc = st.sidebar.checkbox(f"No asistencia escolar por localidad ({EDAD})", False)
c_esp = st.sidebar.checkbox("Espacios públicos de acceso libre (DENUE)", True)
st.sidebar.markdown("---")
st.sidebar.caption("Datos públicos: SESNSP/RNID (ene–ago 2026), INEGI Censo 2020, SEP (CNCT), INEGI DENUE. El delito se publica solo por MUNICIPIO; "
                   "por eso la unidad de análisis es el municipio, no zonas más pequeñas.")
st.sidebar.caption("🔒 La información individual nunca aparece en este mapa; vive en el Protocolo de Protección Escolar.")

R = _calc(solo_prio)
Rf = R[R.municipio.isin(sel)]; cves = set(Rf.mun_cve)
esc = D["escuelas"][D["escuelas"].mun_cve.isin(cves)]
esc_aprox, esc_real = esc[esc.coord_aprox], esc[~esc.coord_aprox]
col_pct, col_pob = ("no_asiste_15_17_pct", "pob_15_17") if EDAD == "15–17" else ("no_asiste_12_14_pct", "pob_12_14")
col_n = "no_asisten_15_17" if EDAD == "15–17" else "no_asisten_12_14"
L_ = D["localidades"]
loc = L_[L_.mun_cve.isin(cves) & (L_[col_pob] >= 30)].dropna(subset=[col_pct])
esp = D["espacios_juveniles"]
esp = esp[esp.lat.notna()] if len(esp) else esp

# ---------- Encabezado + KPI ----------
st.markdown(f"""<div class="hero"><span class="tag">Prevención del reclutamiento juvenil</span>
<h1>Mapa de Entornos de Riesgo y Protección · A Tiempo</h1>
<div class="sub">Mapa de condiciones</div>
<p>Componente territorial de A Tiempo. El tablero cubre los {N_MUN} municipios de Nuevo León; el piloto es el Área Metropolitana de Monterrey (AMM).
Indica dónde empezar y en qué orden entran los planteles, según las condiciones del entorno. Nunca puntúa a una persona.</p></div>""", unsafe_allow_html=True)
en_score = bool(R.espacios_en_score.iloc[0])
with st.expander("¿Qué estamos analizando?", expanded=True):
    st.markdown(f"""
**Pregunta que responde este tablero:** ¿en qué municipios conviene empezar y en qué orden entran los planteles, según las condiciones del entorno? Describe territorios, no personas.

- **Condición 1 · No asistencia escolar 15–17.** % de jóvenes de 15–17 años que no asiste a la escuela (Censo 2020). El proyecto considera la salida de la escuela una señal de alerta. {"También se muestra 12–14 años como capa descriptiva." if HAY_1214 else ""}
- **Condición 2 · Delitos registrados.** Delitos priorizados por 100 mil habitantes (SESNSP, ene–ago 2026, 8 meses sin anualizar): extorsión, narcomenudeo, homicidio y lesiones dolosas, feminicidio, secuestro, trata, robo de vehículo.
- **Contexto de protección · Espacios públicos de acceso libre.** Parques, deportivos, bibliotecas, centros comunitarios y casas de cultura (DENUE). {"Más espacios por joven bajan el score." if en_score else "Solo describen el entorno: no suben ni bajan la prioridad."}
- **Brecha de victimización por sexo (13–17), aparte de la prioridad.** Compara víctimas mujeres y hombres de 13–17 años. Refleja sobre todo violencia familiar y sexual; no mide riesgo de reclutamiento.

""")
n = Rf.prioridad.value_counts()
n_ins = int((Rf.brecha_sexo == "n insuficiente").sum())
kp = [(len(Rf), "municipios analizados"), (int(n.get("Alta", 0)), "prioridad territorial alta"), (int(n.get("Media", 0)), "prioridad territorial media"),
      (int(n.get("Baja", 0)), "prioridad territorial baja"), (f"{int(Rf.delitos.sum()):,}", "delitos registrados (ene–ago 2026)"),
      (int((Rf.brecha_sexo == "Brecha alta").sum()), "con brecha de victimización por sexo (13–17)")]
for c, (v, l) in zip(st.columns(len(kp)), kp):
    c.markdown(f'<div class="kpi"><div class="n">{v}</div><div class="l">{l}</div></div>', unsafe_allow_html=True)
st.caption(f"Prioridad territorial **relativa**: compara municipios entre sí, no mide un nivel absoluto. "
           f"Brecha por sexo: {n_ins} de {len(Rf)} municipios seleccionados quedan en «n insuficiente» (menos de {MIN_VICTIMAS} víctimas de 13–17 años) y no se les calcula.")
if len(Rf):
    w = lambda col: (Rf[col] * Rf.pob_15_17).sum() / Rf.pob_15_17.sum()
    a, b, c, d = st.columns(4)
    a.metric("No asiste a la escuela (15–17) — hombres", f"{w('no_asiste_15_17_hombres_pct'):.1f}%")
    b.metric("No asiste a la escuela (15–17) — mujeres", f"{w('no_asiste_15_17_mujeres_pct'):.1f}%")
    vol = f"{int(Rf.no_asisten_15_17.sum()):,}" + (f" / {int(Rf.no_asisten_12_14.sum()):,}" if HAY_1214 else "")
    c.metric("Adolescentes que no asisten (15–17" + (" / 12–14)" if HAY_1214 else ")"), vol)
    d.metric("Víctimas de 13–17 años: mujeres vs. hombres", f"{int(Rf.vic_13_17_mujeres.sum()):,} vs. {int(Rf.vic_13_17_hombres.sum()):,}")
st.markdown('<div class="bar"></div>', unsafe_allow_html=True)
if not R.espacios_disponibles.iloc[0]:
    st.info("Sin datos DENUE: la capa de espacios públicos está vacía.")
if len(esc_aprox):
    st.info(f"{len(esc_aprox)} de {len(esc)} escuelas no están en el CNCT y se ubican de forma aproximada (centro de su municipio). "
            + ("Se dibujan en gris." if c_aprox else "No se dibujan en el mapa; actívalas en «Capas del mapa» si quieres verlas."))

# ---------- Mapa ----------
def capa(df, color, r, tt):
    df = df.assign(tt=tt); return pdk.Layer("ScatterplotLayer", df, get_position="[lon, lat]", get_fill_color=color, get_radius=r, pickable=True)
def tt_escuela(e):
    s = lambda c: e[c].fillna("s/d").astype(str)
    return s("escuela_nombre") + " · " + s("rol_capa") + " · tipo: " + s("tipo") + " · " + s("sostenimiento") + " · turno: " + s("turno")
L = []
if c_prio and len(Rf):
    L.append(capa(Rf.assign(color=Rf.prioridad.map(PRIO), radio=900 + Rf.prioridad_score * 70), "color", "radio",
                  Rf.municipio + " · prioridad territorial relativa " + Rf.prioridad.str.lower() + " (score " + Rf.prioridad_score.astype(str) + ")"))
if c_loc and len(loc):
    L.append(capa(loc, [166, 140, 255, 150], 220, loc.localidad + " · " + loc[col_pct].astype(str) + "% de " + EDAD + " no asiste"))
if c_esc and len(esc_real):
    sec, ms = esc_real[esc_real.rol_capa == "Secundaria"], esc_real[esc_real.rol_capa != "Secundaria"]
    if len(sec): L.append(capa(sec, [34, 224, 245, 200], 110, tt_escuela(sec)))
    if len(ms): L.append(capa(ms, [255, 224, 74, 210], 110, tt_escuela(ms)))
if c_esc and c_aprox and len(esc_aprox):
    L.append(capa(esc_aprox, [160, 160, 160, 150], 110, tt_escuela(esc_aprox) + " · UBICACIÓN APROXIMADA"))
if c_esp and len(esp):
    L.append(capa(esp, [166, 242, 92, 220], 130, esp.nombre.astype(str) + " · " + esp.tipo.astype(str)))
st.pydeck_chart(pdk.Deck(layers=L, map_provider="carto", map_style="dark", tooltip={"text": "{tt}"},
    initial_view_state=pdk.ViewState(latitude=25.9, longitude=-100.1, zoom=7.3)), height=500)
st.caption("Prioridad territorial relativa: coral = alta · ámbar = media · gris = baja. Cian = secundarias · amarillo = media superior técnica (transición) · "
           "gris pequeño = escuela con ubicación aproximada · lila = localidades con no asistencia escolar · lima = espacios públicos de acceso libre.")

# ---------- Gráficas ----------
def sty(f): return f.update_layout(font_family="Poppins", margin=dict(l=10, r=10, t=50, b=10), legend_title_text="")
g1, g2 = st.columns(2)
if len(Rf):
    t = Rf.nlargest(15, "prioridad_score")
    g1.plotly_chart(sty(px.bar(t, x="prioridad_score", y="municipio", orientation="h", color="prioridad", color_discrete_map=PRIOC,
        category_orders={"prioridad": ORDEN_PRIO}, title="Prioridad territorial relativa (top 15 por score)").update_yaxes(categoryorder="total ascending")), width="stretch")
    g2.plotly_chart(sty(px.scatter(Rf, x="no_asiste_15_17_pct", y="delitos_100k", size="pobtot", color="prioridad", color_discrete_map=PRIOC,
        category_orders={"prioridad": ORDEN_PRIO}, hover_name="municipio", title="No asistencia escolar vs. delitos por 100 mil hab.",
        labels={"no_asiste_15_17_pct": "% 15–17 que no asiste", "delitos_100k": "Delitos por 100 mil (8 meses, sin anualizar)"})), width="stretch")

    st.subheader("Vista de volumen (cifras absolutas)")
    st.caption("El score ordena por tasas, que comparan municipios de distinto tamaño; este panel ordena por volumen. Los municipios grandes pueden quedar fuera del top 15 "
               "por tasa y aun así concentrar la mayor cantidad de adolescentes y de casos. Para decidir el orden de entrada de los planteles conviene mirar ambas vistas.")
    k1, k2 = st.columns(2)
    v1 = Rf.dropna(subset=[col_n]).nlargest(15, col_n)
    k1.plotly_chart(sty(px.bar(v1, x=col_n, y="municipio", orientation="h", color="prioridad", color_discrete_map=PRIOC, category_orders={"prioridad": ORDEN_PRIO},
        title=f"Adolescentes de {EDAD} que no asisten a la escuela (top 15 por volumen)", labels={col_n: "Adolescentes"}).update_yaxes(categoryorder="total ascending")), width="stretch")
    v2 = Rf.nlargest(15, "delitos")
    k2.plotly_chart(sty(px.bar(v2, x="delitos", y="municipio", orientation="h", color="prioridad", color_discrete_map=PRIOC, category_orders={"prioridad": ORDEN_PRIO},
        title="Delitos registrados, ene–ago 2026 (top 15 por volumen)", labels={"delitos": "Delitos"}).update_yaxes(categoryorder="total ascending")), width="stretch")

    h1, h2 = st.columns(2)
    gv = Rf.nlargest(10, "vic_13_17_mujeres" if Rf.vic_13_17_mujeres.sum() else "delitos")[["municipio", "vic_13_17_mujeres", "vic_13_17_hombres"]].melt("municipio", var_name="Sexo", value_name="Víctimas")
    gv["Sexo"] = gv.Sexo.map({"vic_13_17_mujeres": "Mujeres", "vic_13_17_hombres": "Hombres"})
    h1.plotly_chart(sty(px.bar(gv, x="municipio", y="Víctimas", color="Sexo", barmode="group", title="Victimización de adolescentes 13–17 por sexo (top 10)",
        color_discrete_sequence=[ROSE, PRUNE])), width="stretch")
    gr = Rf[Rf.pob_15_17 > 500].nlargest(10, "no_asiste_15_17_pct")[["municipio", "no_asiste_15_17_mujeres_pct", "no_asiste_15_17_hombres_pct"]].melt("municipio", var_name="Sexo", value_name="%")
    gr["Sexo"] = gr.Sexo.map({"no_asiste_15_17_mujeres_pct": "Mujeres", "no_asiste_15_17_hombres_pct": "Hombres"})
    h2.plotly_chart(sty(px.bar(gr, x="municipio", y="%", color="Sexo", barmode="group", title="15–17 años que no asisten a la escuela, por sexo (Censo 2020)",
        color_discrete_sequence=[ROSE, PRUNE])), width="stretch")

# ---------- Tablas ----------
tabs = st.tabs(["📊 Prioridad por municipio", "🚨 Delitos", "👤 Victimización de adolescentes 13–17", "🏫 Escuelas", "🏀 Espacios públicos", "📖 Metodología"])
with tabs[0]:
    ORDENES = {"Prioridad (score)": "prioridad_score", "Volumen: adolescentes 15–17 que no asisten": "no_asisten_15_17", "Volumen: delitos": "delitos"}
    orden = st.selectbox("Ordenar por", list(ORDENES))
    cols = ["municipio", "prioridad", "prioridad_score", "no_asiste_15_17_pct", "no_asisten_15_17", "no_asiste_12_14_pct", "no_asisten_12_14",
            "no_asiste_15_17_mujeres_pct", "no_asiste_15_17_hombres_pct", "delitos", "delitos_100k", "brecha_sexo", "razon_mujeres_hombres",
            "vic_13_17_mujeres", "vic_13_17_hombres", "espacios", "espacios_10k_jovenes", "pobtot", "pob_pequena"]
    if not HAY_1214: cols = [c for c in cols if "12_14" not in c]
    st.dataframe(Rf[cols].sort_values(ORDENES[orden], ascending=False), width="stretch", hide_index=True)
    st.caption("`prioridad` es relativa (alta / media / baja) y se calcula con las columnas de no asistencia escolar 15–17 y delitos por 100 mil (8 meses, sin anualizar). "
               "`pob_pequena` = municipio con menos de 10 mil habitantes: pocas denuncias bastan para disparar la tasa, interpretar con cautela. "
               "`brecha_sexo` es un indicador INDEPENDIENTE de la prioridad (mide victimización de 13–17 por sexo, sobre todo violencia familiar y sexual).")
    st.download_button("⬇️ Descargar CSV", Rf.to_csv(index=False).encode("utf-8"), "prioridad_territorial_por_municipio.csv", "text/csv")
with tabs[1]:
    d = D["delitos"][D["delitos"].mun_cve.isin(cves)]; d = d[d.prioritario] if solo_prio else d
    st.dataframe(d.groupby(["municipio", "tipo", "subtipo"], as_index=False).casos.sum().sort_values("casos", ascending=False), width="stretch", hide_index=True)
with tabs[2]:
    v = D["victimas"][D["victimas"].mun_cve.isin(cves) & (D["victimas"].edad == "13 a 17 años")]
    st.markdown("**Victimización de adolescentes de 13 a 17 años** (SESNSP). Incluye **todos** los delitos con víctimas de esa edad registrados en la tabla municipal, "
                "no solo los priorizados.")
    st.info("El filtro «Solo delitos priorizados» **no** afecta esta pestaña ni la brecha por sexo.")
    if len(v):
        tipos = v.groupby("tipo", as_index=False).casos.sum().sort_values("casos", ascending=False)
        st.markdown("**Delitos incluidos (casos en la selección):** " + "; ".join(f"{r.tipo} ({int(r.casos):,})" for r in tipos.itertuples()) + ".")
        vt = v.groupby(["tipo", "sexo"], as_index=False).casos.sum()
        vt = vt[vt.tipo.isin(tipos.tipo.head(12))]
        st.plotly_chart(sty(px.bar(vt, x="casos", y="tipo", color="sexo", barmode="group", color_discrete_map={"Mujer": ROSE, "Hombre": PRUNE},
            title="Víctimas de 13–17 años por tipo de delito y sexo (top 12 tipos)").update_yaxes(categoryorder="total ascending")), width="stretch")
    st.markdown(f"**Brecha de victimización por sexo (13–17).** Razón mujeres/hombres de víctimas de 13–17 años ≥ {UMBRAL_BRECHA:g} con al menos {MIN_VICTIMAS} casos. "
                f"Refleja sobre todo violencia familiar y delitos sexuales (ver gráfica); **no** es una medida de riesgo de reclutamiento y no entra en la prioridad territorial. "
                f"{n_ins} de {len(Rf)} municipios seleccionados quedan en «n insuficiente».")
    st.dataframe(v.groupby(["municipio", "tipo", "sexo"], as_index=False).casos.sum().sort_values("casos", ascending=False), width="stretch", hide_index=True)
with tabs[3]:
    n_sec, n_ms = int((esc.rol_capa == "Secundaria").sum()), int((esc.rol_capa != "Secundaria").sum())
    st.markdown(f"**{len(esc):,} escuelas** en la selección: {n_sec:,} secundarias y {n_ms:,} de media superior técnica (**transición**: el paso de secundaria a bachillerato). "
                f"{len(esc_aprox)} tienen ubicación aproximada (ver Metodología).")
    CE = ["CCT", "escuela_nombre", "rol_capa", "nivel", "tipo", "sostenimiento", "turno", "municipio", "coord_aprox", "no_asiste_15_17_pct"]
    st.dataframe(esc[[c for c in CE if c in esc.columns]], width="stretch", hide_index=True)
with tabs[4]:
    if len(esp):
        st.caption("Solo espacios públicos de acceso libre: parques, deportivos, bibliotecas, centros comunitarios y casas de cultura. DENUE no indica su estado ni su uso.")
        st.dataframe(esp, width="stretch", hide_index=True)
    else:
        st.write("Sin datos DENUE todavía (ver README).")
with tabs[5]:
    w_ = PESOS_BASE
    formula = (f"prioridad = {w_['no_asistencia']:.2f} × no asistencia escolar 15–17 + {w_['incidencia']:.2f} × incidencia registrada"
               + (f" − {w_['espacios']:.2f} × espacios públicos" if en_score else "") + " (cada componente como percentil 0–1; resultado 0–100)")
    ps = resumen_posesion_simple(D["delitos"])
    E = D["escuelas"]
    st.markdown(f"""
**Alcance.** El tablero mide condiciones del entorno de un territorio, no personas ni reclutamiento. Sirve para decidir dónde empezar y en qué orden entran los planteles.

**Fórmula.** {formula}.
Nivel: baja < {CORTES[0]} ≤ media < {CORTES[1]} ≤ alta. **Es relativo**: compara municipios entre sí, no mide un nivel absoluto. Ponderaciones por validar con el equipo técnico del Consejo NL.

**Espacios públicos: solo describen.** {"Restan al score (peso en la fórmula)." if en_score else "Se muestran como contexto y no entran a la fórmula: DENUE registra que el espacio existe, no si se usa, si es seguro ni si está al alcance de los adolescentes, así que no se puede afirmar que más espacios signifiquen más protección. El escenario «espacios restan» está en las sensibilidades."}

**No asistencia escolar 15–17: qué es y qué no es.**
- *Es* el % de jóvenes de 15–17 años que no asiste a la escuela el día del Censo 2020 (fotografía puntual, municipal). No existe por escuela.
- *No es* el rezago educativo de CONEVAL (referencia: {REF_CONEVAL}): ese indicador es una carencia social de toda la población de 3 años o más frente a la educación obligatoria que le correspondía por edad y generación.
- *No es* el abandono escolar en media superior (referencia: {REF_ABANDONO}): es una tasa administrativa de la SEP que mide a los alumnos inscritos que no continúan el ciclo siguiente. Un joven de 15–17 que terminó secundaria y nunca se inscribió a bachillerato cuenta en el Censo, pero no en esa tasa.
- Por eso las tres cifras no son comparables entre sí y no deben presentarse como equivalentes.

**Edades.**
- {"*12–14 años* está disponible en la capa de asistencia escolar y en la vista de volumen (Censo 2020). El score sigue usando solo 15–17 para no cambiar la fórmula; incluir 12–14 en el score es una decisión pendiente." if HAY_1214 else "*12–14 años* no está disponible en los datos cargados: las columnas del Censo 2020 (población de 12–14 y de 12–14 que no asiste) no se encontraron en el archivo ITER usado. Para incorporarlo hay que revisar el archivo."}
- *Víctimas usa 13–17* porque SESNSP publica la edad de la víctima en rangos predefinidos y el rango disponible que cubre la adolescencia es 13 a 17 años. No coincide con los cortes 12–14 y 15–17 del Censo, así que las dos capas no se suman ni se comparan una a una.

**Delitos registrados.**
- Delitos priorizados SESNSP/RNID municipal, ene–ago 2026. Sin coordenadas: el mapa muestra municipios, no puntos de delitos.
- **La tasa es de 8 meses (ene–ago), sin anualizar.** Sirve para comparar municipios entre sí; no debe compararse con tasas anuales de otras fuentes ni multiplicarse por 12/8 sin más.
- **Posesión simple.** {_pct(ps['narcomenudeo'])} del narcomenudeo y {_pct(ps['priorizados'])} del total de delitos priorizados en Nuevo León corresponde a posesión simple. Este delito se registra cuando la autoridad detecta a la persona, de modo que refleja la actividad policial más que la presencia del crimen organizado. Su efecto se prueba en la sensibilidad «Sin posesión simple».
- Municipios con menos de 10 mil habitantes: pocas denuncias bastan para disparar la tasa (`pob_pequena`).

**Brecha de victimización por sexo (13–17).** Razón mujeres/hombres de víctimas de 13–17 años ≥ {UMBRAL_BRECHA:g}, con al menos {MIN_VICTIMAS} casos. Refleja sobre todo violencia familiar y delitos sexuales; no es una lectura de riesgo de reclutamiento y es independiente de la prioridad. En esta selección, {n_ins} de {len(Rf)} municipios quedan en «n insuficiente».

**Escuelas.**
- *Origen:* {ORIGEN_DIRECTORIO}.
- *Niveles incluidos en la capa:* secundarias (general, técnica y telesecundaria) y media superior técnica, marcada como **transición**. El directorio original trae todos los niveles (preescolar, primaria, educación especial, etc.); se excluyen de la capa.
- *Campos:* nivel, tipo, sostenimiento y turno. El tipo se toma de la clave del centro de trabajo y del nombre; el sostenimiento, de la columna del directorio cuando existe y, si no, de la clave. «No determinado» significa que no se pudo inferir.
- *Ubicación aproximada:* {int(E.coord_aprox.sum())} de {len(E):,} escuelas no están en el CNCT. Se colocan en el centro de su municipio (ponderado por población) con un desplazamiento aleatorio solo visual, se marcan con `coord_aprox = True`, se dibujan en gris y solo si se activa la opción. No deben usarse para medir cercanía ni para ordenar planteles dentro de un municipio.

**Espacios públicos.** INEGI DENUE: parques, deportivos, bibliotecas, centros comunitarios y casas de cultura de acceso libre ({len(D['espacios_juveniles']):,} registros). Se excluyen establecimientos privados, albercas, balnearios y parques acuáticos. DENUE no incluye horarios, estado de conservación ni uso real.

**Límites.**
- *Falacia ecológica:* las condiciones son del municipio, no de las personas que viven en él. Nada de lo que muestra el tablero permite inferir algo sobre un adolescente concreto.
- *Los delitos registrados no son la incidencia real:* son carpetas de investigación; dependen de que alguien denuncie y de que la autoridad abra la carpeta.
- *Subregistro:* gran parte de los delitos no se denuncia, y la proporción cambia entre municipios y tipos de delito.
- *Efecto de la actividad policial:* donde hay más operativos se detectan y registran más delitos (sobre todo narcomenudeo, ver posesión simple), sin que necesariamente haya más delito.
- *Fuentes de distinto año:* Censo 2020 frente a delitos de 2026.
- *Percentiles:* garantizan que siempre haya municipios en alta y en baja aunque las diferencias absolutas sean pequeñas.
""")
    with st.expander("Sensibilidades: ¿cambia el resultado si cambian los supuestos?"):
        S = _sens(solo_prio)
        st.dataframe(S, width="stretch", hide_index=True)
        st.caption(f"Cada fila recalcula la prioridad con otros pesos o sin posesión simple y la compara con la base ({N_MUN} municipios). "
                   "Pocos cambios de nivel y una correlación cercana a 1 indican que el orden es estable frente a ese supuesto.")
    st.markdown(f"**Versión y fecha de actualización:** {VERSION} · datos procesados el {FECHA}. Fuentes: SESNSP/RNID (ene–ago 2026), INEGI Censo 2020, SEP (CNCT), INEGI DENUE.")

st.markdown("---")
st.caption(f"Prototipo funcional, datos públicos · {VERSION} · actualizado el {FECHA}")

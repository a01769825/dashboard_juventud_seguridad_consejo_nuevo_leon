"""Dashboard de Riesgo Territorial · Prevención juvenil AMM · identidad visual Consejo Nuevo León.
Datos REALES (SESNSP, Censo 2020, SEP/CNCT, DENUE). Ejecutar: streamlit run app.py"""
import os
import pandas as pd, plotly.express as px, pydeck as pdk, streamlit as st
from risk_score import calcular_riesgo, UMBRAL_GENERO, MIN_VICTIMAS

PRUNE, ANTHRACITE, AMBRE = "#5B2245", "#232A33", "#FFC20E"      # colores estimados de conl.mx: ajustar aquí
CYAN, JAUNE, ROSE, LAVANDE, LIME, TURQ = "#22E0F5", "#FFE04A", "#F7A8F0", "#A68CFF", "#A6F25C", "#00A9A5"
SEM = {"Rojo": [220, 53, 69, 190], "Amarillo": [255, 194, 14, 190], "Verde": [40, 167, 69, 190]}
SEMC = {"Rojo": "#DC3545", "Amarillo": AMBRE, "Verde": "#28A745", "": "#999"}

st.set_page_config(page_title="Factores de riesgo del reclutamiento juvenil · Nuevo León", page_icon="🧭", layout="wide")
st.markdown(f"""<style>
@import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;800&display=swap');
html, body, [class*="css"], .stApp {{ font-family:'Poppins',sans-serif; }}
.hero {{ background:{PRUNE}; color:#fff; padding:1.8rem 2.2rem; border-radius:18px; margin-bottom:1rem; }}
.hero h1 {{ color:#fff; font-weight:800; font-size:2.1rem; margin:0 0 .3rem 0; }} .hero p {{ color:#f1e4ec; margin:0; font-size:.9rem; }}
.tag {{ display:inline-block; background:{ANTHRACITE}; color:#fff; font-size:.7rem; padding:2px 8px; border-radius:4px; margin-bottom:.5rem; }}
.kpi {{ background:{ANTHRACITE}; border-radius:16px; padding:.9rem 1.1rem; }} .kpi .n {{ color:{AMBRE}; font-size:1.9rem; font-weight:800; line-height:1.1; }}
.kpi .l {{ color:#fff; font-size:.78rem; }}
.bar {{ height:10px; border-radius:6px; margin:.5rem 0 1.2rem 0; background:linear-gradient(90deg,{CYAN} 0 16%,{JAUNE} 16% 33%,{ROSE} 33% 50%,{LAVANDE} 50% 66%,{LIME} 66% 83%,{TURQ} 83%); }}
section[data-testid="stSidebar"] {{ background:{ANTHRACITE}; }} section[data-testid="stSidebar"] * {{ color:#fff; }} h2,h3 {{ font-weight:800; }}
</style>""", unsafe_allow_html=True)

if not os.path.exists("data/municipios.csv"):
    st.error("Falta la carpeta data/. Ejecuta: python convertir_datos.py"); st.stop()

@st.cache_data(show_spinner=False)
def cargar():
    return {n: pd.read_csv(f"data/{n}.csv") for n in ["municipios", "colonias", "escuelas", "delitos", "victimas", "espacios_juveniles"]}
D = cargar()

# ---------- Barra lateral ----------
st.sidebar.header("Filtros")
munis = sorted(D["municipios"].municipio)
sel = st.sidebar.multiselect("Municipio", munis, default=munis)
solo_prio = st.sidebar.checkbox("Solo delitos priorizados (asociados a delincuencia organizada)", value=True,
    help="Extorsión, narcomenudeo, homicidio y lesiones dolosas, feminicidio, secuestro y privación de la libertad, trata y robo de vehículo. "
         "Portación de armas y asociación delictuosa no existen en la tabla municipal SESNSP.")
st.sidebar.markdown("---"); st.sidebar.subheader("Capas del mapa")
c_riesgo = st.sidebar.checkbox("Riesgo por municipio (semáforo)", True)
c_esc = st.sidebar.checkbox("Escuelas", True)
c_loc = st.sidebar.checkbox("Rezago educativo por localidad (15–17 años)", False)
c_esp = st.sidebar.checkbox("Espacios para jóvenes (DENUE)", True)
st.sidebar.markdown("---")
st.sidebar.caption("Datos públicos: SESNSP/RNID (ene–ago 2026), INEGI Censo 2020, SEP (CNCT), INEGI DENUE. El delito se publica solo por MUNICIPIO; "
                   "por eso la unidad de análisis es el municipio, no la colonia.")
st.sidebar.caption("⚠️ Este tablero muestra riesgo TERRITORIAL. Deliberadamente NO incluye quién recluta dentro de la familia: es un dato sensible y no geográfico, "
                   "y debe manejarse solo a nivel de protocolo familiar/SAT, nunca en un mapa.")

R = calcular_riesgo(D["municipios"], D["delitos"], D["victimas"], D["espacios_juveniles"], solo_prio)
Rf = R[R.municipio.isin(sel)]; cves = set(Rf.mun_cve)
esc = D["escuelas"][D["escuelas"].mun_cve.isin(cves)]
loc = D["colonias"][D["colonias"].mun_cve.isin(cves) & (D["colonias"].pob_15_17 >= 30)].dropna(subset=["no_asiste_15_17_pct"])
esp = D["espacios_juveniles"]
esp = esp[esp.lat.notna()] if len(esp) else esp

# ---------- Encabezado + KPI ----------
st.markdown("""<div class="hero"><span class="tag">Prevención del reclutamiento juvenil</span>
<h1>Factores de riesgo del reclutamiento juvenil en Nuevo León</h1>
<p>Dónde se concentran, por municipio, las condiciones asociadas al reclutamiento de adolescentes: rezago educativo, exposición a la violencia
y falta de espacios protectores · Ecosistema de prevención escolar-comunitaria (AMM)</p></div>""", unsafe_allow_html=True)
with st.expander("¿Qué estamos analizando?", expanded=True):
    st.markdown("""
**Pregunta que responde este tablero:** ¿en qué municipios coinciden más los factores de riesgo asociados al reclutamiento de adolescentes, y dónde faltan factores de protección?

- **Factor de riesgo 1 · Rezago educativo.** % de jóvenes de 15–17 años que no asiste a la escuela (Censo 2020). El proyecto considera la salida de la escuela una señal de alerta.
- **Factor de riesgo 2 · Exposición a la violencia.** Delitos priorizados por 100 mil habitantes (SESNSP, ene–ago 2026): extorsión, narcomenudeo, homicidio y lesiones dolosas, feminicidio, secuestro, trata, robo de vehículo.
- **Factor de protección · Espacios para jóvenes.** Parques, deportivos, bibliotecas y centros comunitarios (DENUE). Más espacios reducen el score.
- **Alerta de género (aparte del semáforo).** Compara víctimas mujeres y hombres de 13–17 años para que el riesgo de las mujeres no quede escondido en un promedio.

""")
n = Rf.semaforo.value_counts()
kp = [(len(Rf), "municipios analizados"), (int(n.get("Rojo", 0)), "🔴 más factores de riesgo"), (int(n.get("Amarillo", 0)), "🟡 factores de riesgo medios"),
      (int(n.get("Verde", 0)), "🟢 menos factores de riesgo"), (f"{int(Rf.delitos.sum()):,}", "delitos (ene–ago 2026)"), (int((Rf.alerta_genero == "⚠️ Sí").sum()), "⚠️ alertas de género")]
for c, (v, l) in zip(st.columns(len(kp)), kp):
    c.markdown(f'<div class="kpi"><div class="n">{v}</div><div class="l">{l}</div></div>', unsafe_allow_html=True)
if len(Rf):
    w = lambda col: (Rf[col] * Rf.pob_15_17).sum() / Rf.pob_15_17.sum()
    a, b, c = st.columns(3)
    a.metric("No asiste a la escuela (15–17) — hombres", f"{w('rezago_hombres_pct'):.1f}%")
    b.metric("No asiste a la escuela (15–17) — mujeres", f"{w('rezago_mujeres_pct'):.1f}%")
    c.metric("Víctimas de 13–17 años: mujeres vs. hombres", f"{int(Rf.vic_13_17_mujeres.sum()):,} vs. {int(Rf.vic_13_17_hombres.sum()):,}")
st.markdown('<div class="bar"></div>', unsafe_allow_html=True)
if not R.espacios_disponibles.iloc[0]:
    st.info("Sin datos DENUE: el score usa solo rezago educativo e incidencia (0.50 / 0.50). Con espacios para jóvenes vuelve a 0.40 / 0.40 / −0.20.")
if len(esc) and esc.coord_aprox.any():
    st.info(f"{int(esc.coord_aprox.sum())} escuelas no están en el CNCT: se ubican de forma aproximada (centro de su municipio).")

# ---------- Mapa ----------
def capa(df, color, r, tt):
    df = df.assign(tt=tt); return pdk.Layer("ScatterplotLayer", df, get_position="[lon, lat]", get_fill_color=color, get_radius=r, pickable=True)
L = []
if c_riesgo and len(Rf):
    L.append(capa(Rf.assign(color=Rf.semaforo.map(SEM), radio=900 + Rf.riesgo_score * 70), "color", "radio",
                  Rf.municipio + " · riesgo " + Rf.riesgo_score.astype(str) + " (" + Rf.semaforo + ")"))
if c_loc and len(loc):
    L.append(capa(loc, [166, 140, 255, 150], 220, loc.localidad + " · " + loc.no_asiste_15_17_pct.astype(str) + "% de 15–17 no asiste"))
if c_esc and len(esc):
    L.append(capa(esc, [34, 224, 245, 200], 110, esc.escuela_nombre + " (" + esc.nivel + ")"))
if c_esp and len(esp):
    L.append(capa(esp, [166, 242, 92, 220], 130, esp.nombre.astype(str) + " · " + esp.tipo.astype(str)))
st.pydeck_chart(pdk.Deck(layers=L, map_provider="carto", map_style="dark", tooltip={"text": "{tt}"},
    initial_view_state=pdk.ViewState(latitude=25.9, longitude=-100.1, zoom=7.3)), height=500)
st.caption("🔴🟡🟢 semáforo relativo por municipio · cian = escuelas · lila = localidades con rezago · lima = espacios para jóvenes.")

# ---------- Gráficas ----------
def sty(f): return f.update_layout(font_family="Poppins", margin=dict(l=10, r=10, t=50, b=10), legend_title_text="")
g1, g2 = st.columns(2)
if len(Rf):
    t = Rf.nlargest(15, "riesgo_score")
    g1.plotly_chart(sty(px.bar(t, x="riesgo_score", y="municipio", orientation="h", color="semaforo", color_discrete_map=SEMC,
        title="Score de riesgo relativo (top 15)").update_yaxes(categoryorder="total ascending")), width="stretch")
    g2.plotly_chart(sty(px.scatter(Rf, x="rezago_pct", y="delitos_100k", size="pobtot", color="semaforo", color_discrete_map=SEMC, hover_name="municipio",
        title="Rezago educativo vs. delitos por 100 mil hab.", labels={"rezago_pct": "% 15–17 que no asiste", "delitos_100k": "Delitos por 100 mil"})), width="stretch")
    h1, h2 = st.columns(2)
    gv = Rf.nlargest(10, "vic_13_17_mujeres" if Rf.vic_13_17_mujeres.sum() else "delitos")[["municipio", "vic_13_17_mujeres", "vic_13_17_hombres"]].melt("municipio", var_name="Sexo", value_name="Víctimas")
    gv["Sexo"] = gv.Sexo.map({"vic_13_17_mujeres": "Mujeres", "vic_13_17_hombres": "Hombres"})
    h1.plotly_chart(sty(px.bar(gv, x="municipio", y="Víctimas", color="Sexo", barmode="group", title="Víctimas de 13–17 años por sexo (top 10)",
        color_discrete_sequence=[ROSE, PRUNE])), width="stretch")
    gr = Rf[Rf.pob_15_17 > 500].nlargest(10, "rezago_pct")[["municipio", "rezago_mujeres_pct", "rezago_hombres_pct"]].melt("municipio", var_name="Sexo", value_name="%")
    gr["Sexo"] = gr.Sexo.map({"rezago_mujeres_pct": "Mujeres", "rezago_hombres_pct": "Hombres"})
    h2.plotly_chart(sty(px.bar(gr, x="municipio", y="%", color="Sexo", barmode="group", title="15–17 años que no asisten a la escuela, por sexo (Censo 2020)",
        color_discrete_sequence=[ROSE, PRUNE])), width="stretch")

# ---------- Tablas ----------
tabs = st.tabs(["📊 Riesgo por municipio", "🚨 Delitos", "👤 Víctimas 13–17", "🏫 Escuelas", "🏀 Espacios", "📖 Metodología"])
with tabs[0]:
    cols = ["municipio", "semaforo", "riesgo_score", "alerta_genero", "razon_mujeres_hombres", "rezago_pct", "rezago_mujeres_pct", "rezago_hombres_pct",
            "delitos", "delitos_100k", "vic_13_17_mujeres", "vic_13_17_hombres", "espacios", "pobtot", "pob_pequena"]
    st.dataframe(Rf[cols].sort_values("riesgo_score", ascending=False), width="stretch", hide_index=True)
    st.caption("`pob_pequena` = municipio con menos de 10 mil habitantes: pocas denuncias bastan para disparar la tasa, interpretar con cautela. `alerta_genero` es un indicador INDEPENDIENTE del semáforo: un municipio puede estar en verde y aun así tener alerta de género, para no esconder el riesgo femenino en un promedio.")
    st.download_button("⬇️ Descargar CSV", Rf.to_csv(index=False).encode("utf-8"), "riesgo_por_municipio.csv", "text/csv")
with tabs[1]:
    d = D["delitos"][D["delitos"].mun_cve.isin(cves)]; d = d[d.prioritario] if solo_prio else d
    st.dataframe(d.groupby(["municipio", "tipo", "subtipo"], as_index=False).casos.sum().sort_values("casos", ascending=False), width="stretch", hide_index=True)
with tabs[2]:
    v = D["victimas"][D["victimas"].mun_cve.isin(cves) & (D["victimas"].edad == "13 a 17 años")]
    st.dataframe(v.groupby(["municipio", "tipo", "sexo"], as_index=False).casos.sum().sort_values("casos", ascending=False), width="stretch", hide_index=True)
with tabs[3]:
    st.dataframe(esc.drop(columns=["mun_cve"]), width="stretch", hide_index=True)
with tabs[4]:
    st.dataframe(esp, width="stretch", hide_index=True) if len(esp) else st.write("Sin datos DENUE todavía (ver README).")
with tabs[5]:
    st.markdown(f"""
**Alcance.** El tablero mide factores asociados al riesgo de reclutamiento, no el reclutamiento en sí.\n
**Fórmula.** riesgo = 0.40 × rezago educativo + 0.40 × incidencia − 0.20 × espacios para jóvenes (cada componente como percentil 0–1; resultado 0–100).
Semáforo: verde < 34 ≤ amarillo < 67 ≤ rojo. **Es relativo**: compara municipios entre sí, no mide un nivel absoluto de riesgo. Ponderaciones por validar con el equipo técnico del Consejo NL.

**Fuentes y límites.**
- *Rezago educativo*: % de 15–17 años que no asiste a la escuela (Censo 2020). Es un proxy; no es la tasa oficial de abandono, y no existe público por escuela.
- *Incidencia*: SESNSP/RNID municipal, ene–ago 2026. Sin coordenadas: el mapa muestra municipios, no puntos de delitos.
- *Víctimas 13–17*: SESNSP. Sustituye a las desapariciones, que provienen del RNPDNO (fuente distinta, no integrada aquí).
- *Alerta de género*: razón mujeres/hombres de víctimas de 13–17 años ≥ {UMBRAL_GENERO} con al menos {MIN_VICTIMAS} casos.
- *Adolescentes imputados*: INEGI (EPACOL) solo publica cifras por entidad; no se muestran por escuela.
- *Escuelas*: directorio SEP con coordenadas del CNCT. *Espacios*: INEGI DENUE (parques, deportivos, bibliotecas, centros comunitarios, casas de cultura); no incluye su estado de uso.""")
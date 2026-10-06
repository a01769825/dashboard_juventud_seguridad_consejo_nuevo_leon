# Dashboard de Riesgo Territorial (datos reales) · Consejo Nuevo León

Misma idea del MVP v2 (score + semáforo + alerta de género), ahora con datos públicos reales y la identidad visual de conl.mx.

## Estructura
```
app.py · risk_score.py · convertir_datos.py · requirements.txt
.streamlit/config.toml   # tema (colores)
data/                    # CSV ya procesados: ESTO es lo que se sube a GitHub
data_raw/                # archivos originales (RNID, ITER, escuelas, CNCT): NO se suben (.gitignore)
```

## Actualizar los datos (en tu computadora)
1. Pon en `data_raw/`: `iter_19_cpv2020_csv.zip`, `2025_escuelas_tcja.csv`, `RNID-Delitos_Municipal-*.csv|zip`, `RNID-Víctimas_Municipal-*.csv|zip`, `cct_nl.csv` (CNCT).
2. (Opcional, espacios para jóvenes) define el token DENUE en tu terminal, nunca en el código:
   `export DENUE_TOKEN=...`  (PowerShell: `$env:DENUE_TOKEN="..."`)
3. `pip install -r requirements.txt` y luego `python convertir_datos.py`
4. `streamlit run app.py` para revisar.

## Publicar (Streamlit Community Cloud)
Sube los cambios al MISMO repositorio de GitHub: la app se redespliega sola. Si no, en share.streamlit.io: *Manage app → Reboot*.
Parámetros del score: `risk_score.py` (pesos, cortes del semáforo, umbral de la alerta de género).

# Dashboard de Riesgo Territorial (datos reales) · Consejo Nuevo León

## Estructura
```
app.py · risk_score.py · convertir_datos.py · requirements.txt
.streamlit/config.toml   # tema (colores)
data/                    # CSV ya procesados: ESTO es lo que se sube a GitHub
data_raw/                # archivos originales (RNID, ITER, escuelas, CNCT): NO se suben (.gitignore)
```

define el token DENUE en terminal, nunca en el código:
   `export DENUE_TOKEN=...`  (PowerShell: `$env:DENUE_TOKEN="..."`)
3. `pip install -r requirements.txt` y luego `python convertir_datos.py`
4. `streamlit run app.py` para revisar.

## Publicar (Streamlit Community Cloud)
Subir los cambios al MISMO repositorio de GitHub: la app se redespliega sola. 
Parámetros del score: `risk_score.py` (pesos, cortes del semáforo, umbral de la alerta de género).

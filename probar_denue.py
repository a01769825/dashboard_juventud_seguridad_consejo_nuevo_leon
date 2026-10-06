"""Prueba rápida de la API DENUE. Uso (en la MISMA terminal donde definiste el token):
    $env:DENUE_TOKEN="tu_token"
    python probar_denue.py
Imprime el código HTTP y el inicio de la respuesta de cada prueba (el token se oculta)."""
import os
import requests

token = os.environ.get("DENUE_TOKEN")
print("Token definido:", "SI (%d caracteres)" % len(token) if token else "NO -> define $env:DENUE_TOKEN en esta terminal")
if not token:
    raise SystemExit

B = "https://www.inegi.org.mx/app/api/denue/v1/consulta"
pruebas = {
    "BuscarEntidad (como usa convertir_datos.py)": f"{B}/BuscarEntidad/parque/19/1/5/{token}",
    "Buscar por radio (Monterrey, 1 km)": f"{B}/Buscar/parque/25.6866,-100.3161/1000/{token}",
}
for nombre, url in pruebas.items():
    print("\n==", nombre)
    try:
        r = requests.get(url, timeout=30)
        print("HTTP", r.status_code)
        print(r.text[:400].replace(token, "***"))
    except Exception as e:
        print("Error de conexión:", str(e).replace(token, "***"))

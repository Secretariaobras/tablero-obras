"""
poblar_cache.py
───────────────
Corre SOLO la descarga de certificados y guarda el caché.
Usá este script en lugar de construir_tablero.py cuando querés
poblar el caché sin tocar el tablero.json existente.

Uso:
    python poblar_cache.py              ← solo procesa archivos nuevos/modificados
    python poblar_cache.py --forzar     ← descarga todo desde cero
"""

import sys
from leer_certificados import obtener_certificados

forzar = "--forzar" in sys.argv

print("🚀 Iniciando descarga de certificados...")
if forzar:
    print("   Modo: RECARGA COMPLETA (ignorando caché existente)\n")
else:
    print("   Modo: INCREMENTAL (solo archivos nuevos/modificados)\n")

certificados = obtener_certificados(forzar_recarga=forzar)

print(f"\n🏁 Listo. {len(certificados)} OCs en caché.")
print("   Siguiente paso: python construir_tablero.py")
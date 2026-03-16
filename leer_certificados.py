import gspread
import time
import json
import os
from googleapiclient.discovery import build
from autentificacion import credenciales

servicio_drive  = build("drive", "v3", credentials=credenciales)
cliente_sheets  = gspread.authorize(credenciales)

CARPETAS_RAIZ = [
    "1EMjGkuUr588NX4Mgq46U1iCKyXDFJrvt",
    "1vbTQLKwZQT_V7u5HKC0xUMKMm3GHOQrl",
    "1Ab95Mi_TbJOLi7EXePpI6wJ8lkolh0AC",
    "1NgoElSs76_23-6cuzkb7qhkdCJ3fVic-"
]

# ── Configuración ─────────────────────────────────────────────────────────────
ARCHIVO_CACHE       = "cache_certificados.json"
MAX_RETRIES         = 5
BACKOFF_BASE        = 2      # segundos
PAUSA_ENTRE_ARCHIVOS = 2.0   # segundos entre archivos (procesamiento secuencial)
# ─────────────────────────────────────────────────────────────────────────────


# ── Retry helper ──────────────────────────────────────────────────────────────
def con_reintentos(fn, *args, **kwargs):
    for intento in range(MAX_RETRIES):
        try:
            return fn(*args, **kwargs)
        except gspread.exceptions.APIError as e:
            codigo = e.response.status_code
            if codigo in (429, 500, 503) and intento < MAX_RETRIES - 1:
                espera = BACKOFF_BASE * (2 ** intento)
                print(f"  ⏳ [{codigo}] Reintentando en {espera:.0f}s… (intento {intento+1}/{MAX_RETRIES})")
                time.sleep(espera)
            else:
                raise
    return None


# ── Caché en disco ────────────────────────────────────────────────────────────
def cargar_cache():
    """Lee el caché del disco. Devuelve (dict_oc→info, dict_id→modified_time)."""
    if not os.path.exists(ARCHIVO_CACHE):
        return {}, {}
    try:
        with open(ARCHIVO_CACHE, "r", encoding="utf-8") as f:
            datos = json.load(f)
        return datos.get("certificados", {}), datos.get("modified_times", {})
    except Exception as e:
        print(f"  ⚠️  No se pudo leer el caché: {e}. Se descargará todo desde cero.")
        return {}, {}


def guardar_cache(certificados: dict, modified_times: dict):
    """Guarda el caché actualizado en disco."""
    with open(ARCHIVO_CACHE, "w", encoding="utf-8") as f:
        json.dump(
            {"certificados": certificados, "modified_times": modified_times},
            f, ensure_ascii=False, indent=2, default=str
        )
    print(f"  💾 Caché guardado → {ARCHIVO_CACHE}  ({len(certificados)} OCs)")


# ── Drive listing (incluye modifiedTime) ──────────────────────────────────────
def listar_sheets_en_carpeta(carpeta_id):
    archivos = []
    query    = f"'{carpeta_id}' in parents and trashed = false"
    resultado = servicio_drive.files().list(
        q=query,
        fields="files(id, name, mimeType, webViewLink, modifiedTime)"
    ).execute()

    for item in resultado.get("files", []):
        if item["mimeType"] == "application/vnd.google-apps.folder":
            archivos += listar_sheets_en_carpeta(item["id"])
        elif item["mimeType"] == "application/vnd.google-apps.spreadsheet":
            archivos.append({
                "id":           item["id"],
                "nombre":       item["name"],
                "link":         item["webViewLink"],
                "modifiedTime": item.get("modifiedTime", ""),
            })
    return archivos


# ── Utilidades ────────────────────────────────────────────────────────────────
def limpiar(val):
    v = str(val).replace("$", "").replace("%", "").replace(",", "").strip()
    return float(v) if v and v not in ("-", "") else 0.0


def _extraer_numero(titulo):
    try:
        return int(titulo.upper().replace("CER", "").strip())
    except ValueError:
        return 0


def _fetch_todas_las_filas(ss, hojas_a_leer: list) -> dict:
    if not hojas_a_leer:
        return {}
    ranges   = [f"'{h.title}'" for h in hojas_a_leer]
    response = con_reintentos(ss.values_batch_get, ranges)
    result   = {}
    for vr in response.get("valueRanges", []):
        titulo         = vr.get("range", "").split("!")[0].strip("'")
        result[titulo] = vr.get("values", [])
    return result


# ── Procesamiento de un archivo ───────────────────────────────────────────────
def procesar_archivo_completo(sheet_id, web_link):
    try:
        ss          = con_reintentos(cliente_sheets.open_by_key, sheet_id)
        todas_hojas = ss.worksheets()

        hoja_oc_obj    = next((h for h in todas_hojas if h.title == "Procesar OC"), None)
        hojas_cer_objs = sorted(
            [h for h in todas_hojas if h.title.upper().startswith("CER")],
            key=lambda h: _extraer_numero(h.title)
        )
        hojas_in_objs = sorted(
            [h for h in todas_hojas if h.title.upper().startswith("IN")],
            key=lambda h: _extraer_numero(h.title.upper().replace("IN", ""))
        )
        hojas_in_ids = {h.title.upper(): h.id for h in hojas_in_objs}

        hojas_a_leer = ([hoja_oc_obj] if hoja_oc_obj else []) + hojas_cer_objs + hojas_in_objs
        datos_batch  = _fetch_todas_las_filas(ss, hojas_a_leer)

        oc          = None
        descripcion = ""
        inspector   = ""
        if hoja_oc_obj:
            filas_oc = datos_batch.get("Procesar OC", [])
            # B2 → ID de OC
            val_b2 = filas_oc[1][1] if len(filas_oc) > 1 and len(filas_oc[1]) > 1 else None
            if val_b2:
                oc = val_b2.replace("/", "_").strip()
            # B1 → Descripción del proyecto
            descripcion = filas_oc[0][1].strip() if len(filas_oc) > 0 and len(filas_oc[0]) > 1 else ""
            # B12 → Inspector de obra
            inspector   = filas_oc[11][1].strip() if len(filas_oc) > 11 and len(filas_oc[11]) > 1 else ""

        if not oc or oc.upper().startswith("SP"):
            return None

        historial_cer       = []
        ultimo_completo_data = None

        for hoja in hojas_cer_objs:
            filas = datos_batch.get(hoja.title, [])
            if not filas:
                continue
            res = analizar_hoja_cer(filas, hoja, sheet_id, hojas_in_ids, web_link, datos_batch)
            if res["cant_items"] > 0:
                historial_cer.append(res["resumen"])
                if res["es_completo"]:
                    ultimo_completo_data = {
                        "certificado":        hoja.title,
                        "items":              res["items_detalle"],
                        "fecha_inicio":       res["fecha_inicio"],
                        "fecha_fin_estimada": res["fecha_fin_estimada"],
                    }
                else:
                    break

        if not ultimo_completo_data:
            return None

        return oc, {**ultimo_completo_data, "historial_cer": historial_cer, "link": web_link, "descripcion": descripcion, "inspector": inspector}

    except Exception as e:
        print(f"  ⚠️  Error procesando {sheet_id}: {e}")
        return None


def analizar_hoja_cer(filas, hoja, sheet_id, hojas_in_ids, web_link, datos_batch={}):
    num    = hoja.title.upper().replace("CER", "").strip()
    gid_in = hojas_in_ids.get(f"IN{num}")

    # Leer fotos de la hoja IN (col A=nombre, col B=link) — solo filas con "Foto" en nombre
    fotos = []
    filas_in = datos_batch.get(f"IN{num}", [])
    for fila in filas_in:
        if len(fila) >= 2 and "foto" in fila[0].strip().lower() and fila[1].strip():
            fotos.append({"nombre": fila[0].strip(), "link": fila[1].strip()})

    res = {
        "es_completo":        True,
        "items_detalle":      [],
        "cant_items":         0,
        "fecha_inicio":       filas[4][12].strip() if len(filas) > 4 and len(filas[4]) > 12 else "",
        "fecha_fin_estimada": filas[7][12].strip() if len(filas) > 7 and len(filas[7]) > 12 else "",
        "resumen":            {},
    }

    t_oc = t_unid_acum = t_cant = t_imp_acum = t_imp_mes = 0.0
    leyendo = False

    for f in filas:
        if len(f) > 2 and "TOTALES" in str(f[2]).upper():
            break
        if len(f) > 1 and "Items" in f[1]:
            leyendo = True
            continue

        if leyendo and len(f) >= 17 and f[2].strip() and f[1].strip():
            if f[10].strip() == "":
                res["es_completo"] = False

            res["items_detalle"].append({
                "Item": f[1], "Denominacion": f[2], "Unidad": f[3],
                "Cantidad": f[4], "Precio_Unitario": f[5], "Total": limpiar(f[6]),
                "%Inc": limpiar(f[7]), "Cantidad_Anterior": f[8], "Cantidad_en_mes": f[9],
                "Cantidad_acumulada": f[10], "Porcentaje_anterior": limpiar(f[11]),
                "Porcentaje_en_mes": limpiar(f[12]), "Porcentaje_Acumulado": limpiar(f[13]),
                "Importe_anterior": limpiar(f[14]), "Importe_en_mes": limpiar(f[15]),
                "Importe_Acumulado": limpiar(f[16]), "Link_Drive": web_link,
            })
            t_oc        += limpiar(f[6])
            t_unid_acum += limpiar(f[10])
            t_imp_mes   += limpiar(f[15])
            t_imp_acum  += limpiar(f[16])
            t_cant      += limpiar(f[4])
            res["cant_items"] += 1

    if res["cant_items"] > 0:
        res["resumen"] = {
            "certificado":        hoja.title,
            "total_oc":           t_oc,
            "total_unidad_acum":  t_unid_acum,
            "total_pct_acum": round((t_imp_acum / t_oc) * 100, 2) if t_oc > 0 else 0.0,
            "total_importe_mes":  t_imp_mes,
            "total_importe_acum": t_imp_acum,
            "fotos":    fotos,
            "link_cer": f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit#gid={hoja.id}",
            "link_in":  f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit#gid={gid_in}"
                        if gid_in else None,
        }
    return res


# ── Entry point con caché incremental ─────────────────────────────────────────
def obtener_certificados(forzar_recarga=False):
    """
    Descarga certificados con caché incremental en disco.

    - Primera ejecución : procesa todos los archivos y guarda caché.
    - Siguientes ejecuciones: solo reprocesa los archivos cuya fecha de
      modificación en Drive cambió desde la última vez.
    - forzar_recarga=True : ignora el caché y descarga todo desde cero.
    """
    cache_oc, cache_mt = ({}, {}) if forzar_recarga else cargar_cache()

    # Listar todos los archivos en Drive (solo Drive API, muy barata)
    print("📂 Listando archivos en Drive…")
    todos_los_archivos = []
    for carpeta_id in CARPETAS_RAIZ:
        todos_los_archivos += listar_sheets_en_carpeta(carpeta_id)

    print(f"   → {len(todos_los_archivos)} archivos encontrados")

    # Determinar cuáles necesitan re-procesarse
    pendientes = []
    omitidos   = 0
    for archivo in todos_los_archivos:
        aid = archivo["id"]
        if not forzar_recarga and cache_mt.get(aid) == archivo["modifiedTime"]:
            omitidos += 1          # sin cambios → usar caché
        else:
            pendientes.append(archivo)

    print(f"   → {omitidos} sin cambios (usando caché)  |  {len(pendientes)} a procesar")

    # Procesar solo los pendientes, de forma SECUENCIAL con pausa
    nuevos   = 0
    errores  = 0
    for i, archivo in enumerate(pendientes, 1):
        print(f"  [{i}/{len(pendientes)}] {archivo['nombre']}")
        datos = procesar_archivo_completo(archivo["id"], archivo["link"])

        if datos:
            oc, info = datos
            cache_oc[oc] = info
            nuevos += 1
        else:
            errores += 1

        # Guardar el modifiedTime incluso si no produjo OC (para no reprocesar)
        cache_mt[archivo["id"]] = archivo["modifiedTime"]

        # Pausa entre archivos para no superar la cuota
        if i < len(pendientes):
            time.sleep(PAUSA_ENTRE_ARCHIVOS)

    # Persistir caché actualizado
    if pendientes:
        guardar_cache(cache_oc, cache_mt)

    print(f"\n✅ Certificados listos: {len(cache_oc)} OCs  "
          f"({nuevos} nuevos/actualizados, {errores} sin resultado, {omitidos} desde caché)")

    return cache_oc
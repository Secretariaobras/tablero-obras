import gspread
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from googleapiclient.discovery import build
from autentificacion import credenciales

servicio_drive = build("drive", "v3", credentials=credenciales)
cliente_sheets = gspread.authorize(credenciales)

CARPETAS_RAIZ = [
    "1EMjGkuUr588NX4Mgq46U1iCKyXDFJrvt",
    "1vbTQLKwZQT_V7u5HKC0xUMKMm3GHOQrl",
    "1Ab95Mi_TbJOLi7EXePpI6wJ8lkolh0AC",
    "1NgoElSs76_23-6cuzkb7qhkdCJ3fVic-"
]

# ── Rate-limit config ────────────────────────────────────────────────────────
MAX_WORKERS        = 4
MAX_RETRIES        = 5
BACKOFF_BASE       = 1.5  # seconds; doubles on each retry
# ────────────────────────────────────────────────────────────────────────────

def limpiar(val):
    v = str(val).replace("$", "").replace("%", "").replace(",", "").strip()
    return float(v) if v and v not in ("-", "") else 0.0


# ── Retry helper (replaces flat sleep) ──────────────────────────────────────
def con_reintentos(fn, *args, **kwargs):
    """Call fn(*args, **kwargs) with exponential backoff on quota errors."""
    for intento in range(MAX_RETRIES):
        try:
            return fn(*args, **kwargs)
        except gspread.exceptions.APIError as e:
            if e.response.status_code in (429, 500, 503) and intento < MAX_RETRIES - 1:
                espera = BACKOFF_BASE * (2 ** intento)
                print(f"  ⏳ Cuota/error transitorio – reintentando en {espera:.1f}s…")
                time.sleep(espera)
            else:
                raise
    return None


# ── Drive listing (unchanged logic, unchanged API surface) ───────────────────
def listar_sheets_en_carpeta(carpeta_id):
    archivos = []
    query = f"'{carpeta_id}' in parents and trashed = false"
    resultado = servicio_drive.files().list(
        q=query,
        fields="files(id, name, mimeType, webViewLink)"
    ).execute()

    for item in resultado.get("files", []):
        if item["mimeType"] == "application/vnd.google-apps.folder":
            archivos += listar_sheets_en_carpeta(item["id"])
        elif item["mimeType"] == "application/vnd.google-apps.spreadsheet":
            archivos.append({
                "id":     item["id"],
                "nombre": item["name"],
                "link":   item["webViewLink"]
            })
    return archivos


# ── OPTIMISATION 1: batch-fetch ALL sheet data in a single API call ──────────
def _fetch_todas_las_filas(ss, hojas_a_leer: list) -> dict[str, list]:
    """
    Returns {sheet_title: [[row values]]} for every sheet in hojas_a_leer.
    Uses a single spreadsheets.values.batchGet call instead of N calls.
    """
    if not hojas_a_leer:
        return {}

    # gspread exposes the raw Sheets v4 client via ss.client.auth
    # We use ss.values_batch_get which maps directly to batchGet.
    ranges = [f"'{h.title}'" for h in hojas_a_leer]
    response = con_reintentos(ss.values_batch_get, ranges)

    result = {}
    for vr in response.get("valueRanges", []):
        # The range key looks like "'CER1'!A1:Z1000" – extract the sheet title
        titulo = vr.get("range", "").split("!")[0].strip("'")
        result[titulo] = vr.get("values", [])
    return result


def procesar_archivo_completo(sheet_id, web_link):
    try:
        ss = con_reintentos(cliente_sheets.open_by_key, sheet_id)
        todas_hojas = ss.worksheets()
        nombres_hojas = {h.title for h in todas_hojas}

        # 1. Obtener OC ── OPTIMISATION 2: include "Procesar OC" in batch below
        #    We defer reading B2 until after the batch fetch.
        oc = None
        hoja_oc_obj = next((h for h in todas_hojas if h.title == "Procesar OC"), None)

        # 2. Identificar hojas CER e IN
        hojas_cer_objs = sorted(
            [h for h in todas_hojas if h.title.upper().startswith("CER")],
            key=lambda h: _extraer_numero(h.title)
        )
        hojas_in_ids = {
            h.title.upper(): h.id
            for h in todas_hojas if h.title.upper().startswith("IN")
        }

        # ── BATCH FETCH: OC sheet + all CER sheets in one round-trip ─────────
        hojas_a_leer = ([hoja_oc_obj] if hoja_oc_obj else []) + hojas_cer_objs
        datos_batch = _fetch_todas_las_filas(ss, hojas_a_leer)

        # Resolve OC from cached data (no extra API call)
        if hoja_oc_obj:
            filas_oc = datos_batch.get("Procesar OC", [])
            val_b2 = filas_oc[1][1] if len(filas_oc) > 1 and len(filas_oc[1]) > 1 else None
            if val_b2:
                oc = val_b2.replace("/", "_").strip()

        if not oc or oc.upper().startswith("SP"):
            return None

        # 3. Procesar cada CER con los datos ya en memoria
        historial_cer = []
        ultimo_completo_data = None

        for hoja in hojas_cer_objs:
            filas = datos_batch.get(hoja.title, [])
            if not filas:
                continue

            res = analizar_hoja_cer(filas, hoja, sheet_id, hojas_in_ids, web_link)
            if res["cant_items"] > 0:
                historial_cer.append(res["resumen"])

                if res["es_completo"]:
                    ultimo_completo_data = {
                        "certificado":       hoja.title,
                        "items":             res["items_detalle"],
                        "fecha_inicio":      res["fecha_inicio"],
                        "fecha_fin_estimada": res["fecha_fin_estimada"],
                    }
                else:
                    break

        if not ultimo_completo_data:
            return None

        return oc, {
            **ultimo_completo_data,
            "historial_cer": historial_cer,
            "link": web_link,
        }

    except Exception as e:
        print(f"  ⚠️ Error procesando {sheet_id}: {e}")
        return None


def _extraer_numero(titulo):
    try:
        return int(titulo.upper().replace("CER", "").strip())
    except ValueError:
        return 0


def analizar_hoja_cer(filas, hoja, sheet_id, hojas_in_ids, web_link):
    """Procesa los datos de las filas de una pestaña CER en memoria (sin cambios)."""
    num    = hoja.title.upper().replace("CER", "").strip()
    gid_in = hojas_in_ids.get(f"IN{num}")

    res = {
        "es_completo":       True,
        "items_detalle":     [],
        "cant_items":        0,
        "fecha_inicio":      filas[4][12].strip() if len(filas) > 4 and len(filas[4]) > 12 else "",
        "fecha_fin_estimada": filas[7][12].strip() if len(filas) > 7 and len(filas[7]) > 12 else "",
        "resumen":           {},
    }

    t_oc = t_unid_acum = t_cant = t_imp_acum = 0.0
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

            t_oc       += limpiar(f[6])
            t_unid_acum += limpiar(f[10])
            t_imp_acum  += limpiar(f[16])
            t_cant      += limpiar(f[4])
            res["cant_items"] += 1

    if res["cant_items"] > 0:
        res["resumen"] = {
            "certificado":       hoja.title,
            "total_oc":          t_oc,
            "total_unidad_acum": t_unid_acum,
            "total_pct_acum":    round(t_unid_acum * 100 / t_cant, 2) if t_cant > 0 else 0.0,
            "total_importe_acum": t_imp_acum,
            "link_cer": f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit#gid={hoja.id}",
            "link_in":  f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit#gid={gid_in}"
                        if gid_in else None,
        }

    return res


# ── OPTIMISATION 3: parallel file processing ────────────────────────────────
def obtener_certificados():
    todos_los_archivos = []
    for carpeta_id in CARPETAS_RAIZ:
        todos_los_archivos += listar_sheets_en_carpeta(carpeta_id)

    resultado = {}

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futuros = {
            executor.submit(
                procesar_archivo_completo, archivo["id"], archivo["link"]
            ): archivo
            for archivo in todos_los_archivos
        }

        for futuro in as_completed(futuros):
            datos = futuro.result()
            if datos:
                oc, info = datos
                resultado[oc] = info

    return resultado

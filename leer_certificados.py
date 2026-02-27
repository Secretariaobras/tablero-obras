import gspread
from googleapiclient.discovery import build
from autentificacion import credenciales

servicio_drive = build("drive", "v3", credentials=credenciales)
cliente_sheets = gspread.authorize(credenciales)

CARPETAS_RAIZ = [
    "1EMjGkuUr588NX4Mgq46U1iCKyXDFJrvt",
    "1vbTQLKwZQT_V7u5HKC0xUMKMm3GHOQrl"
]


def listar_sheets_en_carpeta(carpeta_id):
    archivos = []
    resultado = servicio_drive.files().list(
        q=f"'{carpeta_id}' in parents and trashed = false",
        fields="files(id, name, mimeType, webViewLink)"
    ).execute()
    for item in resultado.get("files", []):
        if item["mimeType"] == "application/vnd.google-apps.folder":
            archivos += listar_sheets_en_carpeta(item["id"])
        elif item["mimeType"] == "application/vnd.google-apps.spreadsheet":
            archivos.append({
                "id": item["id"],
                "nombre": item["name"],
                "link": item["webViewLink"]
            })
    return archivos


def normalizar_oc(oc):
    return oc.replace("/", "_") if oc else None


def obtener_oc_del_archivo(sheet_id):
    try:
        sheet = cliente_sheets.open_by_key(sheet_id)
        hoja = sheet.worksheet("Procesar OC")
        oc = hoja.acell("B2").value
        oc = normalizar_oc(oc)
        return oc.strip() if oc else None
    except:
        return None


def obtener_ultimo_cer_completo(sheet_id):
    try:
        sheet = cliente_sheets.open_by_key(sheet_id)
        hojas = sheet.worksheets()
        hojas_cer = [h for h in hojas if h.title.upper().startswith("CER")]

        def numero_cer(hoja):
            try:
                return int(hoja.title.upper().replace("CER", "").strip())
            except:
                return 0

        hojas_cer_ordenadas = sorted(hojas_cer, key=numero_cer)
        ultimo_completo = None

        for hoja in hojas_cer_ordenadas:
            datos = hoja.get_all_values()
            tiene_vacios = False
            encontro_items = False

            for fila in datos:
                if len(fila) > 1 and "Items" in fila[1]:
                    encontro_items = True
                    continue
                if encontro_items and len(fila) > 2 and "TOTALES" in str(fila[2]).upper():
                    break
                if encontro_items and len(fila) >= 11 and fila[2].strip() != "" and fila[1] != "":
                    if fila[10].strip() == "":
                        tiene_vacios = True
                        break

            if encontro_items and not tiene_vacios:
                ultimo_completo = hoja.title
            elif encontro_items and tiene_vacios:
                break

        return ultimo_completo
    except:
        return None


def limpiar(val):
    v = str(val).replace("$", "").replace("%", "").replace(",", "").strip()
    return float(v) if v and v != "-" and v != "" else 0.0


def extraer_items_certificado(sheet_id, nombre_hoja, link_archivo):
    try:
        sheet = cliente_sheets.open_by_key(sheet_id)
        hoja = sheet.worksheet(nombre_hoja)
        filas = hoja.get_all_values()

        numero_oc          = filas[6][12].strip() if len(filas) > 6 and len(filas[6]) > 12 else "?"
        fecha_inicio       = filas[4][12].strip() if len(filas) > 4 and len(filas[4]) > 12 else ""
        fecha_fin_estimada = filas[7][12].strip() if len(filas) > 7 and len(filas[7]) > 12 else ""

        items = []
        leyendo_items = False

        for fila in filas:
            if len(fila) > 2 and "TOTALES" in str(fila[2]).upper():
                break
            if len(fila) > 1 and "Items" in fila[1]:
                leyendo_items = True
                continue
            if leyendo_items and len(fila) >= 17 and fila[2].strip() != "" and fila[1].strip() != "":
                items.append({
                    "OC": numero_oc,
                    "Certificado": nombre_hoja,
                    "Item": fila[1],
                    "Denominacion": fila[2],
                    "Unidad": fila[3],
                    "Cantidad": fila[4],
                    "Precio_Unitario": fila[5],
                    "Total": limpiar(fila[6]),
                    "%Inc": limpiar(fila[7]),
                    "Cantidad_Anterior": fila[8],
                    "Cantidad_en_mes": fila[9],
                    "Cantidad_acumulada": fila[10],
                    "Porcentaje_anterior": limpiar(fila[11]),
                    "Porcentaje_en_mes": limpiar(fila[12]),
                    "Porcentaje_Acumulado": limpiar(fila[13]),
                    "Importe_anterior": limpiar(fila[14]),
                    "Importe_en_mes": limpiar(fila[15]),
                    "Importe_Acumulado": limpiar(fila[16]),
                    "Link_Drive": link_archivo
                })

        return {
            "items": items,
            "fecha_inicio": fecha_inicio,
            "fecha_fin_estimada": fecha_fin_estimada
        }

    except Exception as e:
        print(f"  ⚠️  Error extrayendo ítems de {nombre_hoja}: {e}")
        return {"items": [], "fecha_inicio": "", "fecha_fin_estimada": ""}


def obtener_resumen_todos_los_cer(sheet_id):
    try:
        sheet = cliente_sheets.open_by_key(sheet_id)
        hojas = sheet.worksheets()
        hojas_cer = [h for h in hojas if h.title.upper().startswith("CER")]
        # Mapa de hojas IN por número
        hojas_in = {h.title.upper(): h for h in hojas if h.title.upper().startswith("IN")}

        def numero_cer(hoja):
            try:
                return int(hoja.title.upper().replace("CER", "").strip())
            except:
                return 0

        hojas_cer_ordenadas = sorted(hojas_cer, key=numero_cer)
        resumenes = []

        for hoja in hojas_cer_ordenadas:
            filas = hoja.get_all_values()
            num = hoja.title.upper().replace("CER", "").strip()

            # Links directos a las hojas
            link_cer = f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit#gid={hoja.id}"
            hoja_in  = hojas_in.get(f"IN{num}")
            link_in  = f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit#gid={hoja_in.id}" if hoja_in else None

            total_oc           = 0.0
            total_unidad_acum  = 0.0
            total_cantidad     = 0.0
            total_importe_acum = 0.0
            leyendo_items      = False
            cant_items         = 0

            for fila in filas:
                if len(fila) > 2 and "TOTALES" in str(fila[2]).upper():
                    break
                if len(fila) > 1 and "Items" in fila[1]:
                    leyendo_items = True
                    continue
                if leyendo_items and len(fila) >= 17 and fila[2].strip() != "" and fila[1].strip() != "":
                    total_oc           += limpiar(fila[6])
                    total_unidad_acum  += limpiar(fila[10])
                    total_importe_acum += limpiar(fila[16])
                    total_cantidad     += limpiar(fila[4])
                    cant_items         += 1

            if cant_items > 0:
                total_pct_acum = round(total_unidad_acum * 100 / total_cantidad, 2) if total_cantidad > 0 else 0.0
                resumenes.append({
                    "certificado":        hoja.title,
                    "total_oc":           total_oc,
                    "total_unidad_acum":  total_unidad_acum,
                    "total_pct_acum":     total_pct_acum,
                    "total_importe_acum": total_importe_acum,
                    "link_cer":           link_cer,
                    "link_in":            link_in,
                })

        return resumenes
    except Exception as e:
        print(f"  ⚠️  Error leyendo resumen de CERs: {e}")
        return []


def obtener_certificados():
    resultado = {}

    for carpeta_id in CARPETAS_RAIZ:
        archivos = listar_sheets_en_carpeta(carpeta_id)

        for archivo in archivos:
            oc = obtener_oc_del_archivo(archivo["id"])

            if not oc or oc.upper().startswith("SP"):
                continue

            ultimo_cer = obtener_ultimo_cer_completo(archivo["id"])
            if not ultimo_cer:
                continue

            resultado_cer = extraer_items_certificado(archivo["id"], ultimo_cer, archivo["link"])
            historial_cer = obtener_resumen_todos_los_cer(archivo["id"])

            resultado[oc] = {
                "certificado":        ultimo_cer,
                "items":              resultado_cer["items"],
                "fecha_inicio":       resultado_cer["fecha_inicio"],
                "fecha_fin_estimada": resultado_cer["fecha_fin_estimada"],
                "historial_cer":      historial_cer,
                "link":               archivo["link"]
            }

    return resultado
    resultado = {}

    for carpeta_id in CARPETAS_RAIZ:
        archivos = listar_sheets_en_carpeta(carpeta_id)

        for archivo in archivos:
            oc = obtener_oc_del_archivo(archivo["id"])

            if not oc or oc.upper().startswith("SP"):
                continue

            ultimo_cer = obtener_ultimo_cer_completo(archivo["id"])
            if not ultimo_cer:
                continue

            resultado_cer = extraer_items_certificado(archivo["id"], ultimo_cer, archivo["link"])
            historial_cer = obtener_resumen_todos_los_cer(archivo["id"])

            resultado[oc] = {
                "certificado":        ultimo_cer,
                "items":              resultado_cer["items"],
                "fecha_inicio":       resultado_cer["fecha_inicio"],
                "fecha_fin_estimada": resultado_cer["fecha_fin_estimada"],
                "historial_cer":      historial_cer,
                "link":               archivo["link"]
            }

    return resultado
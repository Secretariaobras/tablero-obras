import gspread
from googleapiclient.discovery import build
from autentificacion import credenciales

# --- Clientes ---
servicio_drive = build("drive", "v3", credentials=credenciales)
cliente_sheets = gspread.authorize(credenciales)

CARPETAS_RAIZ = [
    "1EMjGkuUr588NX4Mgq46U1iCKyXDFJrvt",
    "1vbTQLKwZQT_V7u5HKC0xUMKMm3GHOQrl"
]


def listar_sheets_en_carpeta(carpeta_id):
    """Recorre carpeta y subcarpetas devolviendo todos los Google Sheets."""
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
    """Lee la celda B2 de la hoja 'Procesar OC' para obtener el número de OC."""
    try:
        sheet = cliente_sheets.open_by_key(sheet_id)
        hoja = sheet.worksheet("Procesar OC")
        oc = hoja.acell("B2").value
        oc = normalizar_oc(oc)
        return oc.strip() if oc else None
    except Exception as e:
        print(f"  ⚠️  No se pudo leer 'Procesar OC' en {sheet_id}: {e}")
        return None

def obtener_ultimo_cer_completo(sheet_id):
    """
    Busca todas las hojas CERx, verifica cual es el último completo
    (columna K sin vacíos en los ítems) y devuelve su nombre.
    """
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

    except Exception as e:
        print(f"  ⚠️  Error buscando CERs en {sheet_id}: {e}")
        return None

def extraer_items_certificado(sheet_id, nombre_hoja, link_archivo):
    """Extrae los ítems del certificado indicado."""
    try:
        sheet = cliente_sheets.open_by_key(sheet_id)
        hoja = sheet.worksheet(nombre_hoja)
        filas = hoja.get_all_values()

        numero_oc = filas[6][12].strip() if len(filas) > 6 and len(filas[6]) > 12 else "?"

        items = []
        leyendo_items = False

        for fila in filas:
            if len(fila) > 2 and "TOTALES" in str(fila[2]).upper():
                break

            if len(fila) > 1 and "Items" in fila[1]:
                leyendo_items = True
                continue

            if leyendo_items and len(fila) >= 17 and fila[2].strip() != "" and fila[1].strip() != "":
                def limpiar(val):
                    v = val.replace("$", "").replace("%", "").replace(",", "").strip()
                    return float(v) if v and v != "-" else 0.0

                items.append({
                    "OC": numero_oc,
                    "Certificado": nombre_hoja,
                    "Item": fila[1],
                    "Denominacion": fila[2],
                    "Unidad": fila[3],
                    "Cantidad" : fila[4],
                    "Precio_Unitario" : fila[5],
                    "Total" : limpiar(fila[6]),
                    "%Inc" : limpiar(fila[7]),
                    #Cantidad ejecutada
                    "Cantidad_Anterior" : fila[8],
                    "Cantidad_en_mes" : fila[9],
                    "Cantidad_acumulada" : fila[10],
                    #% ejecutado
                    "Porcentaje_anterior" : limpiar(fila[11]),
                    "Porcentaje_en_mes" : limpiar(fila[12]),
                    "Porcentaje_Acumulado" : limpiar(fila[13]),
                    #Importe
                    "Importe_anterior": limpiar(fila[14]),
                    "Importe_en_mes": limpiar(fila[15]),
                    "Importe_Acumulado": limpiar(fila[16]),
                    "Link_Drive": link_archivo
                })

        return items

    except Exception as e:
        print(f"  ⚠️  Error extrayendo ítems de {nombre_hoja} en {sheet_id}: {e}")
        return []

def obtener_certificados():
    """
    Recorre todas las carpetas, lee cada archivo,
    y devuelve un dict { OC: { certificado, items, link } }
    """
    resultado = {}

    for carpeta_id in CARPETAS_RAIZ:
        print(f"\n📂 Recorriendo carpeta: {carpeta_id}")
        archivos = listar_sheets_en_carpeta(carpeta_id)
        print(f"   {len(archivos)} archivo(s) encontrado(s)")

        for archivo in archivos:
            print(f"\n  📄 {archivo['nombre']}")

            oc = obtener_oc_del_archivo(archivo["id"])

            if not oc:
                print(f"  ⏭️  Sin OC, salteando")
                continue

            if oc.upper().startswith("SP"):
                print(f"  ⏭️  OC {oc} empieza con SP, salteando")
                continue

            print(f"  🔑 OC: {oc}")

            ultimo_cer = obtener_ultimo_cer_completo(archivo["id"])

            if not ultimo_cer:
                print(f"  ⚠️  No se encontró certificado completo")
                continue

            print(f"  ✅ Último CER completo: {ultimo_cer}")

            items = extraer_items_certificado(archivo["id"], ultimo_cer, archivo["link"])
            print(f"  📋 {len(items)} ítems extraídos")

            resultado[oc] = {
                "certificado": ultimo_cer,
                "items": items,
                "link": archivo["link"]
            }

    return resultado



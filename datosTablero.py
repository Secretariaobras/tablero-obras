import gspread
import time
from autentificacion import credenciales
import pandas as pd

cliente_sheets = gspread.authorize(credenciales)
ID_TABLERO = "14zgEM2DLgK92DLNE8vn7SUGTWi4qd1L_LxzdtFcCcO0"

# ── Retry config ─────────────────────────────────────────────────────────────
MAX_RETRIES  = 5
BACKOFF_BASE = 2  # segundos; se duplica en cada reintento
# ─────────────────────────────────────────────────────────────────────────────

def con_reintentos(fn, *args, **kwargs):
    """Llama a fn(*args, **kwargs) con backoff exponencial si hay error de cuota."""
    for intento in range(MAX_RETRIES):
        try:
            return fn(*args, **kwargs)
        except gspread.exceptions.APIError as e:
            codigo = e.response.status_code
            if codigo in (429, 500, 503) and intento < MAX_RETRIES - 1:
                espera = BACKOFF_BASE * (2 ** intento)
                print(f"  ⏳ [{codigo}] Cuota/error transitorio – reintentando en {espera:.0f}s… (intento {intento + 1}/{MAX_RETRIES})")
                time.sleep(espera)
            else:
                raise
    return None


def limpiar_moneda(columna):
    return (
        columna.astype(str)
        .str.replace("$", "", regex=False)
        .str.replace(",", "", regex=False)
        .str.strip()
        .replace("", "0")
        .replace("nan", "0")
        .astype(float)
    )


def obtener_datos_tablero():
    tablero = con_reintentos(cliente_sheets.open_by_key, ID_TABLERO)

    df_suministro  = pd.DataFrame(con_reintentos(tablero.worksheet("dato_suministro").get_all_records))
    df_pagos       = pd.DataFrame(con_reintentos(tablero.worksheet("dato_pagos").get_all_records))
    df_presupuesto = pd.DataFrame(con_reintentos(tablero.worksheet("dato_presupuesto").get_all_records))

    col_monto       = df_pagos.columns[13]
    col_id          = df_pagos.columns[3]
    col_orden       = df_pagos.columns[14]
    col_estado_pago = df_pagos.columns[22]
    col_estado_z    = df_pagos.columns[25]

    df_pagos[col_monto] = limpiar_moneda(df_pagos[col_monto])

    df_presupuesto_limpio = df_presupuesto[df_presupuesto["Cat Programatica"] != ""].copy()
    df_resultado = pd.merge(df_presupuesto_limpio, df_suministro, left_on="Cat Programatica", right_on="OBR")

    df_resultado["Monto comprometido"] = limpiar_moneda(df_resultado["Monto comprometido"])
    df_resultado["Monto adjudicado"]   = limpiar_moneda(df_resultado["Monto adjudicado"])

    df_pagos_ordenado  = df_pagos.sort_values(by=[col_id, col_orden], ascending=[True, True])
    dict_total_pagado  = df_pagos[df_pagos[col_estado_pago] == "PAGO"].groupby(col_id)[col_monto].sum().to_dict()
    dict_ultimo_estado = df_pagos_ordenado.groupby(col_id)[col_estado_z].last().to_dict()

    return df_resultado, df_suministro, df_pagos, dict_total_pagado, dict_ultimo_estado
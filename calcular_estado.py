import pandas as pd
from datetime import date


def calcular_estado(oc, porcentaje, adjudicado, df_suministro, df_pagos):
    if not oc or oc == "":
        return ""

    hoy = date.today()

    # --- Columnas de df_suministro ---
    col_su_id      = df_suministro.columns[0]   # A - ID UNICO
    col_su_fecha_oc = df_suministro.columns[2]  # C - Fecha OC
    col_su_fecha_sp = df_suministro.columns[4]  # E - Fecha SP
    col_su_V       = df_suministro.columns[21]  # V - Fecha actualizacion
    col_su_W       = df_suministro.columns[22]  # W - Oficina
    col_su_X       = df_suministro.columns[23]  # X - Estado

    # --- Columnas de df_pagos ---
    col_pago_id     = df_pagos.columns[3]       # D - ID OC
    col_pago_orden  = df_pagos.columns[14]      # O - Fecha ordenamiento
    col_pago_status = df_pagos.columns[22]      # W - Estado
    col_pago_monto  = df_pagos.columns[13]      # N - Monto
    col_pago_Z      = df_pagos.columns[25]      # Z - Descripcion estado
    col_pago_T      = df_pagos.columns[19]      # T - Fecha estado
    col_pago_fecha  = df_pagos.columns[23]      # X - Fecha pago

    def to_date(val):
        if val is None or val == 0 or val == "":
            return None
        try:
            return pd.to_datetime(val, dayfirst=True).date()
        except:
            return None

    def dias_entre(fecha_inicio, fecha_fin=None):
        if fecha_fin is None:
            fecha_fin = hoy
        if fecha_inicio is None:
            return "?"
        try:
            return (fecha_fin - fecha_inicio).days
        except:
            return "?"

    fila_su = df_suministro[df_suministro[col_su_id] == oc]
    if fila_su.empty:
        fecha_sp = fecha_oc = col_W = col_X = col_V = None
    else:
        fila_su = fila_su.iloc[0]
        fecha_sp = to_date(fila_su[col_su_fecha_sp])
        fecha_oc = to_date(fila_su[col_su_fecha_oc])
        col_W    = fila_su[col_su_W]
        col_X    = fila_su[col_su_X]
        col_V    = to_date(fila_su[col_su_V])

    pagos_oc = df_pagos[df_pagos[col_pago_id] == oc].copy()
    hay_pagos = len(pagos_oc) > 0
    es_finalizado = porcentaje >= 1

    # ===========================================
    # RAMA 1: Finalizado
    # ===========================================
    if es_finalizado:
        dias_sp_oc = dias_entre(fecha_sp, fecha_oc)

        pagos_realizados = pagos_oc[pagos_oc[col_pago_status] == "PAGO"].copy()
        pagos_realizados[col_pago_fecha] = pagos_realizados[col_pago_fecha].apply(to_date)
        max_fecha_pago = pagos_realizados[col_pago_fecha].max()
        dias_oc_fin = dias_entre(fecha_oc, max_fecha_pago)
        cant_pagos = len(pagos_realizados)

        texto = (
            f"Finalizado. Desde la SP hasta la OC se demoró {dias_sp_oc} días. "
            f"Para finalizar de pagar se demoró {dias_oc_fin} días. "
            f"Se realizaron {cant_pagos} pagos:\n"
        )

        pagos_ord = pagos_realizados.sort_values(by=col_pago_fecha)
        lineas = []
        for i, (_, pago) in enumerate(pagos_ord.iterrows(), 1):
            f = pago[col_pago_fecha]
            fecha_str = f.strftime("%d/%m/%Y") if f else "?"
            pct = (pago[col_pago_monto] / adjudicado * 100) if adjudicado > 0 else 0
            lineas.append(f"  -{i}° pago: {fecha_str} + {pct:.0f}%")

        return texto + "\n".join(lineas)

    # ===========================================
    # RAMA 2: Hay pagos pero no finalizado
    # ===========================================
    elif hay_pagos:
        pagos_oc[col_pago_orden] = pagos_oc[col_pago_orden].apply(to_date)
        pagos_ord = pagos_oc.sort_values(by=col_pago_orden, ascending=False)
        ultimo = pagos_ord.iloc[0]

        ultimo_status = ultimo[col_pago_status]
        fecha_pago    = to_date(ultimo[col_pago_fecha])
        z_val         = ultimo[col_pago_Z]
        t_val         = to_date(ultimo[col_pago_T])

        if ultimo_status == "PAGO":
            fecha_str = fecha_pago.strftime("%d/%m/%Y") if fecha_pago else "?"
            return f"En Ejecución, último pago registrado el {fecha_str}"
        else:
            dias_t = dias_entre(t_val)
            return f"En Ejecución / Pendiente de Pago: {z_val} desde hace {dias_t} días"

    # ===========================================
    # RAMA 3: Sin pagos
    # ===========================================
    else:
        if not fecha_oc:
            dias_sp = dias_entre(fecha_sp)
            dias_v  = dias_entre(col_V)
            return (
                f"En gestión desde hace {dias_sp} días, "
                f"se encuentra en {col_W}-{col_X} desde hace {dias_v} días"
            )
        else:
            dias_sp = dias_entre(fecha_sp)
            return f"En Gestión de Compra: {col_W} {col_X} desde hace {dias_sp} días"


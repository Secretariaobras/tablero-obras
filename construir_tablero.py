from datosTablero import obtener_datos_tablero
from leer_certificados import obtener_certificados
from calcular_estado import calcular_estado
import json

def construir_tablero():
    df_resultado, df_suministro, df_pagos, dict_total_pagado, dict_ultimo_estado, dict_redeterminaciones= obtener_datos_tablero()
    certificados = obtener_certificados()

    tablero = []

    for cat, grupo in df_resultado.groupby("Cat Programatica"):
        proyecto = {
            "cat_programatica": cat,
            "nombre_proyecto":  grupo.iloc[0]["Nombre Proyecto"],
            "presupuesto":      grupo.iloc[0]["Presupuesto"],
            "ocs": []
        }

        for _, row in grupo.iterrows():
            oc         = row["ID UNICO"]
            adjudicado = row["Monto adjudicado"]
            pago       = dict_total_pagado.get(oc, 0)
            redeterminacion = dict_redeterminaciones.get(oc,0)
            plazo = int(row.get("plazo_oc_sp", 0))
            porcentaje = (pago / adjudicado) if adjudicado > 0 else 0
            estado     = calcular_estado(oc, porcentaje, adjudicado, df_suministro, df_pagos)
            datos_cer  = certificados.get(oc)

            proyecto["ocs"].append({
                "oc":                 oc,
                "proveedor":          row["Proveedor"],
                "comprometido":       row["Monto comprometido"],
                "adjudicado":         adjudicado,
                "pagado":             pago,
                "redeterminado":      redeterminacion,
                "porcentaje":         porcentaje,
                "estado":             estado,
                "Plazo entre OC y SP":plazo,
                "certificado":        datos_cer["certificado"]        if datos_cer else None,
                "fecha_inicio":       datos_cer["fecha_inicio"]       if datos_cer else "",
                "fecha_fin_estimada": datos_cer["fecha_fin_estimada"] if datos_cer else "",
                "historial_cer":      datos_cer["historial_cer"]      if datos_cer else [],
                "link_certificado":   datos_cer["link"]               if datos_cer else None,
                "items":              datos_cer["items"]              if datos_cer else []
            })

        tablero.append(proyecto)

    return tablero


if __name__ == "__main__":
    tablero = construir_tablero()

    with open("tablero.json", "w", encoding="utf-8") as f:
        json.dump(tablero, f, ensure_ascii=False, indent=2, default=str)

    print(f"✅ Tablero construido: {len(tablero)} proyectos → tablero.json")
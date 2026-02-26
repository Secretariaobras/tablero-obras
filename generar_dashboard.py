import json
import plotly.graph_objects as go
import plotly.io as pio
import os

# --- Cargamos el tablero.json ---
with open("tablero.json", "r", encoding="utf-8") as f:
    tablero = json.load(f)

# Carpeta donde se guardan los HTML
os.makedirs("dashboards", exist_ok=True)


# =============================================
# HELPERS
# =============================================

def clasificar_estado(ocs):
    porcentajes = [oc["porcentaje"] for oc in ocs if oc["adjudicado"] > 0]
    if not porcentajes:
        return "En Gestión"
    promedio = sum(porcentajes) / len(porcentajes)
    if promedio >= 1:
        return "Finalizado"
    elif promedio > 0:
        return "En Ejecución"
    return "En Gestión"

def color_estado(estado):
    return {
        "Finalizado": "#27ae60",
        "En Ejecución": "#f39c12",
        "En Gestión": "#e74c3c"
    }.get(estado, "#95a7b5")

def limpiar_presupuesto(valor):
    if isinstance(valor, (int, float)):
        return float(valor)
    v = str(valor).replace("$", "").replace(",", "").strip()
    try:
        return float(v)
    except:
        return 0.0

def fig_to_html(fig):
    return pio.to_html(fig, full_html=False, include_plotlyjs=False)

def limpiar_num(valor):
    """Convierte cualquier valor string con $, % o comas a float."""
    if isinstance(valor, (int, float)):
        return float(valor)
    v = str(valor).replace("$", "").replace("%", "").replace(",", "").strip()
    try:
        return float(v)
    except:
        return 0.0


# =============================================
# GENERAMOS UN HTML POR PROYECTO
# =============================================

archivos_generados = []

for proyecto in tablero:
    nombre    = proyecto["nombre_proyecto"]
    cat       = proyecto["cat_programatica"]
    ocs       = proyecto["ocs"]
    presup    = limpiar_presupuesto(proyecto["presupuesto"])
    estado    = clasificar_estado(ocs)
    color     = color_estado(estado)
    adj_total = sum(oc["adjudicado"] for oc in ocs)
    pago_total= sum(oc["pagado"] for oc in ocs)
    pct_fin   = (pago_total / adj_total * 100) if adj_total > 0 else 0

    # --- GRAFICO 1: Avance Financiero por OC ---
    oc_labels  = [oc["oc"] for oc in ocs]
    oc_adj     = [oc["adjudicado"] for oc in ocs]
    oc_pag     = [oc["pagado"] for oc in ocs]

    fig_fin = go.Figure()
    fig_fin.add_trace(go.Bar(
        name="Adjudicado",
        x=oc_labels,
        y=oc_adj,
        marker_color="#3498db",
        opacity=0.5,
        text=[f"${v:,.0f}" for v in oc_adj],
        textposition="outside"
    ))
    fig_fin.add_trace(go.Bar(
        name="Pagado",
        x=oc_labels,
        y=oc_pag,
        marker_color="#2ecc71",
        text=[f"${v:,.0f}" for v in oc_pag],
        textposition="outside"
    ))
    fig_fin.update_layout(
        title="💰 Avance Financiero por OC",
        barmode="overlay",
        yaxis_title="Monto ($)",
        xaxis_title="Orden de Compra",
        legend=dict(orientation="h", y=-0.2),
        plot_bgcolor="white",
        height=400
    )

    # --- GRAFICO 2: Estado por OC ---
    oc_estados = [clasificar_estado([oc]) for oc in ocs]
    oc_colores = [color_estado(e) for e in oc_estados]

    fig_estado = go.Figure(go.Bar(
        x=oc_labels,
        y=[1] * len(oc_labels),
        marker_color=oc_colores,
        text=oc_estados,
        textposition="inside",
        textfont=dict(color="white", size=13),
        showlegend=False,
        hovertext=[f"{oc}: {e}" for oc, e in zip(oc_labels, oc_estados)],
        hoverinfo="text"
    ))
    fig_estado.update_layout(
        title="🚦 Estado por OC",
        yaxis=dict(visible=False),
        plot_bgcolor="white",
        height=250
    )

    # --- GRAFICO 3: Avance Físico por Ítem ---
    html_fisico = ""
    for oc in ocs:
        if oc["items"]:
            items     = oc["items"]
            etiquetas = [f"Ítem {it['Item']}: {it['Denominacion'][:40]}" for it in items]

            # Barras agrupadas: anterior / en mes / acumulado (%)
            fig_fis = go.Figure()
            fig_fis.add_trace(go.Bar(
                name="Anterior",
                x=[it["Porcentaje_anterior"] for it in items],
                y=etiquetas,
                orientation="h",
                marker_color="#95a5a6",
                text=[f"{it['Porcentaje_anterior']:.1f}%" for it in items],
                textposition="inside",
                hovertemplate="<b>%{y}</b><br>Anterior: %{x:.1f}%<extra></extra>"
            ))
            fig_fis.add_trace(go.Bar(
                name="En Mes",
                x=[it["Porcentaje_en_mes"] for it in items],
                y=etiquetas,
                orientation="h",
                marker_color="#3498db",
                text=[f"{it['Porcentaje_en_mes']:.1f}%" for it in items],
                textposition="inside",
                hovertemplate="<b>%{y}</b><br>En Mes: %{x:.1f}%<extra></extra>"
            ))
            fig_fis.add_trace(go.Bar(
                name="Acumulado",
                x=[it["Porcentaje_Acumulado"] for it in items],
                y=etiquetas,
                orientation="h",
                marker_color="#9b59b6",
                text=[f"{it['Porcentaje_Acumulado']:.1f}%" for it in items],
                textposition="inside",
                hovertemplate="<b>%{y}</b><br>Acumulado: %{x:.1f}%<extra></extra>"
            ))
            fig_fis.update_layout(
                title=f"🔧 Avance Físico (%) — OC: {oc['oc']} | {oc.get('certificado', '')}",
                barmode="group",
                xaxis=dict(title="% Avance", range=[0, 115]),
                plot_bgcolor="white",
                legend=dict(orientation="h", y=-0.15),
                height=max(350, len(items) * 70)
            )

            # Tabla detallada de ítems
            filas_items = ""
            for it in items:
                filas_items += f"""
                <tr>
                    <td><b>{it['Item']}</b></td>
                    <td>{it['Denominacion']}</td>
                    <td>{it['Unidad']}</td>
                    <td>{limpiar_num(it['Cantidad']):,.2f}</td>
                    <td>${limpiar_num(it['Precio_Unitario']):,.2f}</td>
                    <td>${limpiar_num(it['Total']):,.2f}</td>
                    <td>{limpiar_num(it['%Inc']):.2f}%</td>
                    <td>{limpiar_num(it['Cantidad_Anterior']):,.2f}</td>
                    <td>{limpiar_num(it['Cantidad_en_mes']):,.2f}</td>
                    <td>{limpiar_num(it['Cantidad_acumulada']):,.2f}</td>
                    <td>{limpiar_num(it['Porcentaje_anterior']):.1f}%</td>
                    <td>{limpiar_num(it['Porcentaje_en_mes']):.1f}%</td>
                    <td><b>{limpiar_num(it['Porcentaje_Acumulado']):.1f}%</b></td>
                    <td>${limpiar_num(it['Importe_anterior']):,.2f}</td>
                    <td>${limpiar_num(it['Importe_en_mes']):,.2f}</td>
                    <td><b>${limpiar_num(it['Importe_Acumulado']):,.2f}</b></td>
                </tr>
                """

            tabla_items = f"""
            <div style="overflow-x:auto; margin-top:20px">
                <table>
                    <thead>
                        <tr style="background:#6c3483;color:white">
                            <th>#</th>
                            <th>Denominación</th>
                            <th>Und</th>
                            <th>Cantidad</th>
                            <th>P. Unitario</th>
                            <th>Total</th>
                            <th>% Inc</th>
                            <th>Cant. Ant</th>
                            <th>Cant. Mes</th>
                            <th>Cant. Acum</th>
                            <th>% Ant</th>
                            <th>% Mes</th>
                            <th>% Acum</th>
                            <th>Imp. Ant</th>
                            <th>Imp. Mes</th>
                            <th>Imp. Acum</th>
                        </tr>
                    </thead>
                    <tbody>{filas_items}</tbody>
                </table>
            </div>
            """

            html_fisico += f"""
            <div class="tarjeta">
                {fig_to_html(fig_fis)}
                <h3 style="margin-top:25px;color:#6c3483">📊 Detalle por Ítem</h3>
                {tabla_items}
            </div>
            """

    if not html_fisico:
        html_fisico = '<div class="tarjeta"><p style="color:gray;text-align:center">Sin certificado completo disponible aún.</p></div>'

    # --- TABLA DE OCs ---
    filas_tabla = ""
    for oc in ocs:
        pct = oc["porcentaje"] * 100
        estado_oc = clasificar_estado([oc])
        color_oc  = color_estado(estado_oc)
        link = f'<a href="{oc["link_certificado"]}" target="_blank">📄 Ver</a>' if oc.get("link_certificado") else "-"
        filas_tabla += f"""
        <tr>
            <td>{oc['oc']}</td>
            <td>{oc['proveedor']}</td>
            <td>${oc['comprometido']:,.0f}</td>
            <td>${oc['adjudicado']:,.0f}</td>
            <td>${oc['pagado']:,.0f}</td>
            <td>{pct:.0f}%</td>
            <td><span style="background:{color_oc};color:white;padding:3px 8px;border-radius:6px;font-size:0.85em">{estado_oc}</span></td>
            <td>{oc.get('certificado') or '-'}</td>
            <td>{link}</td>
        </tr>
        """

    # --- HTML FINAL DEL PROYECTO ---
    html = f"""
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>{nombre}</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        body {{ font-family: 'Segoe UI', sans-serif; background: #f4f6f9; margin: 0; padding: 20px; color: #2c3e50; }}
        h1 {{ text-align: center; font-size: 1.8em; margin-bottom: 5px; }}
        .subtitulo {{ text-align: center; color: #7f8c8d; margin-bottom: 25px; }}
        .tarjeta {{ background: white; border-radius: 12px; padding: 20px; margin-bottom: 25px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
        .kpis {{ display: flex; justify-content: center; gap: 20px; flex-wrap: wrap; margin-bottom: 25px; }}
        .kpi {{ background: white; border-radius: 12px; padding: 15px 25px; text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,0.08); min-width: 130px; }}
        .kpi .numero {{ font-size: 1.8em; font-weight: bold; }}
        .kpi .etiqueta {{ font-size: 0.85em; color: #7f8c8d; margin-top: 4px; }}
        .badge {{ display:inline-block; padding: 5px 14px; border-radius: 20px; color: white; font-weight: bold; font-size: 1em; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 0.9em; }}
        th {{ background: #2c3e50; color: white; padding: 10px; text-align: left; }}
        td {{ padding: 9px 10px; border-bottom: 1px solid #ecf0f1; }}
        tr:hover {{ background: #f9f9f9; }}
    </style>
</head>
<body>

<h1>🏗️ {nombre}</h1>
<p class="subtitulo">{cat}</p>

<!-- KPIs -->
<div class="kpis">
    <div class="kpi">
        <div class="numero">${presup/1_000_000:.1f}M</div>
        <div class="etiqueta">Presupuesto</div>
    </div>
    <div class="kpi">
        <div class="numero">${adj_total/1_000_000:.1f}M</div>
        <div class="etiqueta">Adjudicado</div>
    </div>
    <div class="kpi">
        <div class="numero">${pago_total/1_000_000:.1f}M</div>
        <div class="etiqueta">Pagado</div>
    </div>
    <div class="kpi">
        <div class="numero">{pct_fin:.0f}%</div>
        <div class="etiqueta">Avance Financiero</div>
    </div>
    <div class="kpi">
        <div class="numero"><span class="badge" style="background:{color}">{estado}</span></div>
        <div class="etiqueta">Estado General</div>
    </div>
</div>

<!-- Estado por OC -->
<div class="tarjeta">
    {fig_to_html(fig_estado)}
</div>

<!-- Avance Financiero -->
<div class="tarjeta">
    {fig_to_html(fig_fin)}
</div>

<!-- Tabla de OCs -->
<div class="tarjeta">
    <h2 style="margin-top:0">📋 Detalle de Órdenes de Compra</h2>
    <table>
        <thead>
            <tr>
                <th>OC</th>
                <th>Proveedor</th>
                <th>Comprometido</th>
                <th>Adjudicado</th>
                <th>Pagado</th>
                <th>%</th>
                <th>Estado</th>
                <th>Certificado</th>
                <th>Link</th>
            </tr>
        </thead>
        <tbody>
            {filas_tabla}
        </tbody>
    </table>
</div>

<!-- Avance Físico -->
<div class="tarjeta">
    <h2 style="margin-top:0">🔧 Avance Físico por Certificado</h2>
</div>
{html_fisico}

</body>
</html>
"""

    # Guardamos el archivo
    nombre_archivo = nombre.replace(" ", "_").replace("/", "-")[:50]
    ruta = f"dashboards/{cat}_{nombre_archivo}.html"
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(html)

    archivos_generados.append(ruta)
    print(f"✅ {nombre} → {ruta}")

print(f"\n📁 {len(archivos_generados)} dashboard(s) generado(s) en la carpeta /dashboards")
import json
import plotly.graph_objects as go
from collections import defaultdict
import plotly.io as pio
import os

# Cargar datos
with open("tablero.json", "r", encoding="utf-8") as f:
    tablero = json.load(f)

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

def tailwind_estado(estado):
    """Retorna clases de Tailwind según el estado para los badges"""
    if not estado:
        return "bg-slate-100 text-slate-700 border-slate-200"
    e = estado.lower()
    if "finalizado" in e:
        return "bg-green-100 text-green-700 border-green-200"
    elif "ejecución" in e or "ejecucion" in e or "pendiente" in e:
        return "bg-amber-100 text-amber-700 border-amber-200"
    else:
        return "bg-red-100 text-red-700 border-red-200"

def limpiar_presupuesto(valor):
    if isinstance(valor, (int, float)): return float(valor)
    v = str(valor).replace("$", "").replace(",", "").strip()
    try: return float(v)
    except: return 0.0

def limpiar_num(valor):
    if isinstance(valor, (int, float)): return float(valor)
    v = str(valor).replace("$", "").replace("%", "").replace(",", "").strip()
    try: return float(v)
    except: return 0.0

def fig_to_html(fig):
    return pio.to_html(fig, full_html=False, include_plotlyjs=False)

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
    estado_clase = tailwind_estado(estado)
    
    adj_total = sum(oc["adjudicado"] for oc in ocs)
    pago_total= sum(oc["pagado"] for oc in ocs)
    pct_fin   = (pago_total / adj_total * 100) if adj_total > 0 else 0

    fecha_inicio = next((oc.get("fecha_inicio") for oc in ocs if oc.get("fecha_inicio")), "-")
    fecha_fin    = next((oc.get("fecha_fin_estimada") for oc in ocs if oc.get("fecha_fin_estimada")), "-")

    # --- GRAFICO 1: Avance Financiero por OC ---
    oc_labels = [oc["oc"] for oc in ocs]
    oc_adj    = [oc["adjudicado"] for oc in ocs]
    oc_pag    = [oc["pagado"] for oc in ocs]

    fig_fin = go.Figure()
    fig_fin.add_trace(go.Bar(name="Adjudicado", x=oc_labels, y=oc_adj, marker_color="#3498db", opacity=0.5, text=[f"${v:,.0f}" for v in oc_adj], textposition="outside"))
    fig_fin.add_trace(go.Bar(name="Pagado", x=oc_labels, y=oc_pag, marker_color="#2ecc71", text=[f"${v:,.0f}" for v in oc_pag], textposition="outside"))
    fig_fin.update_layout(title="💰 Avance Financiero por OC", barmode="overlay", yaxis_title="Monto ($)", xaxis_title="Orden de Compra", legend=dict(orientation="h", y=-0.2), plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", height=350, margin=dict(l=20, r=20, t=40, b=20))

    # --- GRAFICO 2: Línea de Importes por CER ---
    fig_linea = go.Figure()
    for idx, oc in enumerate(ocs):
        historial = oc.get("historial_cer", [])
        if historial:
            pares    = [(h["certificado"], limpiar_num(h["total_importe_mes"])) for h in historial if limpiar_num(h["total_importe_mes"]) >= 0]
            certs    = [p[0] for p in pares]
            importes = [p[1] for p in pares]
            if certs:
                visible = True if idx == 0 else "legendonly"
                fig_linea.add_trace(go.Scatter(x=certs, y=importes, mode="lines+markers+text", name=oc["oc"], visible=visible, text=[f"${v:,.0f}" for v in importes], textposition="top center", hovertemplate="<b>%{x}</b><br>Importe Mes: $%{y:,.0f}<extra></extra>", marker=dict(size=10), line=dict(width=2)))
    fig_linea.update_layout(title="📈 Importe Ejecutado por Certificado", xaxis_title="Certificado", yaxis_title="Importe del Mes ($)", plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", legend=dict(title="OC — clic para mostrar/ocultar", orientation="h", y=-0.2), height=350, margin=dict(l=20, r=20, t=40, b=20))
    # --- GRAFICO 3: Avance Físico por Ítem ---
    html_fisico = ""
    for oc in ocs:
        if oc["items"]:
            items = oc["items"]
            etiquetas = [f"Ítem {it['Item']}: {it['Denominacion'][:40]}" for it in items]

            fig_fis = go.Figure()
            fig_fis.add_trace(go.Bar(name="Anterior", x=[it["Porcentaje_anterior"] for it in items], y=etiquetas, orientation="h", marker_color="#cbd5e1", text=[f"{it['Porcentaje_anterior']:.1f}%" for it in items], textposition="inside", hovertemplate="<b>%{y}</b><br>Anterior: %{x:.1f}%<extra></extra>"))
            fig_fis.add_trace(go.Bar(name="En Mes", x=[it["Porcentaje_en_mes"] for it in items], y=etiquetas, orientation="h", marker_color="#60a5fa", text=[f"{it['Porcentaje_en_mes']:.1f}%" for it in items], textposition="inside", hovertemplate="<b>%{y}</b><br>En Mes: %{x:.1f}%<extra></extra>"))
            fig_fis.add_trace(go.Bar(name="Acumulado", x=[it["Porcentaje_Acumulado"] for it in items], y=etiquetas, orientation="h", marker_color="#818cf8", text=[f"{it['Porcentaje_Acumulado']:.1f}%" for it in items], textposition="inside", hovertemplate="<b>%{y}</b><br>Acumulado: %{x:.1f}%<extra></extra>"))
            fig_fis.update_layout(title="", barmode="group", xaxis=dict(title="% Avance", range=[0, 115]), plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", legend=dict(orientation="h", y=-0.15), height=max(350, len(items) * 50), margin=dict(l=10, r=10, t=10, b=10))

            # Tabla detallada de ítems
            filas_items = ""
            for it in items:
                filas_items += f"""
                <tr class="border-b border-slate-100 hover:bg-slate-50 transition-colors">
                    <td class="p-3 font-bold text-slate-400">{it['Item']}</td>
                    <td class="p-3 font-medium max-w-[250px] truncate" title="{it['Denominacion']}">{it['Denominacion']}</td>
                    <td class="p-3 text-center text-slate-500">{it['Unidad']}</td>
                    <td class="p-3 text-right">{limpiar_num(it['Cantidad']):,.2f}</td>
                    <td class="p-3 text-right text-slate-500">${limpiar_num(it['Precio_Unitario']):,.2f}</td>
                    <td class="p-3 text-right font-medium">${limpiar_num(it['Total']):,.2f}</td>
                    <td class="p-3 text-right text-indigo-600 font-bold">{limpiar_num(it['%Inc']):.2f}%</td>
                    <td class="p-3 text-right text-slate-400">{limpiar_num(it['Cantidad_Anterior']):,.2f}</td>
                    <td class="p-3 text-right text-slate-500">{limpiar_num(it['Cantidad_en_mes']):,.2f}</td>
                    <td class="p-3 text-right text-indigo-600 font-bold">{limpiar_num(it['Cantidad_acumulada']):,.2f}</td>
                    <td class="p-3 text-right text-slate-400">{limpiar_num(it['Porcentaje_anterior']):.1f}%</td>
                    <td class="p-3 text-right text-slate-500">{limpiar_num(it['Porcentaje_en_mes']):.1f}%</td>
                    <td class="p-3 text-right bg-indigo-50 font-bold text-indigo-700">{limpiar_num(it['Porcentaje_Acumulado']):.1f}%</td>
                    <td class="p-3 text-right text-slate-400">${limpiar_num(it['Importe_anterior']):,.2f}</td>
                    <td class="p-3 text-right text-slate-500">${limpiar_num(it['Importe_en_mes']):,.2f}</td>
                    <td class="p-3 text-right font-bold text-slate-700">${limpiar_num(it['Importe_Acumulado']):,.2f}</td>
                </tr>
                """

            html_fisico += f"""
            <div class="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm mb-8">
                <div class="flex flex-wrap justify-between items-center gap-4 mb-4">
                    <h5 class="font-bold text-slate-800 flex items-center gap-2 text-lg">
                        <i data-lucide="wrench" class="w-6 h-6 text-orange-500"></i>
                        Avance Físico Detallado: OC {oc['oc']}
                    </h5>
                    <span class="text-[10px] font-bold text-slate-500 bg-slate-100 border border-slate-200 px-3 py-1.5 rounded-lg uppercase tracking-widest">Certificado: {oc.get('certificado','')}</span>
                </div>
                <div class="mb-6">{fig_to_html(fig_fis)}</div>
                
                <h6 class="text-sm font-bold text-slate-500 uppercase mb-3 flex items-center gap-2"><i data-lucide="table-2" class="w-4 h-4"></i> Tabla de Ítems</h6>
                <div class="overflow-x-auto rounded-xl border border-slate-200 bg-white custom-scroll shadow-sm">
                    <table class="w-full text-left text-xs whitespace-nowrap">
                        <thead class="bg-slate-50 text-slate-500 uppercase font-bold border-b border-slate-200 tracking-wider">
                            <tr>
                                <th class="p-4">#</th><th class="p-4">Denominación</th><th class="p-4 text-center">Und</th>
                                <th class="p-4 text-right">Cant. Total</th><th class="p-4 text-right">P. Unit</th>
                                <th class="p-4 text-right">Total $</th><th class="p-4 text-right">% Incidencia</th>
                                <th class="p-4 text-right">Cant. Ant</th><th class="p-4 text-right">Cant. Mes</th><th class="p-4 text-right">Cant. Acum</th>
                                <th class="p-4 text-right">% Ant</th><th class="p-4 text-right">% Mes</th><th class="p-4 text-right">% Acum</th>
                                <th class="p-4 text-right">Imp. Ant</th><th class="p-4 text-right">Imp. Mes</th><th class="p-4 text-right">Imp. Acum</th>
                            </tr>
                        </thead>
                        <tbody>{filas_items}</tbody>
                    </table>
                </div>
            </div>
            """

    if not html_fisico:
        html_fisico = '<div class="bg-white p-8 rounded-2xl border-2 border-dashed border-slate-200 text-center text-slate-400 font-medium"><i data-lucide="info" class="w-8 h-8 mx-auto mb-3 opacity-50"></i> Sin certificados completos disponibles aún para esta obra.</div>'

    # --- TABLA DE OCs CON DESPLEGABLE DE HISTORIAL ---
    filas_tabla = ""
    for i_oc, oc in enumerate(ocs):
        pct       = oc["porcentaje"] * 100
        estado_texto = oc["estado"] if oc["estado"] else "Sin estado"
        color_clase  = tailwind_estado(estado_texto)

        historial = oc.get("historial_cer", [])
        if historial:
            filas_hist = ""
            for cer in historial:
                link_cer = f'<a href="{cer["link_cer"]}" target="_blank" class="text-indigo-600 hover:text-indigo-800 font-semibold underline">📄 CER</a>' if cer.get("link_cer") else "-"
                link_in  = f'<a href="{cer["link_in"]}" target="_blank" class="text-indigo-600 hover:text-indigo-800 font-semibold underline">📸 Fotos</a>' if cer.get("link_in") else "-"
                filas_hist += f"""
                <tr class="border-b border-slate-100 hover:bg-slate-50 transition-colors">
                    <td class="p-3 font-medium">{cer['certificado']}</td>
                    <td class="p-3">${limpiar_num(cer['total_oc']):,.2f}</td>
                    <td class="p-3">{limpiar_num(cer['total_unidad_acum']):,.2f}</td>
                    <td class="p-3 font-bold">{limpiar_num(cer['total_pct_acum']):.2f}%</td>
                    <td class="p-3 text-indigo-700 font-bold">${limpiar_num(cer['total_importe_acum']):,.2f}</td>
                    <td class="p-3 text-center">{link_cer}</td>
                    <td class="p-3 text-center">{link_in}</td>
                </tr>
                """
            desplegable = f"""
            <tr id="hist_{i_oc}" class="hidden bg-slate-50/80 border-b border-slate-200">
                <td colspan="8" class="p-6">
                    <div class="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
                        <h6 class="text-sm font-bold text-slate-600 uppercase mb-4 flex items-center gap-2"><i data-lucide="file-spreadsheet" class="w-5 h-5 text-indigo-500"></i> Historial de Certificados — OC {oc['oc']}</h6>
                        <div class="overflow-x-auto rounded-lg border border-slate-100">
                            <table class="w-full text-left text-xs whitespace-nowrap">
                                <thead class="bg-slate-100 text-slate-500 uppercase font-bold tracking-wider">
                                    <tr>
                                        <th class="p-3">Certificado</th><th class="p-3">Total OC</th><th class="p-3">Unid. Acum</th>
                                        <th class="p-3">% Acum</th><th class="p-3">Importe Acum</th><th class="p-3 text-center">CER</th><th class="p-3 text-center">Fotos IN</th>
                                    </tr>
                                </thead>
                                <tbody>{filas_hist}</tbody>
                            </table>
                        </div>
                    </div>
                </td>
            </tr>
            """
            btn = f'<button onclick="toggleHist({i_oc})" class="px-3 py-1.5 bg-slate-100 text-slate-600 hover:bg-slate-200 hover:text-indigo-600 rounded-lg text-xs font-bold flex items-center gap-1.5 transition-colors"><i data-lucide="history" class="w-4 h-4"></i> Ver CERs</button>'
        else:
            desplegable = ""
            btn = "-"

        filas_tabla += f"""
        <tr class="hover:bg-slate-50 transition-colors border-b border-slate-100">
            <td class="p-4 font-mono font-bold text-sm text-slate-700">{oc['oc']}</td>
            <td class="p-4 text-sm font-medium">{oc['proveedor']}</td>
            <td class="p-4 text-right font-semibold">${limpiar_num(oc['comprometido']):,.0f}</td>
            <td class="p-4 text-right font-semibold text-blue-600">${limpiar_num(oc['adjudicado']):,.0f}</td>
            <td class="p-4 text-right font-semibold text-green-600">${limpiar_num(oc['pagado']):,.0f}</td>
            <td class="p-4 text-center font-black">{pct:.0f}%</td>
            <td class="p-4">
                <span class="px-2.5 py-1.5 rounded-lg border text-[11px] font-bold inline-block max-w-[250px] whitespace-normal {color_clase}">{estado_texto}</span>
            </td>
            <td class="p-4 text-center">{btn}</td>
        </tr>
        {desplegable}
        """

    # --- HTML FINAL POR PROYECTO ---
    html = f"""
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{nombre} - Tablero de Obras</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/lucide@latest"></script>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
        body {{ font-family: 'Inter', sans-serif; }}
        .custom-scroll::-webkit-scrollbar {{ width: 6px; height: 6px; }}
        .custom-scroll::-webkit-scrollbar-track {{ background: #f8fafc; }}
        .custom-scroll::-webkit-scrollbar-thumb {{ background: #cbd5e1; border-radius: 10px; }}
        .custom-scroll::-webkit-scrollbar-thumb:hover {{ background: #94a3b8; }}
    </style>
    <script>
        function toggleHist(i) {{
            const row = document.getElementById('hist_' + i);
            if(row.classList.contains('hidden')) {{
                row.classList.remove('hidden');
            }} else {{
                row.classList.add('hidden');
            }}
        }}
    </script>
</head>
<body class="bg-slate-50 min-h-screen text-slate-900 selection:bg-indigo-100">

    <div class="max-w-7xl mx-auto px-4 md:px-8 py-10">
        
        <header class="mb-10 text-center">
            <div class="inline-flex items-center justify-center p-3 bg-indigo-600 rounded-2xl shadow-lg shadow-indigo-200 mb-4">
                <i data-lucide="hard-hat" class="text-white w-8 h-8"></i>
            </div>
            <h1 class="text-3xl md:text-4xl font-extrabold tracking-tight text-slate-800 mb-2">{nombre}</h1>
            <div class="inline-flex items-center gap-2 bg-slate-200/60 text-slate-600 px-4 py-1.5 rounded-full text-sm font-bold tracking-wider">
                <i data-lucide="tag" class="w-4 h-4"></i> {cat}
            </div>
        </header>

        <div class="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-4 mb-10">
            <div class="bg-white p-4 rounded-2xl border border-slate-200 shadow-sm col-span-2 lg:col-span-1">
                <div class="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1">Presupuesto</div>
                <div class="text-xl font-black text-slate-800">${presup/1_000_000:.1f}M</div>
            </div>
            <div class="bg-white p-4 rounded-2xl border border-slate-200 shadow-sm col-span-2 lg:col-span-1 border-b-4 border-b-blue-500">
                <div class="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1">Adjudicado</div>
                <div class="text-xl font-black text-blue-600">${adj_total/1_000_000:.1f}M</div>
            </div>
            <div class="bg-white p-4 rounded-2xl border border-slate-200 shadow-sm col-span-2 lg:col-span-1 border-b-4 border-b-green-500">
                <div class="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1">Pagado</div>
                <div class="text-xl font-black text-green-600">${pago_total/1_000_000:.1f}M</div>
            </div>
            <div class="bg-white p-4 rounded-2xl border border-slate-200 shadow-sm col-span-2 lg:col-span-1">
                <div class="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1">Avance Financiero</div>
                <div class="text-xl font-black text-indigo-600">{pct_fin:.0f}%</div>
            </div>
            <div class="bg-white p-4 rounded-2xl border border-slate-200 shadow-sm col-span-2 md:col-span-4 lg:col-span-1">
                <div class="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-2">Estado General</div>
                <span class="px-2.5 py-1 rounded-md text-xs font-bold border {estado_clase}">{estado}</span>
            </div>
            <div class="bg-white p-4 rounded-2xl border border-slate-200 shadow-sm col-span-1">
                <div class="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1">Fecha Inicio</div>
                <div class="text-sm font-bold text-slate-700 mt-1 flex items-center gap-1.5"><i data-lucide="calendar" class="w-4 h-4 text-slate-400"></i> {fecha_inicio}</div>
            </div>
            <div class="bg-white p-4 rounded-2xl border border-slate-200 shadow-sm col-span-1">
                <div class="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1">Fin Estimado</div>
                <div class="text-sm font-bold text-slate-700 mt-1 flex items-center gap-1.5"><i data-lucide="calendar-check" class="w-4 h-4 text-slate-400"></i> {fecha_fin}</div>
            </div>
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-10">
            <div class="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm">
                <h2 class="text-lg font-bold text-slate-800 mb-4 flex items-center gap-2"><i data-lucide="trending-up" class="w-5 h-5 text-indigo-500"></i> Evolución de Certificados</h2>
                {fig_to_html(fig_linea)}
            </div>
            <div class="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm">
                <h2 class="text-lg font-bold text-slate-800 mb-4 flex items-center gap-2"><i data-lucide="bar-chart-3" class="w-5 h-5 text-indigo-500"></i> Balance por Orden de Compra</h2>
                {fig_to_html(fig_fin)}
            </div>
        </div>

        <div class="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm mb-10">
            <h2 class="text-lg font-bold text-slate-800 mb-6 flex items-center gap-2"><i data-lucide="list-checks" class="w-5 h-5 text-indigo-500"></i> Detalle de Órdenes de Compra</h2>
            <div class="overflow-x-auto rounded-xl border border-slate-200 custom-scroll">
                <table class="w-full text-left text-sm border-collapse">
                    <thead class="bg-slate-50 text-slate-500 font-bold uppercase text-[10px] tracking-wider border-b border-slate-200">
                        <tr>
                            <th class="p-4">OC</th><th class="p-4">Proveedor</th><th class="p-4 text-right">Comprometido</th>
                            <th class="p-4 text-right">Adjudicado</th><th class="p-4 text-right">Pagado</th><th class="p-4 text-center">% Fin</th>
                            <th class="p-4">Estado</th><th class="p-4 text-center">Acciones</th>
                        </tr>
                    </thead>
                    <tbody>{filas_tabla}</tbody>
                </table>
            </div>
        </div>

        <div class="mb-4">
            <h2 class="text-2xl font-extrabold text-slate-800 flex items-center gap-3">
                <div class="bg-orange-100 p-2 rounded-lg"><i data-lucide="activity" class="w-6 h-6 text-orange-600"></i></div> 
                Avance Físico de la Obra
            </h2>
        </div>
        
        {html_fisico}

    </div>

    <script>
        lucide.createIcons();
    </script>
</body>
</html>
"""

    nombre_archivo = nombre.replace(" ", "_").replace("/", "-")[:50]
    ruta = f"dashboards/{cat}_{nombre_archivo}.html"
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(html)

    archivos_generados.append(ruta)
    print(f"✅ {nombre} → {ruta}")

# =============================================
# GENERAMOS EL INDEX.HTML (menú principal)
# =============================================

proyectos_por_cat = defaultdict(list)
for proyecto, ruta in zip(tablero, archivos_generados):
    proyectos_por_cat[proyecto["cat_programatica"]].append((proyecto, ruta))

cards_html = ""
for cat, items in sorted(proyectos_por_cat.items()):
    cards_html += f"""
    <div class="mb-10">
        <h2 class="text-xs font-bold text-slate-400 uppercase tracking-widest mb-4 flex items-center gap-2">
            <i data-lucide="folder" class="w-4 h-4"></i> {cat}
        </h2>
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
    """
    for proyecto, ruta in items:
        ocs       = proyecto["ocs"]
        estado    = clasificar_estado(ocs)
        estado_clase = tailwind_estado(estado)
        adj_total = sum(oc["adjudicado"] for oc in ocs)
        pago_total= sum(oc["pagado"] for oc in ocs)
        pct_fin   = (pago_total / adj_total * 100) if adj_total > 0 else 0
        nombre_p  = proyecto["nombre_proyecto"]
        # ruta relativa desde index.html (mismo directorio dashboards/)
        href      = os.path.basename(ruta)

        cards_html += f"""
        <a href="{href}" class="group block bg-white border border-slate-200 rounded-2xl p-5 shadow-sm hover:shadow-md hover:border-indigo-300 transition-all">
            <div class="flex justify-between items-start mb-3">
                <h3 class="font-bold text-slate-800 text-sm leading-snug group-hover:text-indigo-600 transition-colors">{nombre_p}</h3>
                <span class="ml-2 shrink-0 px-2 py-1 rounded-md text-[10px] font-bold border {estado_clase}">{estado}</span>
            </div>
            <div class="flex items-center gap-1 mb-3">
                <div class="flex-1 bg-slate-100 rounded-full h-2 overflow-hidden">
                    <div class="bg-indigo-500 h-2 rounded-full" style="width:{min(pct_fin,100):.0f}%"></div>
                </div>
                <span class="text-xs font-black text-indigo-600 ml-2">{pct_fin:.0f}%</span>
            </div>
            <div class="flex justify-between text-[11px] text-slate-400 font-medium">
                <span>Adj: <span class="text-slate-600 font-bold">${adj_total/1_000_000:.1f}M</span></span>
                <span>Pag: <span class="text-green-600 font-bold">${pago_total/1_000_000:.1f}M</span></span>
                <span>{len(ocs)} OC{'s' if len(ocs)>1 else ''}</span>
            </div>
        </a>
        """
    cards_html += "</div></div>"

index_html = f"""
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Tablero de Obras</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/lucide@latest"></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
        body {{ font-family: 'Inter', sans-serif; }}
    </style>
</head>
<body class="bg-slate-50 min-h-screen text-slate-900">
    <div class="max-w-6xl mx-auto px-4 md:px-8 py-10">
        <header class="mb-10 text-center">
            <div class="inline-flex items-center justify-center p-3 bg-indigo-600 rounded-2xl shadow-lg shadow-indigo-200 mb-4">
                <i data-lucide="hard-hat" class="text-white w-8 h-8"></i>
            </div>
            <h1 class="text-3xl md:text-4xl font-extrabold tracking-tight text-slate-800 mb-2">Tablero de Obras</h1>
            <p class="text-slate-400 text-sm">{len(tablero)} proyecto(s) — hacé clic en una tarjeta para ver el detalle</p>
        </header>
        {cards_html}
    </div>
    <script>lucide.createIcons();</script>
</body>
</html>
"""

with open("dashboards/index.html", "w", encoding="utf-8") as f:
    f.write(index_html)

print("🏠 index.html generado → dashboards/index.html")
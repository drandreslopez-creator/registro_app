from datetime import datetime
from html import escape
from io import StringIO
from pathlib import Path
from urllib.parse import parse_qs, urlencode
import csv

from wsgiref.simple_server import make_server

from app_registro_hospital import (
    COLOMBIA_TZ,
    DATE_FORMAT,
    TODOS_LOS_PERIODOS,
    TURNOS,
    agrupar_resumenes_jornada,
    ahora_colombia,
    calcular_periodo,
    exportar_html,
    formatear_hora_visible,
    guardar_registro,
    guardar_registro_en_fecha,
    leer_registros,
    minutos_a_texto,
    periodos_disponibles,
    resumir_periodo,
    turno_actual_por_hora,
)


HOST = "0.0.0.0"
PORT = 8000


def html_layout(content: str, mensaje: str = "", error: str = "") -> bytes:
    mensaje_html = f'<div class="notice ok">{escape(mensaje)}</div>' if mensaje else ""
    error_html = f'<div class="notice error">{escape(error)}</div>' if error else ""
    ahora = ahora_colombia()
    periodo_actual = calcular_periodo(ahora)

    pagina = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Registro hospital</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f7f8fc;
      --card: #ffffff;
      --ink: #18212f;
      --muted: #5b6472;
      --line: #d9deea;
      --accent: #0f62fe;
      --accent-2: #0b4ecc;
      --good: #e8f7ee;
      --good-ink: #166534;
      --bad: #fff1f2;
      --bad-ink: #b42318;
      --shadow: 0 16px 40px rgba(15, 23, 42, 0.08);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background:
        radial-gradient(circle at top left, #dbeafe 0, transparent 28%),
        radial-gradient(circle at top right, #fde68a 0, transparent 18%),
        var(--bg);
      color: var(--ink);
    }}
    .page {{
      max-width: 1180px;
      margin: 0 auto;
      padding: 20px 14px 40px;
    }}
    .hero {{
      background: linear-gradient(135deg, #ffffff, #eef4ff);
      border: 1px solid var(--line);
      border-radius: 24px;
      padding: 22px;
      box-shadow: var(--shadow);
      margin-bottom: 16px;
    }}
    .hero h1 {{
      margin: 0 0 8px;
      font-size: clamp(1.8rem, 4vw, 2.6rem);
    }}
    .hero p {{
      margin: 0;
      color: var(--muted);
      line-height: 1.5;
    }}
    .hero-meta {{
      margin-top: 14px;
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      color: var(--muted);
      font-size: 0.95rem;
    }}
    .badge {{
      display: inline-flex;
      align-items: center;
      padding: 7px 12px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.8);
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(12, minmax(0, 1fr));
      gap: 16px;
    }}
    .card {{
      grid-column: span 12;
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 20px;
      padding: 18px;
      box-shadow: var(--shadow);
    }}
    .card h2 {{
      margin: 0 0 14px;
      font-size: 1.15rem;
    }}
    .stack {{
      display: grid;
      gap: 12px;
    }}
    .actions {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }}
    .actions.wide {{
      grid-template-columns: repeat(3, minmax(0, 1fr));
    }}
    label {{
      display: block;
      font-size: 0.92rem;
      color: var(--muted);
      margin-bottom: 6px;
    }}
    input, select, button {{
      width: 100%;
      border-radius: 12px;
      border: 1px solid var(--line);
      padding: 12px 14px;
      font-size: 1rem;
      background: #fff;
    }}
    button {{
      border: none;
      background: var(--accent);
      color: #fff;
      font-weight: 600;
      cursor: pointer;
    }}
    button.secondary {{
      background: #eef4ff;
      color: var(--accent-2);
      border: 1px solid #bfd2ff;
    }}
    button.neutral {{
      background: #f3f4f6;
      color: #111827;
      border: 1px solid #d1d5db;
    }}
    .notice {{
      border-radius: 14px;
      padding: 12px 14px;
      margin-bottom: 14px;
      font-weight: 600;
    }}
    .ok {{
      background: var(--good);
      color: var(--good-ink);
      border: 1px solid #b7e3c6;
    }}
    .error {{
      background: var(--bad);
      color: var(--bad-ink);
      border: 1px solid #f7c1c7;
    }}
    .stats {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
    }}
    .stat {{
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 14px;
      background: linear-gradient(180deg, #fff, #f8fbff);
    }}
    .stat small {{
      display: block;
      color: var(--muted);
      margin-bottom: 6px;
    }}
    .stat strong {{
      font-size: 1.15rem;
    }}
    .table-wrap {{
      overflow-x: auto;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      min-width: 760px;
    }}
    th, td {{
      border-bottom: 1px solid var(--line);
      padding: 10px 8px;
      text-align: left;
      font-size: 0.95rem;
    }}
    th {{
      color: var(--muted);
      font-weight: 700;
    }}
    .filters {{
      display: grid;
      grid-template-columns: 2fr 1fr 1fr;
      gap: 10px;
      align-items: end;
    }}
    .muted {{
      color: var(--muted);
    }}
    .footer {{
      margin-top: 16px;
      color: var(--muted);
      font-size: 0.92rem;
    }}
    @media (min-width: 900px) {{
      .span-4 {{ grid-column: span 4; }}
      .span-5 {{ grid-column: span 5; }}
      .span-7 {{ grid-column: span 7; }}
      .span-8 {{ grid-column: span 8; }}
    }}
    @media (max-width: 760px) {{
      .actions,
      .actions.wide,
      .stats,
      .filters {{
        grid-template-columns: 1fr;
      }}
      .page {{
        padding: 14px 10px 26px;
      }}
      .card {{
        padding: 14px;
      }}
    }}
  </style>
</head>
<body>
  <main class="page">
    <section class="hero">
      <h1>Registro personal del hospital</h1>
      <p>Versión web para celular. Guarda tus movimientos, calcula el tiempo por fuera de la institución y resume cada período del 21 al 20.</p>
      <div class="hero-meta">
        <span class="badge">Hora Colombia: {ahora.strftime("%Y-%m-%d %H:%M")}</span>
        <span class="badge">Período actual: {escape(periodo_actual)}</span>
      </div>
    </section>
    {mensaje_html}
    {error_html}
    {content}
    <div class="footer">Si vas a usarla desde el celular, abre esta dirección en el navegador del teléfono usando la misma red Wi‑Fi del computador.</div>
  </main>
</body>
</html>
"""
    return pagina.encode("utf-8")


def opciones_turno(include_libre: bool = False) -> str:
    turnos = ["12h dia", "12h noche", "5h manana"]
    if include_libre:
        turnos.append("libre")
    return "".join(f'<option value="{escape(turno)}">{escape(turno)}</option>' for turno in turnos)


def render_inicio(periodo_filtro: str, mensaje: str = "", error: str = "") -> bytes:
    registros = leer_registros()
    periodos = periodos_disponibles(registros)
    if periodo_filtro not in periodos:
        periodo_filtro = TODOS_LOS_PERIODOS

    registros_filtrados = [
        registro for registro in registros
        if periodo_filtro == TODOS_LOS_PERIODOS or registro.periodo == periodo_filtro
    ]
    resumen_total = resumir_periodo(registros_filtrados)
    resumenes_jornada = agrupar_resumenes_jornada(registros_filtrados)

    opciones_periodo = "".join(
        f'<option value="{escape(periodo)}" {"selected" if periodo == periodo_filtro else ""}>{escape(periodo)}</option>'
        for periodo in periodos
    )

    filas_jornada = "".join(
        "<tr>"
        f"<td>{escape(item.jornada)}</td>"
        f"<td>{escape(item.turno)}</td>"
        f"<td>{escape(item.horario)}</td>"
        f"<td>{minutos_a_texto(item.minutos_dentro)}</td>"
        f"<td>{minutos_a_texto(item.minutos_fuera)}</td>"
        f"<td>{minutos_a_texto(item.minutos_permitidos)}</td>"
        f"<td>{minutos_a_texto(item.minutos_exceso)}</td>"
        f"<td>{escape(item.estado)}</td>"
        "</tr>"
        for item in resumenes_jornada
    )

    filas_movimientos = "".join(
        "<tr>"
        f"<td>{escape(registro.fecha)}</td>"
        f"<td>{escape(formatear_hora_visible(registro.hora))}</td>"
        f"<td>{escape(registro.tipo.capitalize())}</td>"
        f"<td>{escape(registro.turno)}</td>"
        f"<td>{escape(registro.jornada)}</td>"
        f"<td>{escape(registro.detalle)}</td>"
        f"<td>{escape(registro.periodo)}</td>"
        "</tr>"
        for registro in registros_filtrados
    )

    contenido = f"""
    <section class="grid">
      <div class="card span-4">
        <h2>Registro rápido</h2>
        <form method="post" action="/registrar" class="stack">
          <input type="hidden" name="modo" value="rapido">
          <div>
            <label>Turno actual</label>
            <select name="turno">
              <option value="12h dia" {"selected" if turno_actual_por_hora() == "12h dia" else ""}>12h dia</option>
              <option value="12h noche" {"selected" if turno_actual_por_hora() == "12h noche" else ""}>12h noche</option>
              <option value="5h manana">5h manana</option>
            </select>
          </div>
          <div class="actions wide">
            <button type="submit" name="tipo" value="entrada">Registrar entrada</button>
            <button type="submit" name="tipo" value="salida">Registrar salida</button>
            <button type="submit" name="tipo" value="libre" class="neutral">Registrar libre</button>
          </div>
        </form>
      </div>

      <div class="card span-8">
        <h2>Registro manual</h2>
        <form method="post" action="/registrar" class="stack">
          <input type="hidden" name="modo" value="manual">
          <div class="filters">
            <div>
              <label>Fecha</label>
              <input type="date" name="fecha" value="{ahora_colombia().strftime('%Y-%m-%d')}">
            </div>
            <div>
              <label>Hora (HH:MM)</label>
              <input type="time" name="hora" value="">
            </div>
            <div>
              <label>Tipo</label>
              <select name="tipo">
                <option value="entrada">entrada</option>
                <option value="salida">salida</option>
                <option value="libre">libre</option>
              </select>
            </div>
          </div>
          <div class="filters">
            <div>
              <label>Turno</label>
              <select name="turno">
                {opciones_turno(include_libre=True)}
              </select>
            </div>
            <div style="grid-column: span 2;">
              <label>Detalle</label>
              <input type="text" name="detalle" placeholder="Opcional">
            </div>
          </div>
          <div class="actions">
            <button type="submit">Guardar manual</button>
            <a href="/"><button type="button" class="secondary">Limpiar</button></a>
          </div>
        </form>
      </div>

      <div class="card span-12">
        <h2>Resumen del período</h2>
        <form method="get" action="/" class="filters" style="margin-bottom: 14px;">
          <div>
            <label>Ver período</label>
            <select name="periodo">
              {opciones_periodo}
            </select>
          </div>
          <div><button type="submit" class="secondary">Filtrar</button></div>
          <div></div>
        </form>
        <div class="stats">
          <div class="stat"><small>Turnos calculados</small><strong>{resumen_total['turnos']}</strong></div>
          <div class="stat"><small>Tiempo dentro</small><strong>{minutos_a_texto(resumen_total['dentro'])}</strong></div>
          <div class="stat"><small>Tiempo fuera</small><strong>{minutos_a_texto(resumen_total['fuera'])}</strong></div>
          <div class="stat"><small>Tiempo permitido</small><strong>{minutos_a_texto(resumen_total['permitidos'])}</strong></div>
          <div class="stat"><small>Exceso a revisar</small><strong>{minutos_a_texto(resumen_total['exceso'])}</strong></div>
          <div class="stat"><small>Registros sin turno</small><strong>{resumen_total['sin_turno']}</strong></div>
        </div>
      </div>

      <div class="card span-12">
        <h2>Exportación</h2>
        <div class="actions">
          <a href="/exportar.csv?{urlencode({'periodo': periodo_filtro})}"><button type="button" class="secondary">Descargar CSV</button></a>
          <a href="/exportar.html?{urlencode({'periodo': periodo_filtro})}"><button type="button" class="secondary">Descargar HTML</button></a>
        </div>
      </div>

      <div class="card span-12">
        <h2>Resumen por jornada</h2>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Jornada</th>
                <th>Turno</th>
                <th>Horario</th>
                <th>Dentro</th>
                <th>Fuera</th>
                <th>Permitido</th>
                <th>Exceso</th>
                <th>Estado</th>
              </tr>
            </thead>
            <tbody>
              {filas_jornada or '<tr><td colspan="8" class="muted">No hay turnos calculables en este filtro.</td></tr>'}
            </tbody>
          </table>
        </div>
      </div>

      <div class="card span-12">
        <h2>Movimientos registrados</h2>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Fecha</th>
                <th>Hora</th>
                <th>Tipo</th>
                <th>Turno</th>
                <th>Jornada</th>
                <th>Detalle</th>
                <th>Período</th>
              </tr>
            </thead>
            <tbody>
              {filas_movimientos or '<tr><td colspan="7" class="muted">No hay registros todavía.</td></tr>'}
            </tbody>
          </table>
        </div>
      </div>
    </section>
    """
    return html_layout(contenido, mensaje=mensaje, error=error)


def registros_filtrados(periodo_filtro: str):
    registros = leer_registros()
    if periodo_filtro == TODOS_LOS_PERIODOS:
        return registros
    return [registro for registro in registros if registro.periodo == periodo_filtro]


def exportar_csv_bytes(periodo_filtro: str) -> bytes:
    salida = StringIO()
    writer = csv.writer(salida)
    writer.writerow(["fecha", "hora", "tipo", "detalle", "periodo", "turno", "jornada"])
    for registro in registros_filtrados(periodo_filtro):
        writer.writerow(
            [
                registro.fecha,
                registro.hora,
                registro.tipo,
                registro.detalle,
                registro.periodo,
                registro.turno,
                registro.jornada,
            ]
        )
    return salida.getvalue().encode("utf-8")


def redirect(start_response, destino: str):
    start_response("303 See Other", [("Location", destino)])
    return [b""]


def app(environ, start_response):
    metodo = environ.get("REQUEST_METHOD", "GET").upper()
    ruta = environ.get("PATH_INFO", "/")
    query = parse_qs(environ.get("QUERY_STRING", ""))
    periodo_filtro = query.get("periodo", [TODOS_LOS_PERIODOS])[0]

    if metodo == "GET" and ruta == "/":
        mensaje = query.get("mensaje", [""])[0]
        error = query.get("error", [""])[0]
        cuerpo = render_inicio(periodo_filtro, mensaje=mensaje, error=error)
        start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
        return [cuerpo]

    if metodo == "POST" and ruta == "/registrar":
        longitud = int(environ.get("CONTENT_LENGTH") or 0)
        datos = parse_qs(environ["wsgi.input"].read(longitud).decode("utf-8"))
        modo = datos.get("modo", ["rapido"])[0]
        tipo = datos.get("tipo", ["entrada"])[0].strip().lower()
        turno = datos.get("turno", ["12h dia"])[0].strip().lower()
        detalle = datos.get("detalle", [""])[0].strip()

        try:
            if tipo not in {"entrada", "salida", "libre"}:
                raise ValueError("Tipo inválido.")

            if modo == "manual":
                fecha = datos.get("fecha", [""])[0].strip()
                hora = datos.get("hora", [""])[0].strip()
                if not fecha or not hora:
                    raise ValueError("Debes indicar fecha y hora.")
                if tipo == "libre":
                    turno = "libre"
                    if not detalle:
                        detalle = "Dia libre"
                elif turno == "libre":
                    raise ValueError("Entrada o salida no pueden quedar con turno libre.")
                fecha_hora = datetime.strptime(f"{fecha} {hora}", DATE_FORMAT).replace(tzinfo=COLOMBIA_TZ)
                guardar_registro_en_fecha(tipo=tipo, fecha_hora=fecha_hora, turno=turno, detalle=detalle)
                destino = "/?" + urlencode({"mensaje": "Registro manual guardado."})
                return redirect(start_response, destino)

            if tipo == "libre":
                turno = "libre"
                detalle = detalle or "Dia libre"
            guardar_registro(tipo=tipo, turno=turno, detalle=detalle)
            destino = "/?" + urlencode({"mensaje": f"Registro de {tipo} guardado."})
            return redirect(start_response, destino)
        except ValueError as exc:
            destino = "/?" + urlencode({"error": str(exc), "periodo": periodo_filtro})
            return redirect(start_response, destino)

    if metodo == "GET" and ruta == "/exportar.csv":
        contenido = exportar_csv_bytes(periodo_filtro)
        nombre = "historial_periodo.csv" if periodo_filtro != TODOS_LOS_PERIODOS else "historial_total.csv"
        start_response(
            "200 OK",
            [
                ("Content-Type", "text/csv; charset=utf-8"),
                ("Content-Disposition", f'attachment; filename="{nombre}"'),
            ],
        )
        return [contenido]

    if metodo == "GET" and ruta == "/exportar.html":
        destino = Path("/tmp/reporte_registro_web.html")
        exportar_html(destino, registros_filtrados(periodo_filtro))
        contenido = destino.read_bytes()
        nombre = "reporte_periodo.html" if periodo_filtro != TODOS_LOS_PERIODOS else "reporte_total.html"
        start_response(
            "200 OK",
            [
                ("Content-Type", "text/html; charset=utf-8"),
                ("Content-Disposition", f'attachment; filename="{nombre}"'),
            ],
        )
        return [contenido]

    start_response("404 Not Found", [("Content-Type", "text/plain; charset=utf-8")])
    return [b"No encontrado"]


def main():
    with make_server(HOST, PORT, app) as server:
        print(f"Servidor web disponible en http://127.0.0.1:{PORT}")
        print(f"Para celular en la misma red: http://TU_IP_LOCAL:{PORT}")
        server.serve_forever()


if __name__ == "__main__":
    main()

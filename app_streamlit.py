from datetime import datetime
from io import BytesIO, StringIO

import pandas as pd
import streamlit as st

from app_registro_hospital import (
    TODOS_LOS_PERIODOS,
    agrupar_resumenes_jornada,
    ahora_colombia,
    construir_fecha_hora_manual,
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


st.set_page_config(
    page_title="Registro hospital",
    page_icon="🏥",
    layout="wide",
)


def estilos():
    st.markdown(
        """
        <style>
        .block-container {
          padding-top: 0.35rem;
          padding-bottom: 1.4rem;
          max-width: 1120px;
        }
        .hero {
          padding: 0.25rem 0 0.35rem;
          margin-bottom: 0.2rem;
        }
        .hero h1 {
          margin: 0;
          color: #152033;
          font-size: 1.25rem;
          line-height: 1.05;
          letter-spacing: 0.04em;
          text-transform: uppercase;
        }
        .summary-card {
          padding: 0.8rem 0.85rem;
          border-radius: 16px;
          border: 1px solid #d7dfef;
          background: linear-gradient(180deg, #ffffff, #f8fbff);
        }
        .summary-card .label {
          color: #607086;
          font-size: 0.82rem;
        }
        .summary-card .value {
          color: #162033;
          font-size: 1.1rem;
          font-weight: 700;
          margin-top: 0.2rem;
        }
        div[data-testid="stForm"] {
          border: 1px solid #d7dfef;
          border-radius: 18px;
          padding: 0.7rem 0.8rem 0.5rem;
          background: rgba(255, 255, 255, 0.78);
        }
        div[data-testid="stForm"] h3 {
          margin-top: 0.2rem;
        }
        div[data-testid="stHorizontalBlock"] > div:has(div[data-testid="metric-container"]) {
          min-width: 0;
        }
        [data-testid="stMetricValue"] {
          font-size: 1.55rem;
        }
        @media (max-width: 768px) {
          .block-container {
            padding-top: 0.2rem;
            padding-bottom: 1rem;
            padding-left: 0.7rem;
            padding-right: 0.7rem;
          }
          .hero h1 {
            font-size: 1rem;
            letter-spacing: 0.05em;
          }
          .summary-card {
            padding: 0.7rem 0.75rem;
          }
          [data-testid="stMetricValue"] {
            font-size: 1.2rem;
          }
          [data-testid="stMetricLabel"] {
            font-size: 0.8rem;
          }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def bytes_csv(registros) -> bytes:
    filas = [
        {
            "fecha": r.fecha,
            "hora": r.hora,
            "tipo": r.tipo,
            "detalle": r.detalle,
            "periodo": r.periodo,
            "turno": r.turno,
            "jornada": r.jornada,
        }
        for r in registros
    ]
    return pd.DataFrame(filas).to_csv(index=False).encode("utf-8")


def bytes_html(registros) -> bytes:
    ruta = "/tmp/reporte_streamlit_registro.html"
    exportar_html(PathLike(ruta), registros)
    with open(ruta, "rb") as archivo:
        return archivo.read()


class PathLike(str):
    def write_text(self, text: str, encoding: str = "utf-8"):
        with open(self, "w", encoding=encoding) as archivo:
            archivo.write(text)


def dataframe_resumen(resumenes):
    filas = []
    for item in resumenes:
        filas.append(
            {
                "Jornada": item.jornada,
                "Turno": item.turno,
                "Horario": item.horario,
                "Dentro": minutos_a_texto(item.minutos_dentro),
                "Fuera": minutos_a_texto(item.minutos_fuera),
                "Permitido": minutos_a_texto(item.minutos_permitidos),
                "Exceso": minutos_a_texto(item.minutos_exceso),
                "Estado": item.estado,
            }
        )
    return pd.DataFrame(filas)


def dataframe_movimientos(registros):
    filas = []
    for r in registros:
        filas.append(
            {
                "Fecha": r.fecha,
                "Hora": formatear_hora_visible(r.hora),
                "Tipo": r.tipo.capitalize(),
                "Turno": r.turno,
                "Jornada": r.jornada,
                "Detalle": r.detalle,
                "Periodo": r.periodo,
            }
        )
    return pd.DataFrame(filas)


def registros_filtrados(periodo: str):
    registros = leer_registros()
    if periodo == TODOS_LOS_PERIODOS:
        return registros
    return [registro for registro in registros if registro.periodo == periodo]


def registrar_rapido():
    tipo = st.session_state["tipo_rapido"]
    turno = st.session_state["turno_rapido"]
    detalle = ""
    try:
        guardar_registro(tipo=tipo, turno=turno, detalle=detalle)
        st.session_state["mensaje_ok"] = f"Registro de {tipo} guardado."
    except ValueError as exc:
        st.session_state["mensaje_error"] = str(exc)


def registrar_manual():
    tipo = st.session_state["manual_tipo"]
    turno = st.session_state["manual_turno"]
    detalle = st.session_state["manual_detalle"].strip()
    fecha = st.session_state["manual_fecha"]
    hora = st.session_state["manual_hora"]

    if tipo == "libre":
        turno = "libre"
        if not detalle:
            detalle = "Dia libre"
    elif turno == "libre":
        st.session_state["mensaje_error"] = "Entrada o salida no pueden quedar con turno libre."
        return

    try:
        fecha_hora = construir_fecha_hora_manual(fecha, hora)
        guardar_registro_en_fecha(tipo=tipo, fecha_hora=fecha_hora, turno=turno, detalle=detalle)
        st.session_state["mensaje_ok"] = (
            f"Registro manual guardado: {tipo.capitalize()} {fecha_hora.strftime('%Y-%m-%d %H:%M')} ({turno})"
        )
        st.session_state["manual_detalle"] = ""
    except ValueError as exc:
        st.session_state["mensaje_error"] = str(exc)


def registrar_dia_libre():
    fecha = st.session_state["libre_fecha"]
    try:
        fecha_hora = construir_fecha_hora_manual(fecha, "00:00")
        guardar_registro_en_fecha(tipo="libre", fecha_hora=fecha_hora, turno="libre", detalle="Dia libre")
        st.session_state["mensaje_ok"] = f"Día libre guardado y bloqueado: {fecha_hora.strftime('%Y-%m-%d')}"
    except ValueError as exc:
        st.session_state["mensaje_error"] = str(exc)


def mostrar_mensajes():
    ok = st.session_state.pop("mensaje_ok", "")
    error = st.session_state.pop("mensaje_error", "")
    if ok:
        st.success(ok)
    if error:
        st.error(error)


def main():
    estilos()
    st.markdown(
        f"""
        <section class="hero">
          <h1>REGISTRO DE INGRESO HRS</h1>
        </section>
        """,
        unsafe_allow_html=True,
    )

    mostrar_mensajes()

    registros = leer_registros()
    opciones_periodo = periodos_disponibles(registros)
    if "periodo_filtro" not in st.session_state:
        st.session_state["periodo_filtro"] = TODOS_LOS_PERIODOS

    st.session_state["periodo_filtro"] = st.selectbox(
        "Ver período",
        opciones_periodo,
        index=opciones_periodo.index(st.session_state["periodo_filtro"])
        if st.session_state["periodo_filtro"] in opciones_periodo
        else 0,
    )

    filtrados = registros_filtrados(st.session_state["periodo_filtro"])
    resumen_total = resumir_periodo(filtrados)
    resumenes_jornada = agrupar_resumenes_jornada(filtrados)

    izquierda, derecha = st.columns([1, 1], gap="medium")

    with izquierda:
        st.subheader("Registro rápido")
        with st.form("registro_rapido"):
            st.selectbox(
                "Turno actual",
                ["12h dia", "12h noche", "5h manana"],
                index=["12h dia", "12h noche", "5h manana"].index(turno_actual_por_hora())
                if turno_actual_por_hora() in ["12h dia", "12h noche", "5h manana"]
                else 0,
                key="turno_rapido",
            )
            c1, c2 = st.columns(2)
            if c1.form_submit_button("Registrar entrada", use_container_width=True):
                st.session_state["tipo_rapido"] = "entrada"
                registrar_rapido()
                st.rerun()
            if c2.form_submit_button("Registrar salida", use_container_width=True):
                st.session_state["tipo_rapido"] = "salida"
                registrar_rapido()
                st.rerun()

        st.subheader("Día libre")
        with st.form("registro_libre"):
            st.date_input("Fecha del día libre", value=ahora_colombia().date(), key="libre_fecha")
            if st.form_submit_button("Bloquear día libre", use_container_width=True):
                registrar_dia_libre()
                st.rerun()

    with derecha:
        st.subheader("Registro manual")
        with st.form("registro_manual"):
            c1, c2 = st.columns(2)
            c1.date_input("Fecha", value=ahora.date(), key="manual_fecha")
            c2.text_input("Hora (HH:MM)", value="", key="manual_hora", placeholder="07:00")
            c3, c4 = st.columns(2)
            c3.selectbox("Tipo", ["entrada", "salida", "libre"], key="manual_tipo")
            c4.selectbox("Turno", ["12h dia", "12h noche", "5h manana", "libre"], key="manual_turno")
            st.text_input("Detalle", key="manual_detalle")
            if st.form_submit_button("Guardar manual", use_container_width=True):
                registrar_manual()
                st.rerun()

    st.subheader("Resumen del período filtrado")
    s1, s2, s3, s4, s5, s6 = st.columns(6)
    cards = [
        ("Turnos calculados", str(resumen_total["turnos"])),
        ("Tiempo dentro", minutos_a_texto(resumen_total["dentro"])),
        ("Tiempo fuera", minutos_a_texto(resumen_total["fuera"])),
        ("Permitido", minutos_a_texto(resumen_total["permitidos"])),
        ("Exceso", minutos_a_texto(resumen_total["exceso"])),
        ("Sin turno", str(resumen_total["sin_turno"])),
    ]
    for columna, (label, value) in zip([s1, s2, s3, s4, s5, s6], cards):
        columna.markdown(
            f'<div class="summary-card"><div class="label">{label}</div><div class="value">{value}</div></div>',
            unsafe_allow_html=True,
        )

    st.subheader("Exportación")
    e1, e2 = st.columns(2)
    e1.download_button(
        "Descargar CSV",
        data=bytes_csv(filtrados),
        file_name="historial_filtrado.csv",
        mime="text/csv",
        use_container_width=True,
    )
    e2.download_button(
        "Descargar HTML",
        data=bytes_html(filtrados),
        file_name="reporte_filtrado.html",
        mime="text/html",
        use_container_width=True,
    )

    st.subheader("Resumen por jornada")
    df_resumen = dataframe_resumen(resumenes_jornada)
    if df_resumen.empty:
        st.info("No hay turnos calculables en este filtro.")
    else:
        st.dataframe(df_resumen, use_container_width=True, hide_index=True)

    st.subheader("Movimientos registrados")
    df_movimientos = dataframe_movimientos(filtrados)
    if df_movimientos.empty:
        st.info("No hay registros todavía.")
    else:
        st.dataframe(df_movimientos, use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()

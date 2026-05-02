from datetime import datetime
from io import BytesIO, StringIO
from pathlib import Path
import csv

import streamlit as st

from app_registro_hospital import (
    TODOS_LOS_PERIODOS,
    agrupar_resumenes_jornada,
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
    page_title="REGISTRO DE INGRESO HRS",
    page_icon="🏥",
    layout="wide",
)


def registros_filtrados(periodo_filtro: str):
    registros = leer_registros()
    if periodo_filtro == TODOS_LOS_PERIODOS:
        return registros
    return [registro for registro in registros if registro.periodo == periodo_filtro]


def csv_bytes(registros) -> bytes:
    salida = StringIO()
    writer = csv.writer(salida)
    writer.writerow(["fecha", "hora", "tipo", "detalle", "periodo", "turno", "jornada"])
    for registro in registros:
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


def html_bytes(registros) -> bytes:
    destino = Path("/tmp/reporte_streamlit.html")
    exportar_html(destino, registros)
    return destino.read_bytes()


def tabla_resumen(resumenes):
    return [
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
        for item in resumenes
    ]


def tabla_movimientos(registros):
    return [
        {
            "Fecha": registro.fecha,
            "Hora": formatear_hora_visible(registro.hora),
            "Tipo": registro.tipo.capitalize(),
            "Turno": registro.turno,
            "Jornada": registro.jornada,
            "Detalle": registro.detalle,
            "Periodo": registro.periodo,
        }
        for registro in registros
    ]


st.markdown(
    """
    <style>
    .block-container {
      padding-top: 1.05rem;
      padding-bottom: 1rem;
      max-width: 1120px;
    }
    .app-title {
      margin: 0 0 0.55rem 0;
      font-size: 1.7rem;
      line-height: 1.05;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      font-weight: 700;
    }
    @media (max-width: 768px) {
      .block-container {
        padding-top: 0.9rem;
        padding-left: 0.7rem;
        padding-right: 0.7rem;
      }
      .app-title {
        font-size: 1.32rem;
      }
    }
    </style>
    <div class="app-title">REGISTRO DE INGRESO HRS</div>
    """,
    unsafe_allow_html=True,
)
ahora = datetime.now()

col_a, col_b = st.columns([1, 1], gap="small")

with col_a:
    st.subheader("Registro rápido")
    with st.form("registro_rapido"):
        turno_rapido = st.selectbox(
            "Turno actual",
            options=["12h dia", "12h noche", "5h manana"],
            index=["12h dia", "12h noche", "5h manana"].index(turno_actual_por_hora())
            if turno_actual_por_hora() in ["12h dia", "12h noche", "5h manana"]
            else 0,
        )
        col_1, col_2 = st.columns(2)
        enviar_entrada = col_1.form_submit_button("Registrar entrada", use_container_width=True)
        enviar_salida = col_2.form_submit_button("Registrar salida", use_container_width=True)

        if enviar_entrada:
            registro = guardar_registro(tipo="entrada", turno=turno_rapido)
            st.success(f"Entrada guardada: {registro.fecha} {registro.hora} ({registro.turno})")
        if enviar_salida:
            registro = guardar_registro(tipo="salida", turno=turno_rapido)
            st.success(f"Salida guardada: {registro.fecha} {registro.hora} ({registro.turno})")

    st.subheader("Día libre")
    with st.form("registro_libre"):
        libre_fecha = st.date_input("Fecha del día libre", value=datetime.now().date(), format="YYYY-MM-DD")
        guardar_libre = st.form_submit_button("Bloquear día libre", use_container_width=True)

        if guardar_libre:
            try:
                fecha_hora = construir_fecha_hora_manual(libre_fecha, "00:00")
                registro = guardar_registro_en_fecha(
                    tipo="libre",
                    fecha_hora=fecha_hora,
                    turno="libre",
                    detalle="Dia libre",
                )
                st.success(f"Día libre guardado y bloqueado: {registro.fecha}")
            except ValueError as exc:
                st.error(str(exc))

with col_b:
    st.subheader("Registro manual")
    with st.form("registro_manual"):
        c1, c2 = st.columns(2)
        manual_fecha = c1.date_input("Fecha", value=ahora.date(), format="YYYY-MM-DD")
        manual_hora = c2.text_input("Hora (HH:MM)", value="", placeholder="07:00")
        c3, c4 = st.columns(2)
        manual_tipo = c3.selectbox("Tipo", options=["entrada", "salida", "libre"])
        manual_turno = c4.selectbox("Turno", options=["12h dia", "12h noche", "5h manana", "libre"])
        manual_detalle = st.text_input("Detalle", value="")
        guardar_manual = st.form_submit_button("Guardar manual", use_container_width=True)

        if guardar_manual:
            try:
                fecha_hora = construir_fecha_hora_manual(manual_fecha, manual_hora)
                turno = manual_turno
                detalle = manual_detalle.strip()
                if manual_tipo == "libre":
                    turno = "libre"
                    detalle = detalle or "Dia libre"
                elif turno == "libre":
                    raise ValueError("Entrada o salida no pueden quedar con turno libre.")

                registro = guardar_registro_en_fecha(
                    tipo=manual_tipo,
                    fecha_hora=fecha_hora,
                    turno=turno,
                    detalle=detalle,
                )
                st.success(
                    f"Registro manual guardado: {registro.tipo.capitalize()} "
                    f"{registro.fecha} {formatear_hora_visible(registro.hora)} ({registro.turno})"
                )
            except ValueError as exc:
                st.error(str(exc))

registros = leer_registros()
periodos = periodos_disponibles(registros)
periodo_filtro = st.selectbox("Ver periodo", options=periodos, index=0)
registros_vista = registros_filtrados(periodo_filtro)
resumen_total = resumir_periodo(registros_vista)
resumenes = agrupar_resumenes_jornada(registros_vista)

met_1, met_2, met_3, met_4, met_5, met_6 = st.columns(6)
met_1.metric("Turnos calculados", resumen_total["turnos"])
met_2.metric("Tiempo dentro", minutos_a_texto(resumen_total["dentro"]))
met_3.metric("Tiempo fuera", minutos_a_texto(resumen_total["fuera"]))
met_4.metric("Salida permitida", minutos_a_texto(resumen_total["permitidos"]))
met_5.metric("Exceso a revisar", minutos_a_texto(resumen_total["exceso"]))
met_6.metric("Registros sin turno", resumen_total["sin_turno"])

exp_1, exp_2 = st.columns(2)
with exp_1:
    st.download_button(
        "Descargar CSV",
        data=csv_bytes(registros_vista),
        file_name="historial_filtrado.csv",
        mime="text/csv",
        use_container_width=True,
    )
with exp_2:
    st.download_button(
        "Descargar HTML",
        data=html_bytes(registros_vista),
        file_name="reporte_filtrado.html",
        mime="text/html",
        use_container_width=True,
    )

st.subheader("Resumen por jornada")
st.dataframe(tabla_resumen(resumenes), use_container_width=True, hide_index=True)

st.subheader("Movimientos registrados")
st.dataframe(tabla_movimientos(registros_vista), use_container_width=True, hide_index=True)

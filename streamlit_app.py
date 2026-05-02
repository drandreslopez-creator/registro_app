from datetime import datetime
from io import BytesIO, StringIO
from pathlib import Path
import csv

import streamlit as st

from app_registro_hospital import (
    COLOMBIA_TZ,
    TODOS_LOS_PERIODOS,
    agrupar_resumenes_jornada,
    ahora_colombia,
    calcular_periodo,
    construir_fecha_hora_manual,
    exportar_html,
    guardar_registro,
    guardar_registro_en_fecha,
    leer_registros,
    minutos_a_texto,
    periodos_disponibles,
    resumir_periodo,
    turno_actual_por_hora,
)


st.set_page_config(
    page_title="Registro Hospital",
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
            "Hora": registro.hora,
            "Tipo": registro.tipo.capitalize(),
            "Turno": registro.turno,
            "Jornada": registro.jornada,
            "Detalle": registro.detalle,
            "Periodo": registro.periodo,
        }
        for registro in registros
    ]


st.title("Registro personal del hospital")
st.caption("Versión Streamlit para usar desde navegador y celular.")

ahora = ahora_colombia()
st.info(
    f"Hora Colombia: {ahora.strftime('%Y-%m-%d %H:%M:%S')} | "
    f"Periodo actual: {calcular_periodo(ahora)}"
)

st.warning(
    "Si publicas esto en Streamlit Community Cloud, los archivos locales generados por la app "
    "no están garantizados entre reinicios o sesiones. Para uso real y continuo conviene conectar "
    "un almacenamiento externo."
)

col_a, col_b = st.columns([1, 1.4])

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
        col_1, col_2, col_3 = st.columns(3)
        enviar_entrada = col_1.form_submit_button("Registrar entrada", use_container_width=True)
        enviar_salida = col_2.form_submit_button("Registrar salida", use_container_width=True)
        enviar_libre = col_3.form_submit_button("Registrar libre", use_container_width=True)

        if enviar_entrada:
            registro = guardar_registro(tipo="entrada", turno=turno_rapido)
            st.success(f"Entrada guardada: {registro.fecha} {registro.hora} ({registro.turno})")
        if enviar_salida:
            registro = guardar_registro(tipo="salida", turno=turno_rapido)
            st.success(f"Salida guardada: {registro.fecha} {registro.hora} ({registro.turno})")
        if enviar_libre:
            registro = guardar_registro(tipo="libre", turno="libre", detalle="Dia libre")
            st.success(f"Día libre guardado: {registro.fecha}")

with col_b:
    st.subheader("Registro manual")
    with st.form("registro_manual"):
        manual_fecha = st.date_input("Fecha", value=ahora.date(), format="YYYY-MM-DD")
        manual_hora = st.time_input("Hora", value=ahora.time().replace(microsecond=0), step=60)
        manual_tipo = st.selectbox("Tipo", options=["entrada", "salida", "libre"])
        manual_turno = st.selectbox("Turno", options=["12h dia", "12h noche", "5h manana", "libre"])
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
                    f"{registro.fecha} {registro.hora} ({registro.turno})"
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

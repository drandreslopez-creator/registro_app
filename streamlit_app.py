from datetime import datetime
from io import BytesIO, StringIO
import json
import os
from pathlib import Path
import csv

import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError


def configurar_google_desde_secrets():
    try:
        secrets = st.secrets
        list(secrets.keys())
    except StreamlitSecretNotFoundError:
        return

    if "google_service_account" in secrets:
        valor = secrets["google_service_account"]
        if isinstance(valor, str):
            os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"] = valor
        else:
            os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"] = json.dumps(dict(valor))
    elif "google_service_account_json" in secrets:
        os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"] = str(secrets["google_service_account_json"])
    elif "GOOGLE_SERVICE_ACCOUNT_JSON" in secrets:
        os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"] = str(secrets["GOOGLE_SERVICE_ACCOUNT_JSON"])

    if "google_sheet_id" in secrets:
        os.environ["GOOGLE_SHEET_ID"] = str(secrets["google_sheet_id"])
    elif "google_sheet_url" in secrets:
        os.environ["GOOGLE_SHEET_ID"] = str(secrets["google_sheet_url"])
    elif "GOOGLE_SHEET_ID" in secrets:
        os.environ["GOOGLE_SHEET_ID"] = str(secrets["GOOGLE_SHEET_ID"])
    elif "GOOGLE_SHEET_URL" in secrets:
        os.environ["GOOGLE_SHEET_ID"] = str(secrets["GOOGLE_SHEET_URL"])


configurar_google_desde_secrets()

from app_registro_hospital import (
    ESTADOS_DIA,
    TODOS_LOS_PERIODOS,
    agrupar_resumenes_jornada,
    construir_fecha_hora_manual,
    eliminar_estado_dia,
    eliminar_registro,
    exportar_html,
    formatear_hora_visible,
    guardar_registro,
    guardar_registro_en_fecha,
    guardar_estado_dia,
    leer_estados_dia,
    leer_registros,
    minutos_a_texto,
    periodos_combinados,
    resumen_total_jornadas,
    resumir_periodo,
    turno_actual_por_hora,
    usar_google_sheets,
)


st.set_page_config(
    page_title="REGISTRO DE INGRESO HRS",
    page_icon="🏥",
    layout="wide",
)


def registros_filtrados(registros, periodo_filtro: str):
    if periodo_filtro == TODOS_LOS_PERIODOS:
        return registros
    return [registro for registro in registros if registro.periodo == periodo_filtro]


def estados_filtrados(estados, periodo_filtro: str):
    if periodo_filtro == TODOS_LOS_PERIODOS:
        return estados
    return [estado for estado in estados if estado.periodo == periodo_filtro]


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


def normalizar_hora_interfaz(valor: str) -> str:
    texto = "".join(char for char in str(valor or "") if char.isdigit() or char == ":")
    if ":" in texto:
        return texto[:5]
    if len(texto) >= 3:
        texto = texto[:4].zfill(4)
        return f"{texto[:2]}:{texto[2:]}"
    return texto


def normalizar_hora_manual_input():
    st.session_state.manual_hora_input = normalizar_hora_interfaz(
        st.session_state.get("manual_hora_input", "")
    )


def tabla_resumen(resumenes):
    filas = [
        {
            "Jornada": item.jornada,
            "Turno": item.turno,
            "Programado": minutos_a_texto(item.minutos_programados),
            "Horario": item.horario,
            "Dentro": minutos_a_texto(item.minutos_dentro),
            "Fuera": minutos_a_texto(item.minutos_fuera),
            "Permitido": minutos_a_texto(item.minutos_permitidos),
            "Exceso": minutos_a_texto(item.minutos_exceso),
            "Estado": item.estado,
        }
        for item in resumenes
    ]
    if resumenes:
        total = resumen_total_jornadas(resumenes)
        filas.append(
            {
                "Jornada": total.jornada,
                "Turno": total.turno,
                "Programado": minutos_a_texto(total.minutos_programados),
                "Horario": total.horario,
                "Dentro": minutos_a_texto(total.minutos_dentro),
                "Fuera": minutos_a_texto(total.minutos_fuera),
                "Permitido": minutos_a_texto(total.minutos_permitidos),
                "Exceso": minutos_a_texto(total.minutos_exceso),
                "Estado": total.estado,
            }
        )
    return filas


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


def tabla_estados(estados):
    return [
        {
            "Fecha": estado.fecha,
            "Estado programado": estado.estado.capitalize(),
            "Detalle": estado.detalle,
            "Periodo": estado.periodo,
        }
        for estado in estados
    ]


def etiqueta_registro(registro):
    return (
        f"{registro.fecha} | {formatear_hora_visible(registro.hora)} | "
        f"{registro.tipo.capitalize()} | {registro.turno} | {registro.detalle or 'sin detalle'}"
    )


def etiqueta_estado(estado):
    return f"{estado.fecha} | {estado.estado} | {estado.detalle or 'sin detalle'}"


st.markdown(
    """
    <style>
    .block-container {
      padding-top: 1.05rem;
      padding-bottom: 1rem;
      max-width: 1120px;
    }
    @media (max-width: 768px) {
      .block-container {
        padding-top: 0.9rem;
        padding-left: 0.7rem;
        padding-right: 0.7rem;
      }
    }
    </style>
    """,
    unsafe_allow_html=True,
)
st.title("INGRESO HRS")
if not usar_google_sheets():
    st.warning("Google Sheets no está conectado todavía. La app seguiría usando archivos locales temporales.")

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

    st.subheader("Estado del día")
    with st.form("estado_dia"):
        estado_fecha = st.date_input("Fecha a programar", value=datetime.now().date(), format="YYYY-MM-DD")
        estado_tipo = st.selectbox(
            "Estado programado",
            options=["12h dia", "12h noche", "5h manana", "libre", "libre despues de noche"],
        )
        estado_detalle = st.text_input("Detalle del estado", value="", placeholder="Opcional")
        guardar_estado = st.form_submit_button("Guardar estado del día", use_container_width=True)

        if guardar_estado:
            try:
                estado = guardar_estado_dia(estado_fecha, estado_tipo, estado_detalle)
                st.success(f"Estado programado guardado: {estado.fecha} ({estado.estado})")
            except ValueError as exc:
                st.error(str(exc))

with col_b:
    st.subheader("Registro manual")
    if "manual_hora_input" not in st.session_state:
        st.session_state.manual_hora_input = ""

    c1, c2 = st.columns(2)
    manual_fecha = c1.date_input("Fecha", value=ahora.date(), format="YYYY-MM-DD")
    c2.text_input(
        "Hora (HH:MM)",
        key="manual_hora_input",
        placeholder="0700",
        on_change=normalizar_hora_manual_input,
    )

    c3, c4 = st.columns(2)
    manual_tipo = c3.selectbox("Tipo", options=["entrada", "salida", "libre"])
    manual_turno = c4.selectbox("Turno", options=["12h dia", "12h noche", "5h manana", "libre"])
    manual_detalle = st.text_input("Detalle", value="")
    guardar_manual = st.button("Guardar manual", use_container_width=True)

    if guardar_manual:
        try:
            fecha_hora = construir_fecha_hora_manual(manual_fecha, st.session_state.manual_hora_input)
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
            st.session_state.manual_hora_input = ""
            st.success(
                f"Registro manual guardado: {registro.tipo.capitalize()} "
                f"{registro.fecha} {formatear_hora_visible(registro.hora)} ({registro.turno})"
            )
        except ValueError as exc:
            st.error(str(exc))

registros = leer_registros()
estados = leer_estados_dia()
periodos = periodos_combinados(registros, estados)
periodo_filtro = st.selectbox("Ver periodo", options=periodos, index=0)
registros_vista = registros_filtrados(registros, periodo_filtro)
estados_vista = estados_filtrados(estados, periodo_filtro)
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

st.subheader("Estado programado del día")
if estados_vista:
    st.dataframe(tabla_estados(estados_vista), use_container_width=True, hide_index=True)
    with st.form("eliminar_estado"):
        estado_seleccionado = st.selectbox(
            "Eliminar estado programado",
            options=range(len(estados_vista)),
            format_func=lambda i: etiqueta_estado(estados_vista[i]),
        )
        confirmar_eliminar_estado = st.form_submit_button("Eliminar estado seleccionado", use_container_width=True)
        if confirmar_eliminar_estado:
            if eliminar_estado_dia(estados_vista[estado_seleccionado].fecha):
                st.success("Estado programado eliminado.")
                st.rerun()
            st.error("No se pudo eliminar el estado programado.")
else:
    st.info("No hay estados programados en este periodo.")

st.subheader("Movimientos registrados")
st.dataframe(tabla_movimientos(registros_vista), use_container_width=True, hide_index=True)
if registros_vista:
    with st.form("eliminar_movimiento"):
        registro_seleccionado = st.selectbox(
            "Eliminar movimiento registrado",
            options=range(len(registros_vista)),
            format_func=lambda i: etiqueta_registro(registros_vista[i]),
        )
        confirmar_eliminar_movimiento = st.form_submit_button(
            "Eliminar movimiento seleccionado",
            use_container_width=True,
        )
        if confirmar_eliminar_movimiento:
            if eliminar_registro(registros_vista[registro_seleccionado]):
                st.success("Movimiento eliminado.")
                st.rerun()
            st.error("No se pudo eliminar el movimiento.")

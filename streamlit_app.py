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
    TURNOS,
    agrupar_resumenes_jornada,
    ahora_colombia,
    calcular_periodo,
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
    resumenes_programado_vs_real,
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


def horas_plan_total_texto(minutos: int) -> str:
    return str(minutos // 60)


def formatear_fecha_visible(fecha: str) -> str:
    try:
        return datetime.strptime(fecha, "%Y-%m-%d").strftime("%d-%m-%y")
    except ValueError:
        return fecha


def formatear_periodo_visible(periodo: str) -> str:
    if " al " not in periodo:
        return periodo
    inicio, fin = periodo.split(" al ", 1)
    return f"{formatear_fecha_visible(inicio)} al {formatear_fecha_visible(fin)}"


def formatear_horario_visible(horario: str) -> str:
    if horario in {"-", "Libre"}:
        return horario
    if " a " not in horario:
        return horario
    inicio, fin = horario.split(" a ", 1)
    try:
        inicio_dt = datetime.strptime(inicio, "%Y-%m-%d %H:%M")
        fin_dt = datetime.strptime(fin, "%Y-%m-%d %H:%M")
        return f"{inicio_dt.strftime('%d-%m-%y %H:%M')} a {fin_dt.strftime('%d-%m-%y %H:%M')}"
    except ValueError:
        return horario


def tabla_resumen(filas_resumen):
    filas = [
        {
            "Jornada": formatear_fecha_visible(item.jornada) if item.jornada != "TOTAL" else item.jornada,
            "Plan del dia": programado,
            "Turno": item.turno,
            "Programado": minutos_a_texto(item.minutos_programados),
            "Horario": formatear_horario_visible(item.horario),
            "Dentro": minutos_a_texto(item.minutos_dentro),
            "Fuera": minutos_a_texto(item.minutos_fuera),
            "Permitido": minutos_a_texto(item.minutos_permitidos),
            "Exceso": minutos_a_texto(item.minutos_exceso),
            "Estado": item.estado,
        }
        for item, programado in filas_resumen
    ]
    if filas_resumen:
        total = resumen_total_jornadas([item for item, _ in filas_resumen])
        filas.append(
            {
                "Jornada": total.jornada,
                "Plan del dia": horas_plan_total_texto(total.minutos_programados),
                "Turno": total.turno,
                "Programado": horas_plan_total_texto(total.minutos_programados),
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
            "Fecha": formatear_fecha_visible(registro.fecha),
            "Hora": formatear_hora_visible(registro.hora),
            "Tipo": registro.tipo.capitalize(),
            "Turno": registro.turno,
            "Jornada": formatear_fecha_visible(registro.jornada),
            "Detalle": registro.detalle,
            "Periodo": formatear_periodo_visible(registro.periodo),
        }
        for registro in registros
    ]


def tabla_estados(estados):
    return [
        {
            "Fecha": formatear_fecha_visible(estado.fecha),
            "Estado programado": estado.estado.capitalize(),
            "Detalle": estado.detalle,
            "Periodo": formatear_periodo_visible(estado.periodo),
        }
        for estado in estados
    ]


def resumen_estados_programados(estados):
    total_minutos = 0
    por_servicio = {}

    for estado in estados:
        minutos = TURNOS.get(estado.estado, TURNOS["sin definir"])["duracion_minutos"]
        total_minutos += minutos

        servicio = (estado.detalle or "Sin detalle").strip().upper()
        if servicio not in por_servicio:
            por_servicio[servicio] = {"dias": 0, "minutos": 0}
        por_servicio[servicio]["dias"] += 1
        por_servicio[servicio]["minutos"] += minutos

    filas_servicio = [
        {
            "Servicio": servicio,
            "Dias": datos["dias"],
            "Horas programadas": horas_plan_total_texto(datos["minutos"]),
        }
        for servicio, datos in sorted(
            por_servicio.items(),
            key=lambda item: (-item[1]["minutos"], item[0]),
        )
    ]
    return total_minutos, filas_servicio


def etiqueta_registro(registro):
    return (
        f"{formatear_fecha_visible(registro.fecha)} | {formatear_hora_visible(registro.hora)} | "
        f"{registro.tipo.capitalize()} | {registro.turno} | {registro.detalle or 'sin detalle'}"
    )


def etiqueta_estado(estado):
    return f"{formatear_fecha_visible(estado.fecha)} | {estado.estado} | {estado.detalle or 'sin detalle'}"


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
            st.success(
                f"Entrada guardada: {formatear_fecha_visible(registro.fecha)} "
                f"{registro.hora} ({registro.turno})"
            )
        if enviar_salida:
            registro = guardar_registro(tipo="salida", turno=turno_rapido)
            st.success(
                f"Salida guardada: {formatear_fecha_visible(registro.fecha)} "
                f"{registro.hora} ({registro.turno})"
            )

    st.subheader("Estado del día")
    with st.form("estado_dia"):
        estado_fecha = st.date_input("Fecha a programar", value=datetime.now().date(), format="DD-MM-YYYY")
        estado_tipo = st.selectbox(
            "Estado programado",
            options=["12h dia", "12h noche", "5h manana", "libre", "libre despues de noche"],
        )
        estado_detalle = st.text_input("Detalle del estado", value="", placeholder="Opcional")
        guardar_estado = st.form_submit_button("Guardar estado del día", use_container_width=True)

        if guardar_estado:
            try:
                estado = guardar_estado_dia(estado_fecha, estado_tipo, estado_detalle)
                st.success(f"Estado programado guardado: {formatear_fecha_visible(estado.fecha)} ({estado.estado})")
            except ValueError as exc:
                st.error(str(exc))

with col_b:
    st.subheader("Registro manual")
    if st.session_state.get("limpiar_hora_manual"):
        st.session_state.manual_hora_input = ""
        st.session_state.limpiar_hora_manual = False
    if st.session_state.get("mensaje_manual_ok"):
        st.success(st.session_state["mensaje_manual_ok"])
        del st.session_state["mensaje_manual_ok"]

    if "manual_hora_input" not in st.session_state:
        st.session_state.manual_hora_input = ""

    c1, c2 = st.columns(2)
    manual_fecha = c1.date_input("Fecha", value=ahora.date(), format="DD-MM-YYYY")
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
            st.session_state.limpiar_hora_manual = True
            st.session_state["mensaje_manual_ok"] = (
                f"Registro manual guardado: {registro.tipo.capitalize()} "
                f"{formatear_fecha_visible(registro.fecha)} "
                f"{formatear_hora_visible(registro.hora)} ({registro.turno})"
            )
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))

try:
    registros = leer_registros()
    estados = leer_estados_dia()
except Exception as exc:
    st.error(
        "No se pudo abrir la base de datos de Google Sheets. "
        "Revisa la clave privada actual de la cuenta de servicio en Streamlit Secrets."
    )
    st.caption(str(exc))
    st.stop()

periodos = periodos_combinados(registros, estados)
periodo_actual = calcular_periodo(ahora_colombia())
indice_periodo = periodos.index(periodo_actual) if periodo_actual in periodos else 0
periodo_filtro = st.selectbox(
    "Ver periodo",
    options=periodos,
    index=indice_periodo,
    format_func=formatear_periodo_visible,
)
registros_vista = registros_filtrados(registros, periodo_filtro)
estados_vista = estados_filtrados(estados, periodo_filtro)
resumen_total = resumir_periodo(registros_vista)
filas_resumen = resumenes_programado_vs_real(registros_vista, estados_vista)

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
st.dataframe(tabla_resumen(filas_resumen), use_container_width=True, hide_index=True)

st.subheader("Estado programado del día")
if estados_vista:
    total_minutos_programados, filas_servicio = resumen_estados_programados(estados_vista)
    etiqueta_horas_programadas = (
        "Horas programadas del periodo"
        if periodo_filtro != TODOS_LOS_PERIODOS
        else "Horas programadas del filtro"
    )
    st.metric(etiqueta_horas_programadas, horas_plan_total_texto(total_minutos_programados))
    st.dataframe(tabla_estados(estados_vista), use_container_width=True, hide_index=True)
    if filas_servicio:
        st.caption("Organizado por servicio / detalle")
        st.dataframe(filas_servicio, use_container_width=True, hide_index=True)
    with st.form("eliminar_estado"):
        estado_seleccionado = st.selectbox(
            "Eliminar estado programado",
            options=range(len(estados_vista)),
            format_func=lambda i: etiqueta_estado(estados_vista[i]),
        )
        confirmar_eliminar_estado = st.form_submit_button("Eliminar estado seleccionado", use_container_width=True)
        if confirmar_eliminar_estado:
            if eliminar_estado_dia(estados_vista[estado_seleccionado]):
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

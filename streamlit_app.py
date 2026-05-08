from datetime import datetime, timedelta
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

    if "google_drive_folder_id" in secrets:
        os.environ["GOOGLE_DRIVE_FOLDER_ID"] = str(secrets["google_drive_folder_id"])
    elif "GOOGLE_DRIVE_FOLDER_ID" in secrets:
        os.environ["GOOGLE_DRIVE_FOLDER_ID"] = str(secrets["GOOGLE_DRIVE_FOLDER_ID"])

    if "cloudinary_cloud_name" in secrets:
        os.environ["CLOUDINARY_CLOUD_NAME"] = str(secrets["cloudinary_cloud_name"])
    elif "CLOUDINARY_CLOUD_NAME" in secrets:
        os.environ["CLOUDINARY_CLOUD_NAME"] = str(secrets["CLOUDINARY_CLOUD_NAME"])

    if "cloudinary_upload_preset" in secrets:
        os.environ["CLOUDINARY_UPLOAD_PRESET"] = str(secrets["cloudinary_upload_preset"])
    elif "CLOUDINARY_UPLOAD_PRESET" in secrets:
        os.environ["CLOUDINARY_UPLOAD_PRESET"] = str(secrets["CLOUDINARY_UPLOAD_PRESET"])

    if "cloudinary_folder" in secrets:
        os.environ["CLOUDINARY_FOLDER"] = str(secrets["cloudinary_folder"])
    elif "CLOUDINARY_FOLDER" in secrets:
        os.environ["CLOUDINARY_FOLDER"] = str(secrets["CLOUDINARY_FOLDER"])


configurar_google_desde_secrets()

from app_registro_hospital import (
    ESTADOS_DIA,
    TODOS_LOS_PERIODOS,
    TURNOS,
    agrupar_resumenes_jornada,
    ahora_colombia,
    calcular_periodo,
    clave_registro,
    construir_fecha_hora_manual,
    eliminar_estado_dia,
    eliminar_registro,
    exportar_html,
    formatear_hora_visible,
    guardar_evidencia_registro,
    guardar_registro,
    guardar_registro_en_fecha,
    guardar_estado_dia,
    leer_estados_dia,
    leer_evidencias,
    leer_registros,
    minutos_a_texto,
    periodos_combinados,
    resumenes_programado_vs_real,
    resumen_total_jornadas,
    resumir_periodo,
    turno_actual_por_hora,
    usar_cloudinary,
    usar_google_sheets,
)


st.set_page_config(
    page_title="REGISTRO DE INGRESO HRS",
    page_icon="🏥",
    layout="wide",
)

CLAVE_ACCESO_APP = "8041003"


def verificar_acceso() -> bool:
    if st.session_state.get("acceso_autorizado"):
        return True

    st.title("Acceso")
    st.caption("Ingresa la clave para abrir la aplicación.")
    with st.form("acceso_app"):
        clave = st.text_input("Clave", type="password")
        entrar = st.form_submit_button("Entrar", use_container_width=True)
        if entrar:
            if clave == CLAVE_ACCESO_APP:
                st.session_state["acceso_autorizado"] = True
                st.rerun()
            st.error("Clave incorrecta.")
    return False


if not verificar_acceso():
    st.stop()


def clave_foto_evidencia_actual() -> str:
    version = st.session_state.get("evidencia_foto_version", 0)
    return f"evidencia_foto_{version}"


def obtener_foto_evidencia_bytes(foto_widget=None):
    foto = foto_widget if foto_widget is not None else st.session_state.get(clave_foto_evidencia_actual())
    if foto is None:
        return None
    try:
        return foto.getvalue()
    except Exception:
        return None


def sincronizar_foto_rapida():
    foto = st.session_state.get(clave_foto_evidencia_actual())
    if foto is None:
        st.session_state["evidencia_foto_bytes"] = None
        return
    try:
        st.session_state["evidencia_foto_bytes"] = foto.getvalue()
    except Exception:
        st.session_state["evidencia_foto_bytes"] = None


def limpiar_evidencia_pendiente():
    st.session_state["limpiar_evidencia_pendiente"] = True


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


def tabla_movimientos(registros, evidencias):
    evidencias_por_clave = {evidencia.registro_clave: evidencia for evidencia in evidencias}
    return [
        {
            "Fecha": formatear_fecha_visible(registro.fecha),
            "Hora": formatear_hora_visible(registro.hora),
            "Tipo": registro.tipo.capitalize(),
            "Turno": registro.turno,
            "Jornada": formatear_fecha_visible(registro.jornada),
            "Detalle": registro.detalle,
            "Evidencia": "Si" if clave_registro(registro) in evidencias_por_clave else "No",
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


def tabla_evidencias(evidencias):
    return [
        {
            "Fecha": formatear_fecha_visible(evidencia.fecha),
            "Hora": formatear_hora_visible(evidencia.hora),
            "Tipo": evidencia.tipo.capitalize(),
            "Turno": evidencia.turno,
            "Observación": evidencia.ubicacion_texto or "-",
            "Foto": "Ver foto" if (evidencia.foto_url or evidencia.foto_nombre) else "Sin foto",
        }
        for evidencia in evidencias
    ]


def render_galeria_evidencias(evidencias):
    evidencias_con_foto = [
        evidencia
        for evidencia in evidencias
        if (evidencia.foto_url or evidencia.foto_nombre)
    ]
    if not evidencias_con_foto:
        return

    st.caption("Vista rápida de fotos")
    for indice, evidencia in enumerate(evidencias_con_foto, start=1):
        titulo = (
            f"{indice}. {formatear_fecha_visible(evidencia.fecha)} "
            f"{formatear_hora_visible(evidencia.hora)} | "
            f"{evidencia.tipo.capitalize()} | {evidencia.turno}"
        )
        with st.expander(titulo):
            if evidencia.ubicacion_texto:
                st.write(f"Observación: {evidencia.ubicacion_texto}")
            if evidencia.foto_url:
                st.image(evidencia.foto_url, use_container_width=True)
                st.link_button("Abrir foto", evidencia.foto_url, use_container_width=True)
            else:
                st.caption(evidencia.foto_nombre)


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

if "evidencia_foto_version" not in st.session_state:
    st.session_state["evidencia_foto_version"] = 0

if st.session_state.get("limpiar_evidencia_pendiente"):
    st.session_state["evidencia_observacion"] = ""
    st.session_state["usar_evidencia_rapida"] = False
    st.session_state["evidencia_foto_bytes"] = None
    st.session_state["evidencia_foto_version"] += 1
    st.session_state["limpiar_evidencia_pendiente"] = False

ahora = datetime.now()

col_a, col_b = st.columns([1, 1], gap="small")

with col_a:
    st.subheader("Registro rápido")
    turno_rapido = st.selectbox(
        "Turno actual",
        options=["12h dia", "12h noche", "5h manana"],
        index=["12h dia", "12h noche", "5h manana"].index(turno_actual_por_hora())
        if turno_actual_por_hora() in ["12h dia", "12h noche", "5h manana"]
        else 0,
    )
    usar_evidencia_rapida = st.checkbox(
        "Agregar evidencia",
        key="usar_evidencia_rapida",
    )
    foto_rapida_widget = None
    if usar_evidencia_rapida:
        evidencia_col_1, evidencia_col_2 = st.columns([0.9, 1.1], gap="small")
        with evidencia_col_1:
            foto_rapida_widget = st.camera_input(
                "Foto opcional",
                key=clave_foto_evidencia_actual(),
                on_change=sincronizar_foto_rapida,
            )
            if foto_rapida_widget is not None:
                try:
                    st.session_state["evidencia_foto_bytes"] = foto_rapida_widget.getvalue()
                except Exception:
                    st.session_state["evidencia_foto_bytes"] = None
        with evidencia_col_2:
            st.text_area(
                "Observación (opcional)",
                key="evidencia_observacion",
                placeholder="Opcional",
                height=90,
            )
            if st.session_state.get("evidencia_foto_bytes"):
                st.caption("Foto lista para guardar.")
    elif not usar_cloudinary() and not os.environ.get("GOOGLE_DRIVE_FOLDER_ID", "").strip():
        st.caption("Si activas evidencia, primero debes configurar almacenamiento de fotos.")
    col_1, col_2 = st.columns(2)
    enviar_entrada = col_1.button("Registrar entrada", use_container_width=True)
    enviar_salida = col_2.button("Registrar salida", use_container_width=True)

    if enviar_entrada:
        registro = guardar_registro(tipo="entrada", turno=turno_rapido)
        if st.session_state.get("usar_evidencia_rapida"):
            try:
                evidencia_guardada = guardar_evidencia_registro(
                    registro,
                    ubicacion_texto=st.session_state.get("evidencia_observacion", ""),
                    foto_bytes=st.session_state.get("evidencia_foto_bytes") or obtener_foto_evidencia_bytes(foto_rapida_widget),
                )
                if evidencia_guardada is None:
                    st.info("No se detectó foto ni observación, así que no se creó evidencia.")
                else:
                    st.success("Evidencia guardada con este registro.")
            except Exception as exc:
                st.warning(f"El registro se guardo, pero la evidencia fotografica no se pudo subir: {exc}")
        limpiar_evidencia_pendiente()
        st.success(
            f"Entrada guardada: {formatear_fecha_visible(registro.fecha)} "
            f"{registro.hora} ({registro.turno})"
        )
        st.rerun()
    if enviar_salida:
        registro = guardar_registro(tipo="salida", turno=turno_rapido)
        if st.session_state.get("usar_evidencia_rapida"):
            try:
                evidencia_guardada = guardar_evidencia_registro(
                    registro,
                    ubicacion_texto=st.session_state.get("evidencia_observacion", ""),
                    foto_bytes=st.session_state.get("evidencia_foto_bytes") or obtener_foto_evidencia_bytes(foto_rapida_widget),
                )
                if evidencia_guardada is None:
                    st.info("No se detectó foto ni observación, así que no se creó evidencia.")
                else:
                    st.success("Evidencia guardada con este registro.")
            except Exception as exc:
                st.warning(f"El registro se guardo, pero la evidencia fotografica no se pudo subir: {exc}")
        limpiar_evidencia_pendiente()
        st.success(
            f"Salida guardada: {formatear_fecha_visible(registro.fecha)} "
            f"{registro.hora} ({registro.turno})"
        )
        st.rerun()

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
    evidencias = leer_evidencias()
except Exception as exc:
    st.error(
        "No se pudo abrir la base de datos de Google Sheets. "
        "Revisa la clave privada actual de la cuenta de servicio en Streamlit Secrets."
    )
    st.caption(str(exc))
    st.stop()

periodos = periodos_combinados(registros, estados)
periodo_actual = calcular_periodo(ahora_colombia())
periodo_siguiente = calcular_periodo(ahora_colombia() + timedelta(days=30))
if periodo_actual not in periodos:
    periodos.append(periodo_actual)
if periodo_siguiente not in periodos:
    periodos.append(periodo_siguiente)
periodos = [TODOS_LOS_PERIODOS] + sorted([item for item in periodos if item != TODOS_LOS_PERIODOS])

if "periodo_filtro" not in st.session_state or st.session_state["periodo_filtro"] not in periodos:
    st.session_state["periodo_filtro"] = periodo_actual if periodo_actual in periodos else periodos[0]

col_periodo_1, col_periodo_2, col_periodo_3 = st.columns([2, 1, 1], gap="small")
with col_periodo_1:
    periodo_filtro = st.selectbox(
        "Ver periodo",
        options=periodos,
        index=periodos.index(st.session_state["periodo_filtro"]),
        format_func=formatear_periodo_visible,
        key="periodo_filtro",
    )
with col_periodo_2:
    if st.button("Periodo actual", use_container_width=True):
        st.session_state["periodo_filtro"] = periodo_actual
        st.rerun()
with col_periodo_3:
    if st.button("Proximo periodo", use_container_width=True):
        st.session_state["periodo_filtro"] = periodo_siguiente
        st.rerun()

registros_vista = registros_filtrados(registros, periodo_filtro)
estados_vista = estados_filtrados(estados, periodo_filtro)
evidencias_vista = [
    evidencia
    for evidencia in evidencias
    if periodo_filtro == TODOS_LOS_PERIODOS or evidencia.periodo == periodo_filtro
]
claves_registros_vista = {clave_registro(registro) for registro in registros_vista}
evidencias_vista = [evidencia for evidencia in evidencias_vista if evidencia.registro_clave in claves_registros_vista]
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
    st.dataframe(tabla_estados(estados_vista), use_container_width=True, hide_index=True)
    if filas_servicio:
        st.caption("Organizado por servicio / detalle")
        st.dataframe(filas_servicio, use_container_width=True, hide_index=True)
    st.metric(etiqueta_horas_programadas, horas_plan_total_texto(total_minutos_programados))
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
st.dataframe(tabla_movimientos(registros_vista, evidencias_vista), use_container_width=True, hide_index=True)
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

st.subheader("Evidencias registradas")
if evidencias_vista:
    st.dataframe(tabla_evidencias(evidencias_vista), use_container_width=True, hide_index=True)
    render_galeria_evidencias(evidencias_vista)
else:
    st.info("No hay evidencias guardadas en este filtro.")

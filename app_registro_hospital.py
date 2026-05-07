from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from functools import lru_cache
from html import escape
import json
import os
from pathlib import Path
import re
import shutil
import time as time_module
from zoneinfo import ZoneInfo


BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "historial_registros.csv"
STATE_FILE = BASE_DIR / "estados_dia.csv"
BACKUP_DIR = BASE_DIR / "copias_seguridad"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
COLOMBIA_TZ = ZoneInfo("America/Bogota")
TODOS_LOS_PERIODOS = "Todos los periodos"
COLUMNAS_ARCHIVO = ["fecha", "hora", "tipo", "detalle", "periodo", "turno", "jornada"]
COLUMNAS_ESTADOS = ["fecha", "estado", "detalle", "periodo"]
ESTADOS_DIA = [
    "12h dia",
    "12h noche",
    "5h manana",
    "libre",
    "libre despues de noche",
    "sin definir",
]
TURNOS = {
    "12h dia": {
        "duracion_minutos": 12 * 60,
        "salida_permitida_minutos": 60,
        "inicio": (7, 0),
        "fin": (19, 0),
    },
    "12h noche": {
        "duracion_minutos": 12 * 60,
        "salida_permitida_minutos": 60,
        "inicio": (19, 0),
        "fin": (7, 0),
    },
    "5h manana": {
        "duracion_minutos": 5 * 60,
        "salida_permitida_minutos": 0,
        "inicio": (7, 0),
        "fin": (12, 0),
    },
    "libre": {
        "duracion_minutos": 0,
        "salida_permitida_minutos": 0,
        "inicio": None,
        "fin": None,
    },
    "sin definir": {
        "duracion_minutos": 0,
        "salida_permitida_minutos": 0,
        "inicio": None,
        "fin": None,
    },
}
ESTADOS_CON_TURNO = {"12h dia", "12h noche", "5h manana"}

tk = None
filedialog = None
messagebox = None
ttk = None
GOOGLE_WORKSHEETS_INICIALIZADAS: set[tuple[str, str]] = set()
GOOGLE_WORKSHEET_CACHE: dict[tuple[str, str], object] = {}


def cargar_ui_escritorio():
    global tk, filedialog, messagebox, ttk
    if tk is not None:
        return

    import tkinter as tkinter_mod
    from tkinter import filedialog as filedialog_mod
    from tkinter import messagebox as messagebox_mod
    from tkinter import ttk as ttk_mod

    tk = tkinter_mod
    filedialog = filedialog_mod
    messagebox = messagebox_mod
    ttk = ttk_mod


@dataclass
class Registro:
    fecha: str
    hora: str
    tipo: str
    detalle: str
    periodo: str
    turno: str
    jornada: str

    @property
    def fecha_hora(self) -> datetime:
        return parsear_fecha_hora_registro(self.fecha, self.hora)


@dataclass
class ResumenJornada:
    jornada: str
    periodo: str
    turno: str
    horario: str
    minutos_programados: int
    minutos_dentro: int
    minutos_fuera: int
    minutos_permitidos: int
    minutos_exceso: int
    estado: str


@dataclass
class EstadoDia:
    fecha: str
    estado: str
    detalle: str
    periodo: str

    @property
    def fecha_base(self) -> date:
        return datetime.strptime(self.fecha, "%Y-%m-%d").date()


def ahora_colombia() -> datetime:
    return datetime.now(COLOMBIA_TZ)


def turno_actual_por_hora() -> str:
    hora = ahora_colombia().hour
    if hora >= 19 or hora < 7:
        return "12h noche"
    return "12h dia"


def calcular_periodo(fecha_hora: datetime) -> str:
    if fecha_hora.day >= 21:
        inicio = fecha_hora.replace(day=21)
        if fecha_hora.month == 12:
            fin = fecha_hora.replace(year=fecha_hora.year + 1, month=1, day=20)
        else:
            fin = fecha_hora.replace(month=fecha_hora.month + 1, day=20)
    else:
        fin = fecha_hora.replace(day=20)
        if fecha_hora.month == 1:
            inicio = fecha_hora.replace(year=fecha_hora.year - 1, month=12, day=21)
        else:
            inicio = fecha_hora.replace(month=fecha_hora.month - 1, day=21)

    return f"{inicio.strftime('%Y-%m-%d')} al {fin.strftime('%Y-%m-%d')}"


def calcular_jornada(turno: str, fecha_hora: datetime) -> str:
    if turno == "12h noche":
        fecha_base = fecha_hora.date() if fecha_hora.hour >= 19 else (fecha_hora - timedelta(days=1)).date()
        return fecha_base.strftime("%Y-%m-%d")
    return fecha_hora.strftime("%Y-%m-%d")


def inicio_fin_jornada(turno: str, jornada: str) -> tuple[datetime | None, datetime | None]:
    config = TURNOS.get(turno, TURNOS["sin definir"])
    if config["inicio"] is None or config["fin"] is None:
        return None, None

    fecha_base = datetime.strptime(jornada, "%Y-%m-%d").replace(tzinfo=COLOMBIA_TZ)
    hora_inicio, minuto_inicio = config["inicio"]
    hora_fin, minuto_fin = config["fin"]

    inicio = fecha_base.replace(hour=hora_inicio, minute=minuto_inicio, second=0)
    fin = fecha_base.replace(hour=hora_fin, minute=minuto_fin, second=0)
    if turno == "12h noche":
        fin += timedelta(days=1)
    return inicio, fin


def formato_horario(turno: str, jornada: str) -> str:
    inicio, fin = inicio_fin_jornada(turno, jornada)
    if not inicio or not fin:
        return "-"
    return f"{inicio.strftime('%Y-%m-%d %H:%M')} a {fin.strftime('%Y-%m-%d %H:%M')}"


def minutos_a_texto(minutos: int) -> str:
    signo = "-" if minutos < 0 else ""
    minutos = abs(minutos)
    horas = minutos // 60
    resto = minutos % 60
    return f"{signo}{horas:02d}:{resto:02d}"


def formatear_hora_visible(hora: str) -> str:
    hora = hora.strip()
    if len(hora) >= 5:
        return hora[:5]
    return hora


def parsear_fecha_hora_registro(fecha: str, hora: str) -> datetime:
    fecha = fecha.strip()
    hora = hora.strip()
    formatos = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M")
    ultimo_error = None
    for formato in formatos:
        try:
            return datetime.strptime(f"{fecha} {hora}", formato).replace(tzinfo=COLOMBIA_TZ)
        except ValueError as exc:
            ultimo_error = exc
    raise ValueError(f"Fecha u hora de registro invalida: {fecha} {hora}") from ultimo_error


def validar_bloqueo_dia_libre(registros: list[Registro], tipo: str, fecha_hora: datetime):
    fecha_texto = fecha_hora.strftime("%Y-%m-%d")
    registros_dia = [registro for registro in registros if registro.fecha == fecha_texto]

    if tipo == "libre":
        if any(registro.tipo == "libre" for registro in registros_dia):
            raise ValueError("Ese día ya está marcado como libre.")
        if any(registro.tipo != "libre" for registro in registros_dia):
            raise ValueError("No puedes marcar libre un día que ya tiene entradas o salidas.")
        return

    if any(registro.tipo == "libre" for registro in registros_dia):
        raise ValueError("Ese día está bloqueado como libre y no admite más registros.")


def construir_fecha_hora_manual(fecha: date | datetime | str, hora: time | str) -> datetime:
    if isinstance(fecha, datetime):
        fecha_base = fecha.date()
    elif isinstance(fecha, date):
        fecha_base = fecha
    elif isinstance(fecha, str):
        fecha_base = datetime.strptime(fecha, "%Y-%m-%d").date()
    else:
        raise ValueError("Fecha manual inválida.")

    if isinstance(hora, time):
        hora_base = hora
    elif isinstance(hora, str):
        hora_texto = hora.strip()
        if hora_texto.isdigit() and len(hora_texto) in {3, 4}:
            hora_texto = hora_texto.zfill(4)
            hora_texto = f"{hora_texto[:2]}:{hora_texto[2:]}"

        formatos = ("%H:%M:%S", "%H:%M")
        ultimo_error = None
        for formato in formatos:
            try:
                hora_base = datetime.strptime(hora_texto, formato).time()
                break
            except ValueError as exc:
                ultimo_error = exc
        else:
            raise ValueError("La hora debe tener formato HH:MM o HHMM.") from ultimo_error
    else:
        raise ValueError("Hora manual inválida.")

    return datetime.combine(fecha_base, hora_base).replace(tzinfo=COLOMBIA_TZ)


def asegurar_archivo():
    BACKUP_DIR.mkdir(exist_ok=True)
    if usar_google_sheets():
        if not _hojas_google_listas():
            asegurar_hojas_google()
        return
    if not DATA_FILE.exists():
        with DATA_FILE.open("w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(COLUMNAS_ARCHIVO)
    asegurar_archivo_estados()
    normalizar_archivo_existente()


def asegurar_archivo_estados():
    if usar_google_sheets():
        if not _hojas_google_listas():
            asegurar_hojas_google()
        return
    if not STATE_FILE.exists():
        with STATE_FILE.open("w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(COLUMNAS_ESTADOS)


def usar_google_sheets() -> bool:
    return bool(
        _normalizar_google_sheet_id(os.environ.get("GOOGLE_SHEET_ID", ""))
        and os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    )


def _normalizar_google_sheet_id(value: str) -> str:
    texto = str(value or "").strip()
    if not texto:
        return ""
    patron = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", texto)
    if patron:
        return patron.group(1)
    patron = re.search(r"^[a-zA-Z0-9-_]{20,}$", texto)
    if patron:
        return patron.group(0)
    return texto


@lru_cache(maxsize=2)
def _google_client_desde_json(credenciales_json: str):
    import gspread

    credenciales = json.loads(credenciales_json)
    return gspread.service_account_from_dict(credenciales)


def _google_client():
    return _google_client_desde_json(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])


@lru_cache(maxsize=4)
def _google_sheet_desde_id(sheet_id: str, credenciales_json: str):
    client = _google_client_desde_json(credenciales_json)
    return client.open_by_key(sheet_id)


def _google_sheet():
    sheet_id = _normalizar_google_sheet_id(os.environ["GOOGLE_SHEET_ID"])
    credenciales_json = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
    try:
        return _google_sheet_desde_id(sheet_id, credenciales_json)
    except Exception as exc:
        raise RuntimeError(
            "No se pudo abrir la Google Sheet. Revisa el sheet id/url, "
            "que la hoja este compartida con la cuenta de servicio como Editor "
            "y que los Secrets de Streamlit sigan vigentes."
        ) from exc


def _obtener_worksheet(nombre: str, headers: list[str]):
    libro = _google_sheet()
    sheet_id = _normalizar_google_sheet_id(os.environ["GOOGLE_SHEET_ID"])
    cache_key = (sheet_id, nombre)
    if cache_key in GOOGLE_WORKSHEET_CACHE:
        return GOOGLE_WORKSHEET_CACHE[cache_key]

    try:
        hoja = libro.worksheet(nombre)
        GOOGLE_WORKSHEETS_INICIALIZADAS.add(cache_key)
        GOOGLE_WORKSHEET_CACHE[cache_key] = hoja
        return hoja
    except Exception:
        try:
            hoja = libro.add_worksheet(title=nombre, rows=1000, cols=max(len(headers), 6))
            hoja.append_row(headers)
            GOOGLE_WORKSHEETS_INICIALIZADAS.add(cache_key)
            GOOGLE_WORKSHEET_CACHE[cache_key] = hoja
            return hoja
        except Exception:
            # If another request created the worksheet first, fetch it again.
            hoja = libro.worksheet(nombre)
    GOOGLE_WORKSHEETS_INICIALIZADAS.add(cache_key)
    GOOGLE_WORKSHEET_CACHE[cache_key] = hoja
    return hoja


def asegurar_hojas_google():
    _obtener_worksheet("movimientos", COLUMNAS_ARCHIVO)
    _obtener_worksheet("estados", COLUMNAS_ESTADOS)


def _hojas_google_listas() -> bool:
    if not usar_google_sheets():
        return False
    sheet_id = _normalizar_google_sheet_id(os.environ["GOOGLE_SHEET_ID"])
    requeridas = {(sheet_id, "movimientos"), (sheet_id, "estados")}
    return requeridas.issubset(GOOGLE_WORKSHEETS_INICIALIZADAS) and requeridas.issubset(set(GOOGLE_WORKSHEET_CACHE))


def _google_con_reintento(func, *args, **kwargs):
    ultimo_error = None
    for intento in range(3):
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            ultimo_error = exc
            if intento == 2:
                raise
            time_module.sleep(1 + intento)
    raise ultimo_error


def _reescribir_worksheet(hoja, headers: list[str], filas: list[list[str]]):
    valores = [headers, *filas]
    _google_con_reintento(hoja.clear)
    _google_con_reintento(hoja.update, range_name="A1", values=valores)


def normalizar_archivo_existente():
    with DATA_FILE.open("r", newline="", encoding="utf-8") as file:
        filas = list(csv.reader(file))

    if not filas:
        with DATA_FILE.open("w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(COLUMNAS_ARCHIVO)
        return

    encabezado = filas[0]
    if encabezado == COLUMNAS_ARCHIVO:
        return

    respaldo = BACKUP_DIR / f"historial_registros_migracion_{ahora_colombia().strftime('%Y%m%d_%H%M%S')}.csv"
    shutil.copy2(DATA_FILE, respaldo)

    registros_convertidos: list[Registro] = []
    for fila in filas[1:]:
        mapa = dict(zip(encabezado, fila))
        fecha = mapa.get("fecha", "")
        hora = mapa.get("hora", "")
        tipo = mapa.get("tipo", "")
        detalle = mapa.get("detalle", "")
        turno = mapa.get("turno", "") or ("libre" if tipo == "libre" else "sin definir")

        if fecha and hora:
            fecha_hora = parsear_fecha_hora_registro(fecha, hora)
            periodo = mapa.get("periodo", "") or calcular_periodo(fecha_hora)
            jornada = mapa.get("jornada", "") or calcular_jornada(turno, fecha_hora)
        else:
            periodo = mapa.get("periodo", "")
            jornada = mapa.get("jornada", "")

        registros_convertidos.append(
            Registro(
                fecha=fecha,
                hora=hora,
                tipo=tipo,
                detalle=detalle,
                periodo=periodo,
                turno=turno,
                jornada=jornada,
            )
        )

    with DATA_FILE.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(COLUMNAS_ARCHIVO)
        for registro in registros_convertidos:
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


def guardar_registro(tipo: str, turno: str, detalle: str = "") -> Registro:
    return guardar_registro_en_fecha(tipo=tipo, fecha_hora=ahora_colombia(), turno=turno, detalle=detalle)


def guardar_registro_en_fecha(tipo: str, fecha_hora: datetime, turno: str, detalle: str = "") -> Registro:
    turno_normalizado = turno if turno in TURNOS else "sin definir"
    validar_bloqueo_dia_libre(leer_registros(), tipo, fecha_hora)
    periodo = calcular_periodo(fecha_hora)
    jornada = calcular_jornada(turno_normalizado, fecha_hora)
    registro = Registro(
        fecha=fecha_hora.strftime("%Y-%m-%d"),
        hora=fecha_hora.strftime("%H:%M"),
        tipo=tipo,
        detalle=detalle,
        periodo=periodo,
        turno=turno_normalizado,
        jornada=jornada,
    )

    if usar_google_sheets():
        hoja = _obtener_worksheet("movimientos", COLUMNAS_ARCHIVO)
        _google_con_reintento(
            hoja.append_row,
            [
                registro.fecha,
                registro.hora,
                registro.tipo,
                registro.detalle,
                registro.periodo,
                registro.turno,
                registro.jornada,
            ],
        )
        return registro

    with DATA_FILE.open("a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
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

    crear_copia_seguridad()
    return registro


def eliminar_registro(registro_objetivo: Registro) -> bool:
    registros = leer_registros()
    eliminado = False
    restantes: list[Registro] = []

    for registro in registros:
        if not eliminado and registro == registro_objetivo:
            eliminado = True
            continue
        restantes.append(registro)

    if not eliminado:
        return False

    if usar_google_sheets():
        hoja = _obtener_worksheet("movimientos", COLUMNAS_ARCHIVO)
        _reescribir_worksheet(
            hoja,
            COLUMNAS_ARCHIVO,
            [
                [
                    registro.fecha,
                    registro.hora,
                    registro.tipo,
                    registro.detalle,
                    registro.periodo,
                    registro.turno,
                    registro.jornada,
                ]
                for registro in restantes
            ],
        )
        return True

    with DATA_FILE.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(COLUMNAS_ARCHIVO)
        for registro in restantes:
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

    crear_copia_seguridad()
    return True


def leer_registros() -> list[Registro]:
    asegurar_archivo()
    registros: list[Registro] = []

    if usar_google_sheets():
        hoja = _obtener_worksheet("movimientos", COLUMNAS_ARCHIVO)
        filas = _google_con_reintento(hoja.get_all_records)
        for row in filas:
            fecha = str(row.get("fecha", "")).strip()
            hora = str(row.get("hora", "")).strip()
            tipo = str(row.get("tipo", "")).strip()
            if not fecha or not hora or not tipo:
                continue
            turno = str(row.get("turno", "")).strip() or ("libre" if tipo == "libre" else "sin definir")
            fecha_hora = parsear_fecha_hora_registro(fecha, hora)
            registros.append(
                Registro(
                    fecha=fecha,
                    hora=hora,
                    tipo=tipo,
                    detalle=str(row.get("detalle", "")).strip(),
                    periodo=str(row.get("periodo", "")).strip() or calcular_periodo(fecha_hora),
                    turno=turno,
                    jornada=str(row.get("jornada", "")).strip() or calcular_jornada(turno, fecha_hora),
                )
            )
        registros.sort(key=lambda item: item.fecha_hora)
        return registros

    with DATA_FILE.open("r", newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        for row in reader:
            fecha = row.get("fecha", "")
            hora = row.get("hora", "")
            tipo = row.get("tipo", "")
            turno = row.get("turno", "") or ("libre" if tipo == "libre" else "sin definir")
            fecha_hora = None
            if fecha and hora:
                fecha_hora = parsear_fecha_hora_registro(fecha, hora)

            registros.append(
                Registro(
                    fecha=fecha,
                    hora=hora,
                    tipo=tipo,
                    detalle=row.get("detalle", ""),
                    periodo=row.get("periodo", "") or (calcular_periodo(fecha_hora) if fecha_hora else ""),
                    turno=turno,
                    jornada=row.get("jornada", "") or (calcular_jornada(turno, fecha_hora) if fecha_hora else ""),
                )
            )

    registros.sort(key=lambda item: item.fecha_hora)
    return registros


def crear_copia_seguridad():
    asegurar_archivo()
    if usar_google_sheets():
        return
    fecha_respaldo = ahora_colombia().strftime("%Y%m%d")
    destino = BACKUP_DIR / f"historial_registros_{fecha_respaldo}.csv"
    shutil.copy2(DATA_FILE, destino)


def guardar_estado_dia(fecha: date | str, estado: str, detalle: str = "") -> EstadoDia:
    asegurar_archivo_estados()
    if estado not in ESTADOS_DIA:
        raise ValueError("Estado del dia invalido.")

    if isinstance(fecha, date):
        fecha_texto = fecha.strftime("%Y-%m-%d")
        fecha_base = fecha
    elif isinstance(fecha, str):
        fecha_texto = fecha.strip()
        fecha_base = datetime.strptime(fecha_texto, "%Y-%m-%d").date()
    else:
        raise ValueError("Fecha del estado invalida.")

    periodo = calcular_periodo(datetime.combine(fecha_base, time(0, 0)).replace(tzinfo=COLOMBIA_TZ))
    estado_dia = EstadoDia(fecha=fecha_texto, estado=estado, detalle=detalle.strip(), periodo=periodo)

    estados = leer_estados_dia()
    actualizados = [item for item in estados if item.fecha != fecha_texto]
    actualizados.append(estado_dia)
    actualizados.sort(key=lambda item: item.fecha)

    if usar_google_sheets():
        hoja = _obtener_worksheet("estados", COLUMNAS_ESTADOS)
        _reescribir_worksheet(
            hoja,
            COLUMNAS_ESTADOS,
            [[item.fecha, item.estado, item.detalle, item.periodo] for item in actualizados],
        )
        return estado_dia

    with STATE_FILE.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(COLUMNAS_ESTADOS)
        for item in actualizados:
            writer.writerow([item.fecha, item.estado, item.detalle, item.periodo])

    return estado_dia


def eliminar_estado_dia(fecha: date | str) -> bool:
    if isinstance(fecha, date):
        fecha_texto = fecha.strftime("%Y-%m-%d")
    elif isinstance(fecha, str):
        fecha_texto = fecha.strip()
    else:
        return False

    estados = leer_estados_dia()
    restantes = [item for item in estados if item.fecha != fecha_texto]
    if len(restantes) == len(estados):
        return False

    if usar_google_sheets():
        hoja = _obtener_worksheet("estados", COLUMNAS_ESTADOS)
        _reescribir_worksheet(
            hoja,
            COLUMNAS_ESTADOS,
            [[item.fecha, item.estado, item.detalle, item.periodo] for item in restantes],
        )
        return True

    with STATE_FILE.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(COLUMNAS_ESTADOS)
        for item in restantes:
            writer.writerow([item.fecha, item.estado, item.detalle, item.periodo])

    return True


def leer_estados_dia() -> list[EstadoDia]:
    asegurar_archivo_estados()
    estados: list[EstadoDia] = []

    if usar_google_sheets():
        hoja = _obtener_worksheet("estados", COLUMNAS_ESTADOS)
        for row in _google_con_reintento(hoja.get_all_records):
            fecha = str(row.get("fecha", "")).strip()
            if not fecha:
                continue
            estado = str(row.get("estado", "")).strip() or "sin definir"
            detalle = str(row.get("detalle", "")).strip()
            periodo = str(row.get("periodo", "")).strip()
            if not periodo:
                fecha_base = datetime.strptime(fecha, "%Y-%m-%d").date()
                periodo = calcular_periodo(datetime.combine(fecha_base, time(0, 0)).replace(tzinfo=COLOMBIA_TZ))
            estados.append(EstadoDia(fecha=fecha, estado=estado, detalle=detalle, periodo=periodo))
        estados.sort(key=lambda item: item.fecha)
        return estados

    with STATE_FILE.open("r", newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        for row in reader:
            fecha = row.get("fecha", "").strip()
            if not fecha:
                continue
            estado = row.get("estado", "").strip() or "sin definir"
            detalle = row.get("detalle", "").strip()
            periodo = row.get("periodo", "").strip()
            if not periodo:
                fecha_base = datetime.strptime(fecha, "%Y-%m-%d").date()
                periodo = calcular_periodo(datetime.combine(fecha_base, time(0, 0)).replace(tzinfo=COLOMBIA_TZ))
            estados.append(EstadoDia(fecha=fecha, estado=estado, detalle=detalle, periodo=periodo))

    estados.sort(key=lambda item: item.fecha)
    return estados


def periodos_disponibles(registros: list[Registro]) -> list[str]:
    periodos = sorted({registro.periodo for registro in registros if registro.periodo})
    return [TODOS_LOS_PERIODOS, *periodos]


def periodos_combinados(registros: list[Registro], estados: list[EstadoDia]) -> list[str]:
    periodos = sorted(
        {registro.periodo for registro in registros if registro.periodo}
        | {estado.periodo for estado in estados if estado.periodo}
    )
    return [TODOS_LOS_PERIODOS, *periodos]


def agrupar_resumenes_jornada(registros: list[Registro]) -> list[ResumenJornada]:
    grupos: dict[tuple[str, str], list[Registro]] = defaultdict(list)
    for registro in registros:
        if registro.turno not in {"12h dia", "12h noche", "5h manana"}:
            continue
        grupos[(registro.turno, registro.jornada)].append(registro)

    resumenes: list[ResumenJornada] = []
    for (turno, jornada), items in sorted(grupos.items(), key=lambda dato: dato[1][0].fecha_hora):
        items.sort(key=lambda item: item.fecha_hora)
        config = TURNOS[turno]
        minutos_fuera = 0
        salida_abierta: datetime | None = None
        incidencias: list[str] = []
        inicio_jornada, fin_jornada = inicio_fin_jornada(turno, jornada)

        if items and items[0].tipo != "entrada":
            incidencias.append("revisar primera marca")

        for item in items:
            momento = item.fecha_hora
            if item.tipo == "salida":
                if salida_abierta is None:
                    salida_abierta = momento
                else:
                    incidencias.append("salidas consecutivas")
                    salida_abierta = momento
            elif item.tipo == "entrada":
                if salida_abierta is not None:
                    inicio_calculo = max(salida_abierta, inicio_jornada) if inicio_jornada else salida_abierta
                    fin_calculo = min(momento, fin_jornada) if fin_jornada else momento
                    if fin_calculo > inicio_calculo:
                        minutos_fuera += int((fin_calculo - inicio_calculo).total_seconds() // 60)
                    salida_abierta = None

        if salida_abierta is not None:
            if fin_jornada and salida_abierta >= fin_jornada - timedelta(minutes=5):
                salida_abierta = None
            else:
                incidencias.append("ultima salida sin regreso")

        minutos_programados = config["duracion_minutos"]
        minutos_permitidos = config["salida_permitida_minutos"]
        minutos_exceso = max(0, minutos_fuera - minutos_permitidos)
        minutos_dentro = max(0, minutos_programados - minutos_fuera)
        if incidencias:
            estado = ", ".join(dict.fromkeys(incidencias))
        elif minutos_exceso > 0:
            estado = "ok (ojo)"
        else:
            estado = "ok"

        resumenes.append(
            ResumenJornada(
                jornada=jornada,
                periodo=items[0].periodo,
                turno=turno,
                horario=formato_horario(turno, jornada),
                minutos_programados=minutos_programados,
                minutos_dentro=minutos_dentro,
                minutos_fuera=minutos_fuera,
                minutos_permitidos=minutos_permitidos,
                minutos_exceso=minutos_exceso,
                estado=estado,
            )
        )

    return resumenes


def _combinar_estado_resumen(estado_base: str, avisos: list[str]) -> str:
    if not avisos and estado_base in {"ok", "ok (ojo)"}:
        return estado_base

    partes = []
    if estado_base and estado_base != "ok":
        partes.append(estado_base)
    for aviso in avisos:
        if aviso and aviso not in partes:
            partes.append(aviso)
    return "ok" if not partes else ", ".join(partes)


def _turno_programado_vencido(fecha: str, estado_programado: str, referencia: datetime | None = None) -> bool:
    if estado_programado not in ESTADOS_CON_TURNO:
        return False
    referencia = referencia or ahora_colombia()
    _, fin = inicio_fin_jornada(estado_programado, fecha)
    if fin is None:
        return False
    return referencia >= fin


def resumenes_programado_vs_real(
    registros: list[Registro],
    estados: list[EstadoDia],
    referencia: datetime | None = None,
) -> list[tuple[ResumenJornada, str]]:
    referencia = referencia or ahora_colombia()
    resumenes_base = agrupar_resumenes_jornada(registros)
    resumenes_por_jornada = {item.jornada: item for item in resumenes_base}
    estados_por_fecha = {item.fecha: item for item in estados}

    jornadas = sorted(set(resumenes_por_jornada) | set(estados_por_fecha))
    filas: list[tuple[ResumenJornada, str]] = []

    for jornada in jornadas:
        resumen = resumenes_por_jornada.get(jornada)
        estado_dia = estados_por_fecha.get(jornada)
        programado = estado_dia.estado if estado_dia else "sin programar"

        if resumen is not None:
            avisos: list[str] = []
            if estado_dia is None:
                avisos.append("sin programacion")
            elif estado_dia.estado in ESTADOS_CON_TURNO and resumen.turno != estado_dia.estado:
                avisos.append("turno distinto a programado")
            elif estado_dia.estado == "libre":
                avisos.append("movimientos en dia libre")

            filas.append(
                (
                    ResumenJornada(
                        jornada=resumen.jornada,
                        periodo=resumen.periodo,
                        turno=resumen.turno,
                        horario=resumen.horario,
                        minutos_programados=resumen.minutos_programados,
                        minutos_dentro=resumen.minutos_dentro,
                        minutos_fuera=resumen.minutos_fuera,
                        minutos_permitidos=resumen.minutos_permitidos,
                        minutos_exceso=resumen.minutos_exceso,
                        estado=_combinar_estado_resumen(resumen.estado, avisos),
                    ),
                    programado,
                )
            )
            continue

        if estado_dia is None:
            continue

        if estado_dia.estado in ESTADOS_CON_TURNO and _turno_programado_vencido(jornada, estado_dia.estado, referencia):
            config = TURNOS[estado_dia.estado]
            filas.append(
                (
                    ResumenJornada(
                        jornada=jornada,
                        periodo=estado_dia.periodo,
                        turno="sin registros",
                        horario=formato_horario(estado_dia.estado, jornada),
                        minutos_programados=config["duracion_minutos"],
                        minutos_dentro=0,
                        minutos_fuera=0,
                        minutos_permitidos=config["salida_permitida_minutos"],
                        minutos_exceso=0,
                        estado="sin registros para turno programado",
                    ),
                    estado_dia.estado,
                )
            )
        elif estado_dia.estado == "libre" and datetime.strptime(jornada, "%Y-%m-%d").date() <= referencia.date():
            filas.append(
                (
                    ResumenJornada(
                        jornada=jornada,
                        periodo=estado_dia.periodo,
                        turno="sin registros",
                        horario="Libre",
                        minutos_programados=0,
                        minutos_dentro=0,
                        minutos_fuera=0,
                        minutos_permitidos=0,
                        minutos_exceso=0,
                        estado="libre",
                    ),
                    estado_dia.estado,
                )
            )

    return filas


def resumir_periodo(registros: list[Registro]) -> dict[str, int]:
    resumenes = agrupar_resumenes_jornada(registros)
    return {
        "turnos": len(resumenes),
        "programados": sum(item.minutos_programados for item in resumenes),
        "dentro": sum(item.minutos_dentro for item in resumenes),
        "fuera": sum(item.minutos_fuera for item in resumenes),
        "permitidos": sum(item.minutos_permitidos for item in resumenes),
        "exceso": sum(item.minutos_exceso for item in resumenes),
        "sin_turno": len([item for item in registros if item.turno == "sin definir"]),
    }


def resumen_total_jornadas(resumenes: list[ResumenJornada]) -> ResumenJornada:
    total_programado = sum(item.minutos_programados for item in resumenes)
    total_dentro = sum(item.minutos_dentro for item in resumenes)
    total_fuera = sum(item.minutos_fuera for item in resumenes)
    total_permitido = sum(item.minutos_permitidos for item in resumenes)
    total_exceso = sum(item.minutos_exceso for item in resumenes)
    turnos_reales = sum(1 for item in resumenes if item.minutos_programados > 0)
    estado_total = "ok" if total_fuera <= total_permitido else "revisar"

    return ResumenJornada(
        jornada="TOTAL",
        periodo=resumenes[0].periodo if resumenes else "",
        turno=f"{turnos_reales} turnos",
        horario=f"Acumulado trabajado: {minutos_a_texto(total_dentro)}",
        minutos_programados=total_programado,
        minutos_dentro=total_dentro,
        minutos_fuera=total_fuera,
        minutos_permitidos=total_permitido,
        minutos_exceso=total_exceso,
        estado=estado_total,
    )


def exportar_csv(destino: Path, registros: list[Registro]):
    with destino.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(COLUMNAS_ARCHIVO)
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


def exportar_html(destino: Path, registros: list[Registro]):
    por_periodo: dict[str, list[Registro]] = defaultdict(list)
    for registro in registros:
        por_periodo[registro.periodo].append(registro)

    bloques = []
    for periodo in sorted(por_periodo):
        registros_periodo = sorted(por_periodo[periodo], key=lambda item: item.fecha_hora)
        resumen_total = resumir_periodo(registros_periodo)
        resumenes_jornada = agrupar_resumenes_jornada(registros_periodo)

        filas_resumen = []
        for item in resumenes_jornada:
            filas_resumen.append(
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
            )

        filas_movimientos = []
        for mov in registros_periodo:
            filas_movimientos.append(
                "<tr>"
                f"<td>{escape(mov.fecha)}</td>"
                f"<td>{escape(mov.hora)}</td>"
                f"<td>{escape(mov.tipo.capitalize())}</td>"
                f"<td>{escape(mov.turno)}</td>"
                f"<td>{escape(mov.jornada)}</td>"
                f"<td>{escape(mov.detalle)}</td>"
                "</tr>"
            )

        bloques.append(
            f"""
  <section>
    <h2>Periodo {escape(periodo)}</h2>
    <p class="totales">
      Turnos: {resumen_total['turnos']} |
      Programado: {minutos_a_texto(resumen_total['programados'])} |
      Dentro: {minutos_a_texto(resumen_total['dentro'])} |
      Fuera: {minutos_a_texto(resumen_total['fuera'])} |
      Permitido: {minutos_a_texto(resumen_total['permitidos'])} |
      Exceso: {minutos_a_texto(resumen_total['exceso'])}
    </p>
    <h3>Resumen por turno</h3>
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
        {''.join(filas_resumen) if filas_resumen else '<tr><td colspan="8">No hay turnos calculables en este periodo.</td></tr>'}
      </tbody>
    </table>
    <h3>Movimientos registrados</h3>
    <table>
      <thead>
        <tr>
          <th>Fecha</th>
          <th>Hora</th>
          <th>Tipo</th>
          <th>Turno</th>
          <th>Jornada</th>
          <th>Detalle</th>
        </tr>
      </thead>
      <tbody>
        {''.join(filas_movimientos) if filas_movimientos else '<tr><td colspan="6">No hay movimientos.</td></tr>'}
      </tbody>
    </table>
  </section>
"""
        )

    contenido = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <title>Reporte de registros</title>
  <style>
    body {{
      font-family: Arial, sans-serif;
      margin: 32px;
      color: #1f2937;
    }}
    h1, h2, h3 {{
      margin-bottom: 8px;
    }}
    section {{
      margin-top: 28px;
    }}
    p {{
      color: #4b5563;
    }}
    .totales {{
      font-weight: bold;
      color: #111827;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin-top: 12px;
      margin-bottom: 24px;
    }}
    th, td {{
      border: 1px solid #d1d5db;
      padding: 8px;
      text-align: left;
      vertical-align: top;
      font-size: 14px;
    }}
    th {{
      background: #e5eef7;
    }}
  </style>
</head>
<body>
  <h1>Reporte de entradas y salidas</h1>
  <p>Generado en hora de Colombia: {ahora_colombia().strftime("%Y-%m-%d %H:%M:%S")}</p>
  {''.join(bloques) if bloques else '<p>No hay registros todavía.</p>'}
</body>
</html>
"""
    destino.write_text(contenido, encoding="utf-8")


class AppRegistro:
    def __init__(self, root):
        cargar_ui_escritorio()
        self.root = root
        self.root.title("Control personal de entradas y salidas")
        self.root.geometry("1180x860")
        self.root.minsize(1080, 760)

        asegurar_archivo()
        self.turno_rapido_var = tk.StringVar(value=turno_actual_por_hora())
        self.estado_var = tk.StringVar(value="Listo para registrar.")
        self.periodo_var = tk.StringVar(value=f"Periodo actual: {calcular_periodo(ahora_colombia())}")
        self.resumen_var = tk.StringVar(value="")
        self.manual_fecha_var = tk.StringVar(value=ahora_colombia().strftime("%Y-%m-%d"))
        self.manual_hora_var = tk.StringVar(value="")
        self.manual_tipo_var = tk.StringVar(value="entrada")
        self.manual_turno_var = tk.StringVar(value=turno_actual_por_hora())
        self.manual_detalle_var = tk.StringVar(value="")
        self.filtro_periodo_var = tk.StringVar(value=TODOS_LOS_PERIODOS)

        self._construir_interfaz()
        self._cargar_tablas()

    def _construir_interfaz(self):
        marco = ttk.Frame(self.root, padding=16)
        marco.pack(fill="both", expand=True)

        ttk.Label(
            marco,
            text="Registro personal del hospital",
            font=("Helvetica", 20, "bold"),
        ).pack(anchor="w")

        ttk.Label(
            marco,
            text="Guarda tus movimientos por turno y calcula tiempo dentro, fuera y exceso del periodo.",
        ).pack(anchor="w", pady=(4, 16))

        rapido_frame = ttk.LabelFrame(marco, text="Registro rapido del momento", padding=12)
        rapido_frame.pack(fill="x", pady=(0, 12))

        ttk.Label(rapido_frame, text="Turno actual").pack(side="left", padx=(0, 8))
        ttk.Combobox(
            rapido_frame,
            textvariable=self.turno_rapido_var,
            values=("12h dia", "12h noche", "5h manana"),
            state="readonly",
            width=14,
        ).pack(side="left", padx=(0, 14))

        ttk.Button(rapido_frame, text="Registrar entrada", command=lambda: self.registrar("entrada")).pack(
            side="left", padx=(0, 8)
        )
        ttk.Button(rapido_frame, text="Registrar salida", command=lambda: self.registrar("salida")).pack(
            side="left", padx=(0, 8)
        )
        ttk.Button(rapido_frame, text="Registrar libre", command=lambda: self.registrar("libre")).pack(
            side="left", padx=(0, 8)
        )
        ttk.Button(rapido_frame, text="Exportar HTML para imprimir", command=self.exportar_como_html).pack(
            side="right"
        )
        ttk.Button(rapido_frame, text="Exportar CSV", command=self.exportar_como_csv).pack(
            side="right", padx=(0, 8)
        )

        manual_frame = ttk.LabelFrame(marco, text="Registro manual de fecha pasada", padding=12)
        manual_frame.pack(fill="x", pady=(0, 12))

        ttk.Label(manual_frame, text="Fecha").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(manual_frame, textvariable=self.manual_fecha_var, width=14).grid(
            row=1, column=0, sticky="w", padx=(0, 8)
        )

        ttk.Label(manual_frame, text="Hora (HH:MM)").grid(row=0, column=1, sticky="w", padx=(0, 8))
        ttk.Entry(manual_frame, textvariable=self.manual_hora_var, width=12).grid(
            row=1, column=1, sticky="w", padx=(0, 8)
        )

        ttk.Label(manual_frame, text="Tipo").grid(row=0, column=2, sticky="w", padx=(0, 8))
        ttk.Combobox(
            manual_frame,
            textvariable=self.manual_tipo_var,
            values=("entrada", "salida", "libre"),
            state="readonly",
            width=10,
        ).grid(row=1, column=2, sticky="w", padx=(0, 8))

        ttk.Label(manual_frame, text="Turno").grid(row=0, column=3, sticky="w", padx=(0, 8))
        ttk.Combobox(
            manual_frame,
            textvariable=self.manual_turno_var,
            values=("12h dia", "12h noche", "5h manana", "libre"),
            state="readonly",
            width=12,
        ).grid(row=1, column=3, sticky="w", padx=(0, 8))

        ttk.Label(manual_frame, text="Detalle").grid(row=0, column=4, sticky="w", padx=(0, 8))
        ttk.Entry(manual_frame, textvariable=self.manual_detalle_var, width=28).grid(
            row=1, column=4, sticky="ew", padx=(0, 8)
        )

        ttk.Button(manual_frame, text="Guardar manual", command=self.registrar_manual).grid(
            row=1, column=5, sticky="e"
        )
        manual_frame.columnconfigure(4, weight=1)

        ttk.Label(marco, textvariable=self.estado_var, foreground="#1d4ed8").pack(anchor="w", pady=(0, 8))
        ttk.Label(marco, textvariable=self.periodo_var, foreground="#374151").pack(anchor="w", pady=(0, 8))

        filtro_frame = ttk.Frame(marco)
        filtro_frame.pack(fill="x", pady=(0, 10))
        ttk.Label(filtro_frame, text="Ver periodo").pack(side="left", padx=(0, 8))
        self.filtro_combo = ttk.Combobox(
            filtro_frame,
            textvariable=self.filtro_periodo_var,
            state="readonly",
            width=32,
        )
        self.filtro_combo.pack(side="left")
        self.filtro_combo.bind("<<ComboboxSelected>>", lambda event: self._cargar_tablas())

        resumen_frame = ttk.LabelFrame(marco, text="Resumen del periodo filtrado", padding=12)
        resumen_frame.pack(fill="x", pady=(0, 12))
        ttk.Label(
            resumen_frame,
            textvariable=self.resumen_var,
            foreground="#111827",
            justify="left",
        ).pack(anchor="w")

        ttk.Label(marco, text="Resumen por jornada").pack(anchor="w")
        columnas_resumen = (
            "jornada",
            "turno",
            "horario",
            "dentro",
            "fuera",
            "permitido",
            "exceso",
            "estado",
        )
        self.tabla_resumen = ttk.Treeview(marco, columns=columnas_resumen, show="headings", height=8)
        for columna, titulo, ancho in (
            ("jornada", "Jornada", 100),
            ("turno", "Turno", 100),
            ("horario", "Horario", 260),
            ("dentro", "Dentro", 80),
            ("fuera", "Fuera", 80),
            ("permitido", "Permitido", 80),
            ("exceso", "Exceso", 80),
            ("estado", "Estado", 180),
        ):
            self.tabla_resumen.heading(columna, text=titulo)
            self.tabla_resumen.column(columna, width=ancho, anchor="center")
        self.tabla_resumen.pack(fill="x", pady=(4, 14))

        ttk.Label(marco, text="Movimientos registrados").pack(anchor="w")
        columnas = ("fecha", "hora", "tipo", "turno", "jornada", "detalle", "periodo")
        self.tabla = ttk.Treeview(marco, columns=columnas, show="headings", height=14)
        for columna, titulo, ancho, anchor in (
            ("fecha", "Fecha", 95, "center"),
            ("hora", "Hora", 80, "center"),
            ("tipo", "Tipo", 80, "center"),
            ("turno", "Turno", 100, "center"),
            ("jornada", "Jornada", 95, "center"),
            ("detalle", "Detalle", 280, "w"),
            ("periodo", "Periodo", 190, "center"),
        ):
            self.tabla.heading(columna, text=titulo)
            self.tabla.column(columna, width=ancho, anchor=anchor)

        tabla_frame = ttk.Frame(marco)
        tabla_frame.pack(fill="both", expand=True)
        self.tabla.pack(in_=tabla_frame, side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(tabla_frame, orient="vertical", command=self.tabla.yview)
        self.tabla.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")

    def registrar(self, tipo: str):
        turno = "libre" if tipo == "libre" else self.turno_rapido_var.get()
        detalle = "Dia libre" if tipo == "libre" else ""
        registro = guardar_registro(tipo=tipo, turno=turno, detalle=detalle)
        self.periodo_var.set(f"Periodo actual: {calcular_periodo(ahora_colombia())}")
        self.estado_var.set(
            f"Registrado: {registro.tipo.capitalize()} el {registro.fecha} a las {formatear_hora_visible(registro.hora)} en turno {registro.turno}."
        )
        self._cargar_tablas()

    def _registros_filtrados(self, registros: list[Registro]) -> list[Registro]:
        periodo_seleccionado = self.filtro_periodo_var.get()
        if periodo_seleccionado == TODOS_LOS_PERIODOS:
            return registros
        return [registro for registro in registros if registro.periodo == periodo_seleccionado]

    def _cargar_tablas(self):
        for item in self.tabla.get_children():
            self.tabla.delete(item)
        for item in self.tabla_resumen.get_children():
            self.tabla_resumen.delete(item)

        registros = leer_registros()
        self.filtro_combo["values"] = periodos_disponibles(registros)
        if self.filtro_periodo_var.get() not in self.filtro_combo["values"]:
            self.filtro_periodo_var.set(TODOS_LOS_PERIODOS)

        registros_filtrados = self._registros_filtrados(registros)
        resumen_total = resumir_periodo(registros_filtrados)
        self.resumen_var.set(
            " | ".join(
                [
                    f"Turnos calculados: {resumen_total['turnos']}",
                    f"Tiempo programado: {minutos_a_texto(resumen_total['programados'])}",
                    f"Tiempo dentro: {minutos_a_texto(resumen_total['dentro'])}",
                    f"Tiempo fuera: {minutos_a_texto(resumen_total['fuera'])}",
                    f"Salida permitida: {minutos_a_texto(resumen_total['permitidos'])}",
                    f"Exceso a revisar: {minutos_a_texto(resumen_total['exceso'])}",
                    f"Registros sin turno: {resumen_total['sin_turno']}",
                ]
            )
        )

        for item in agrupar_resumenes_jornada(registros_filtrados):
            self.tabla_resumen.insert(
                "",
                "end",
                values=(
                    item.jornada,
                    item.turno,
                    item.horario,
                    minutos_a_texto(item.minutos_dentro),
                    minutos_a_texto(item.minutos_fuera),
                    minutos_a_texto(item.minutos_permitidos),
                    minutos_a_texto(item.minutos_exceso),
                    item.estado,
                ),
            )

        for registro in registros_filtrados:
            self.tabla.insert(
                "",
                "end",
                values=(
                    registro.fecha,
                    formatear_hora_visible(registro.hora),
                    registro.tipo.capitalize(),
                    registro.turno,
                    registro.jornada,
                    registro.detalle,
                    registro.periodo,
                ),
            )

    def registrar_manual(self):
        fecha_texto = self.manual_fecha_var.get().strip()
        hora_texto = self.manual_hora_var.get().strip()
        tipo = self.manual_tipo_var.get().strip().lower()
        turno = self.manual_turno_var.get().strip().lower()
        detalle = self.manual_detalle_var.get().strip()

        if tipo not in {"entrada", "salida", "libre"}:
            messagebox.showerror("Tipo invalido", "El tipo debe ser entrada, salida o libre.")
            return
        if turno not in TURNOS:
            messagebox.showerror("Turno invalido", "Escoge un turno valido.")
            return
        if tipo == "libre":
            turno = "libre"
            if not detalle:
                detalle = "Dia libre"
        elif turno == "libre":
            messagebox.showerror("Turno invalido", "Entrada o salida no pueden quedar con turno libre.")
            return

        try:
            fecha_hora = construir_fecha_hora_manual(fecha_texto, hora_texto)
        except ValueError:
            messagebox.showerror(
                "Fecha u hora invalida",
                "Usa el formato fecha AAAA-MM-DD y hora HH:MM.",
            )
            return

        registro = guardar_registro_en_fecha(tipo=tipo, fecha_hora=fecha_hora, turno=turno, detalle=detalle)
        self.periodo_var.set(f"Periodo actual: {calcular_periodo(ahora_colombia())}")
        self.estado_var.set(
            f"Registrado manual: {registro.tipo.capitalize()} del {registro.fecha} a las {formatear_hora_visible(registro.hora)} en turno {registro.turno}."
        )
        self.manual_detalle_var.set("")
        self._cargar_tablas()

    def exportar_como_csv(self):
        registros = self._registros_filtrados(leer_registros())
        destino = filedialog.asksaveasfilename(
            title="Guardar historial como CSV",
            defaultextension=".csv",
            filetypes=[("Archivo CSV", "*.csv")],
            initialfile="historial_organizado.csv",
        )
        if not destino:
            return

        exportar_csv(Path(destino), registros)
        messagebox.showinfo("Exportacion lista", "Se guardo el historial filtrado en formato CSV.")

    def exportar_como_html(self):
        registros = self._registros_filtrados(leer_registros())
        destino = filedialog.asksaveasfilename(
            title="Guardar reporte para imprimir",
            defaultextension=".html",
            filetypes=[("Archivo HTML", "*.html")],
            initialfile="reporte_para_imprimir.html",
        )
        if not destino:
            return

        exportar_html(Path(destino), registros)
        messagebox.showinfo(
            "Reporte listo",
            "Se guardo el reporte HTML con resumen de turnos y movimientos.",
        )


def main():
    cargar_ui_escritorio()
    root = tk.Tk()
    style = ttk.Style()
    if "clam" in style.theme_names():
        style.theme_use("clam")
    AppRegistro(root)
    root.mainloop()


if __name__ == "__main__":
    main()

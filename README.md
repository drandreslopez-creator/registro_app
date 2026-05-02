# Registro personal de entradas y salidas

Esta app en Python sirve para guardar tus registros personales de:

- `Entrada`
- `Salida`
- `Libre`

Cada clic guarda la fecha y la hora en un archivo local llamado `historial_registros.csv`.
La hora usada es siempre la de Colombia (`America/Bogota`).

## Como usarla

1. Abre una terminal en esta carpeta.
2. Si quieres la version de escritorio, ejecuta:

```bash
python3 app_registro_hospital.py
```

3. Si quieres la version Streamlit, que es la mejor opcion para navegador y celular, ejecuta:

```bash
python3 -m streamlit run streamlit_app.py
```

4. Si quieres la version web simple, ejecuta:

```bash
python3 app_registro_web.py
```

## Que puede hacer

- Guardar historial con fecha y hora.
- No tiene opcion de borrar registros desde la app, para que el soporte no se pierda.
- Mostrar todos los registros en pantalla.
- Exportar un `CSV` organizado para abrir en Excel.
- Exportar un `HTML` listo para imprimir.
- Guardar el periodo de cada movimiento con corte del dia `21` al dia `20`.
- Permitir registrar manualmente una fecha y hora pasada si se te olvido marcarla el mismo dia.
- Filtrar la tabla por periodo para revisar o exportar solo el corte que necesites.
- Crear una copia de seguridad automatica del historial cada vez que guardas.
- Asociar cada marca a un turno: `12h dia`, `12h noche` o `5h manana`.
- Calcular por jornada cuanto tiempo estuviste dentro, cuanto por fuera y si te excediste.
- Mostrar resumen acumulado del periodo filtrado.

## Como funciona el periodo

- Si hoy fuera `2026-05-02`, el periodo actual seria `2026-04-21 al 2026-05-20`.
- Si hoy fuera `2026-05-25`, el periodo actual seria `2026-05-21 al 2026-06-20`.

## Registro manual

En la misma ventana puedes escribir:

- Fecha en formato `AAAA-MM-DD`
- Hora en formato `HH:MM:SS`
- Tipo: `entrada`, `salida` o `libre`
- Turno: `12h dia`, `12h noche`, `5h manana` o `libre`
- Un detalle opcional

Luego presionas `Guardar manual` y el sistema lo guarda en el periodo que corresponda a esa fecha.

## Turnos y calculos

- `12h dia`: se toma como jornada de `07:00` a `19:00`
- `12h noche`: se toma como jornada de `19:00` a `07:00` del dia siguiente
- `5h manana`: se toma como jornada de `07:00` a `12:00`
- En turnos de `12h` la app considera `01:00` permitida por comida
- En `5h manana` la salida permitida queda en `00:00`

La app suma el tiempo por fuera tomando cada bloque `salida -> entrada` dentro del mismo turno.
Luego calcula:

- `Dentro`: tiempo programado menos tiempo por fuera
- `Fuera`: tiempo total que estuviste fuera durante el turno
- `Permitido`: tiempo aceptado sin problema
- `Exceso`: lo que supera el tiempo permitido

## Filtro por periodo

Puedes escoger `Todos los periodos` o un periodo especifico en la parte de filtro.
Las exportaciones en `CSV` y `HTML` usan lo que tengas visible en ese momento.

## Version web para celular

- Ejecuta `python3 app_registro_web.py`
- Abre en el computador `http://127.0.0.1:8000`
- Si el celular esta en la misma red Wi-Fi, abre `http://TU_IP_LOCAL:8000`
- La app web usa el mismo historial de la version de escritorio
- Desde la web tambien puedes registrar movimientos, filtrar periodos y exportar reportes

## Version Streamlit

- Ejecuta `python3 -m streamlit run streamlit_app.py`
- Se abrira en `http://localhost:8501`
- En el celular, si esta en la misma red, puedes abrir `http://TU_IP_LOCAL:8501`
- El archivo principal para subir a Streamlit es `streamlit_app.py`
- Las dependencias quedaron en `requirements.txt`
- Usa el mismo historial de la app de escritorio
- Importante: en Streamlit Community Cloud, los archivos generados por la app no estan garantizados entre reinicios o sesiones. Para uso real continuo conviene conectar un almacenamiento externo.

## Archivos que genera

- `historial_registros.csv`: historial principal
- `historial_organizado.csv`: exportacion manual
- `reporte_para_imprimir.html`: reporte para imprimir
- `copias_seguridad/`: carpeta con respaldo automatico del historial
- `app_registro_web.py`: version web para navegador y celular
- `streamlit_app.py`: version principal para Streamlit
- `requirements.txt`: dependencias para ejecutar o publicar

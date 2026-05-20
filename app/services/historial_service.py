# =============================================================================
# app/services/historial_service.py
# Lógica de negocio para historial de intentos — Fase D
# =============================================================================
from datetime import datetime, timezone

from fastapi import HTTPException, status

from app.core.supabase import supabase_get
from app.schemas.schemas import (
    HistorialDetalleResponse,
    HistorialItemSchema,
    HistorialListadoResponse,
    OpcionResultadoSchema,
    RespuestaFeedbackSchema,
)


# ---------------------------------------------------------------------------
# Helpers privados
# ---------------------------------------------------------------------------

def _ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


def _resultados_disponibles(exam_fecha_vencimiento) -> bool:
    """
    Retorna True si exam_fecha_vencimiento < ahora (el período cerró).
    Si la fecha de vencimiento es null, se considera que los resultados
    están disponibles de inmediato.
    """
    if not exam_fecha_vencimiento:
        return True
    try:
        fecha = datetime.fromisoformat(str(exam_fecha_vencimiento))
        if fecha.tzinfo is None:
            fecha = fecha.replace(tzinfo=timezone.utc)
        return _ahora_utc() >= fecha
    except Exception:
        return True


def _calcular_calificacion(
    progreso_json: dict,
    exam_json: dict,
) -> tuple[float, int, int]:
    """
    Calcula calificación, aciertos y total_preguntas desde los JSONs.
    Retorna (calificacion, aciertos, total_preguntas).

    Las respuestas del alumno están en progreso_json['respuestas']:
        { id_pregunta: letra_elegida }

    Las respuestas correctas están en exam_json['preguntas'][]['opciones']:
        opciones con es_correcta=True.

    Para preguntas tipo 'simple': un acierto si la opción elegida es correcta.
    Para preguntas tipo 'multiple': un acierto si TODAS las opciones correctas
    coinciden con las elegidas (el frontend envía solo una letra por pregunta
    en el autosave, así que se trata igual que simple).
    """
    respuestas_alumno: dict = progreso_json.get("respuestas", {})
    preguntas: list = exam_json.get("preguntas", [])

    if not preguntas:
        return 0.0, 0, 0

    total = len(preguntas)
    aciertos = 0

    for pregunta in preguntas:
        id_p = pregunta.get("id_pregunta", "")
        respuesta_alumno = respuestas_alumno.get(id_p)
        if not respuesta_alumno:
            continue
        opciones = pregunta.get("opciones", [])
        for opcion in opciones:
            if opcion.get("letra") == respuesta_alumno and opcion.get("es_correcta"):
                aciertos += 1
                break

    calificacion = round((aciertos / total) * 100, 2) if total > 0 else 0.0
    return calificacion, aciertos, total


def _construir_feedback(
    progreso_json: dict,
    exam_json: dict,
) -> list[RespuestaFeedbackSchema]:
    """
    Construye el feedback pregunta por pregunta cruzando las respuestas
    del alumno con las respuestas correctas y explicaciones del exam_json.
    """
    respuestas_alumno: dict = progreso_json.get("respuestas", {})
    preguntas: list = exam_json.get("preguntas", [])
    feedback = []

    for pregunta in preguntas:
        id_p = pregunta.get("id_pregunta", "")
        respuesta_alumno = respuestas_alumno.get(id_p)
        opciones_raw = pregunta.get("opciones", [])

        # Encontrar la opción correcta y su explicación
        respuesta_correcta = ""
        explicacion = None
        opciones_resultado = []

        for opcion in opciones_raw:
            if opcion.get("es_correcta"):
                respuesta_correcta = opcion.get("letra", "")
                explicacion = opcion.get("explicacion")
            opciones_resultado.append(
                OpcionResultadoSchema(
                    letra=opcion.get("letra", ""),
                    texto=opcion.get("texto", ""),
                    es_correcta=opcion.get("es_correcta", False),
                    explicacion=opcion.get("explicacion"),
                )
            )

        es_correcto = (
            respuesta_alumno is not None
            and respuesta_alumno == respuesta_correcta
        )

        feedback.append(
            RespuestaFeedbackSchema(
                id_pregunta=id_p,
                enunciado=pregunta.get("enunciado", ""),
                tipo_pregunta=pregunta.get("tipo_pregunta", "simple"),
                respuesta_alumno=respuesta_alumno,
                respuesta_correcta=respuesta_correcta,
                es_correcto=es_correcto,
                explicacion=explicacion,
                opciones=opciones_resultado,
            )
        )

    return feedback


def _capaci_desde_examenes_raw(examenes_raw: list[dict], exam_id: str) -> tuple[str | None, str | None]:
    """Extrae capaci_id y capaci_nombre para un exam_id dado."""
    for e in examenes_raw:
        if e.get("exam_id") == exam_id:
            cap = e.get("capacitaciones") or {}
            if isinstance(cap, list):
                cap = cap[0] if cap else {}
            return e.get("capaci_id"), cap.get("capaci_nombre")
    return None, None


# =============================================================================
# listar_historial()
# =============================================================================
async def listar_historial(
    usuario_id: str,
    estado: str | None = None,
    capaci_id: str | None = None,
) -> HistorialListadoResponse:
    """
    Lista los intentos COMPLETADO y EXPIRADO del alumno.

    Filtros opcionales:
        estado    → 'completado' | 'expirado' | None (ambos).
        capaci_id → filtra por capacitación específica.

    Flujo:
        1. Consultar intentos_examen con estado COMPLETADO/EXPIRADO.
        2. JOIN con examenes para nombre y dificultad.
        3. JOIN con capacitacion_examenes + capacitaciones para capaci_id/nombre.
        4. Si capaci_id está en el filtro, descartar los que no coincidan.
    """

    # -----------------------------------------------------------------
    # 1. Intentos terminados del alumno
    # -----------------------------------------------------------------
    estados_filtro = "in.(COMPLETADO,EXPIRADO)"
    if estado == "completado":
        estados_filtro = "eq.COMPLETADO"
    elif estado == "expirado":
        estados_filtro = "eq.EXPIRADO"

    intentos_raw = await supabase_get(
        "intentos_examen",
        f"select=intento_id,exam_id,inex_estado,inex_numero_intento,"
        f"inex_fecha_inicio,inex_fecha_fin,inex_calificacion,"
        f"inex_aciertos,inex_total_preguntas,"
        f"examenes(exam_nombre,exam_dificultad,exam_fecha_vencimiento)"
        f"&usuario_id=eq.{usuario_id}"
        f"&inex_estado={estados_filtro}"
        f"&order=inex_fecha_inicio.desc",
    )

    if not intentos_raw:
        return HistorialListadoResponse(total=0, items=[])

    # -----------------------------------------------------------------
    # 2. Obtener capaci_id/nombre para cada examen
    # -----------------------------------------------------------------
    exam_ids = list({i["exam_id"] for i in intentos_raw})
    exam_ids_str = ",".join(exam_ids)

    capacitacion_por_exam: dict[str, tuple[str | None, str | None]] = {}

    cap_examenes_raw = await supabase_get(
        "capacitacion_examenes",
        f"select=exam_id,capaci_id,"
        f"capacitaciones(capaci_nombre)"
        f"&exam_id=in.({exam_ids_str})",
    )

    for ce in cap_examenes_raw:
        cap = ce.get("capacitaciones") or {}
        if isinstance(cap, list):
            cap = cap[0] if cap else {}
        capacitacion_por_exam[ce["exam_id"]] = (
            ce.get("capaci_id"),
            cap.get("capaci_nombre"),
        )

    # -----------------------------------------------------------------
    # 3. Construir items con filtro opcional por capaci_id
    # -----------------------------------------------------------------
    items: list[HistorialItemSchema] = []

    for intento in intentos_raw:
        exam_data = intento.get("examenes") or {}
        exam_id = intento["exam_id"]
        capaci_id_exam, capaci_nombre_exam = capacitacion_por_exam.get(exam_id, (None, None))

        # Filtro por capacitación
        if capaci_id and capaci_id_exam != capaci_id:
            continue

        disponible = _resultados_disponibles(exam_data.get("exam_fecha_vencimiento"))

        items.append(
            HistorialItemSchema(
                intento_id=intento["intento_id"],
                exam_id=exam_id,
                exam_nombre=exam_data.get("exam_nombre", "Sin nombre"),
                exam_dificultad=exam_data.get("exam_dificultad", "BASICO"),
                capaci_id=capaci_id_exam,
                capaci_nombre=capaci_nombre_exam,
                inex_estado=intento["inex_estado"],
                inex_numero_intento=intento["inex_numero_intento"],
                inex_fecha_inicio=str(intento["inex_fecha_inicio"]),
                inex_fecha_fin=str(intento["inex_fecha_fin"]) if intento.get("inex_fecha_fin") else None,
                calificacion=float(intento["inex_calificacion"]) if disponible and intento.get("inex_calificacion") is not None else None,
                aciertos=intento.get("inex_aciertos") if disponible else None,
                total_preguntas=intento.get("inex_total_preguntas") if disponible else None,
                resultados_disponibles=disponible,
            )
        )

    return HistorialListadoResponse(total=len(items), items=items)


# =============================================================================
# obtener_detalle_historial()
# =============================================================================
async def obtener_detalle_historial(
    intento_id: str,
    usuario_id: str,
) -> HistorialDetalleResponse:
    """
    Detalle completo de un intento pasado con feedback si el período cerró.

    Lógica de calificación:
        - Si inex_calificacion tiene valor en BD → usarlo directamente.
        - Si es null y exam_fecha_vencimiento < ahora → calcular desde
          inex_progreso_json vs exam_json en tiempo real.
        - Si es null y la fecha aún no pasó → devolver sin calificación
          con resultados_disponibles: false.
    """

    # -----------------------------------------------------------------
    # 1. Cargar el intento con datos del examen
    # -----------------------------------------------------------------
    intentos = await supabase_get(
        "intentos_examen",
        f"select=intento_id,usuario_id,exam_id,inex_estado,"
        f"inex_numero_intento,inex_fecha_inicio,inex_fecha_fin,"
        f"inex_calificacion,inex_aciertos,inex_total_preguntas,"
        f"inex_progreso_json,"
        f"examenes(exam_nombre,exam_dificultad,exam_fecha_vencimiento,"
        f"exam_calificacion_minima,exam_json)"
        f"&intento_id=eq.{intento_id}",
    )

    if not intentos:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Intento no encontrado.",
        )

    intento = intentos[0]

    # Verificar propiedad
    if intento["usuario_id"] != usuario_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes acceso a este intento.",
        )

    # Solo se puede ver historial de intentos terminados
    if intento["inex_estado"] not in ("COMPLETADO", "EXPIRADO"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Este intento aún está en curso.",
        )

    exam_data = intento.get("examenes") or {}
    exam_json = exam_data.get("exam_json") or {}
    progreso_json = intento.get("inex_progreso_json") or {}
    fecha_venc = exam_data.get("exam_fecha_vencimiento")
    disponible = _resultados_disponibles(fecha_venc)
    cal_minima = float(exam_data.get("exam_calificacion_minima", 70.0))

    # -----------------------------------------------------------------
    # 2. Obtener capacitación del examen
    # -----------------------------------------------------------------
    cap_examenes = await supabase_get(
        "capacitacion_examenes",
        f"select=capaci_id,capacitaciones(capaci_nombre)"
        f"&exam_id=eq.{intento['exam_id']}&limit=1",
    )
    capaci_id = None
    capaci_nombre = None
    if cap_examenes:
        ce = cap_examenes[0]
        capaci_id = ce.get("capaci_id")
        cap = ce.get("capacitaciones") or {}
        if isinstance(cap, list):
            cap = cap[0] if cap else {}
        capaci_nombre = cap.get("capaci_nombre")

    # -----------------------------------------------------------------
    # 3. Calcular o leer calificación
    # -----------------------------------------------------------------
    calificacion = None
    aciertos = None
    total_preguntas = None
    aprobado = None
    feedback = []

    if disponible:
        # Usar valores de BD si existen
        if intento.get("inex_calificacion") is not None:
            calificacion = float(intento["inex_calificacion"])
            aciertos = intento.get("inex_aciertos")
            total_preguntas = intento.get("inex_total_preguntas")
        elif exam_json and progreso_json:
            # Calcular en tiempo real
            calificacion, aciertos, total_preguntas = _calcular_calificacion(
                progreso_json, exam_json
            )

        if calificacion is not None:
            aprobado = calificacion >= cal_minima

        # Construir feedback si hay exam_json y respuestas
        if exam_json and progreso_json:
            feedback = _construir_feedback(progreso_json, exam_json)

    return HistorialDetalleResponse(
        intento_id=intento_id,
        exam_id=intento["exam_id"],
        exam_nombre=exam_data.get("exam_nombre", "Sin nombre"),
        exam_dificultad=exam_data.get("exam_dificultad", "BASICO"),
        exam_calificacion_minima=cal_minima,
        capaci_id=capaci_id,
        capaci_nombre=capaci_nombre,
        inex_estado=intento["inex_estado"],
        inex_numero_intento=intento["inex_numero_intento"],
        inex_fecha_inicio=str(intento["inex_fecha_inicio"]),
        inex_fecha_fin=str(intento["inex_fecha_fin"]) if intento.get("inex_fecha_fin") else None,
        resultados_disponibles=disponible,
        resultados_disponibles_en=str(fecha_venc) if fecha_venc else None,
        calificacion=calificacion,
        aciertos=aciertos,
        total_preguntas=total_preguntas,
        aprobado=aprobado,
        feedback=feedback,
    )

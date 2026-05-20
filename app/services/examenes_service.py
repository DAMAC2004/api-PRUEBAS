# =============================================================================
# app/services/examenes_service.py
# Lógica de negocio para listado y detalle de exámenes — Fase B
# =============================================================================
from fastapi import HTTPException, status

from app.core.supabase import supabase_get
from app.schemas.schemas import (
    DistribucionSchema,
    ExamenDetalleResponse,
    ExamenListadoItemSchema,
    ExamenesListadoResponse,
)


# ---------------------------------------------------------------------------
# Helpers privados para parsear exam_json
# ---------------------------------------------------------------------------

def _total_preguntas(exam_json: dict) -> int:
    """Extrae total_preguntas desde metadata.distribucion del exam_json."""
    return exam_json.get("metadata", {}).get("distribucion", {}).get("total_preguntas", 0)


def _distribucion(exam_json: dict) -> DistribucionSchema:
    dist = exam_json.get("metadata", {}).get("distribucion", {})
    return DistribucionSchema(
        total_preguntas=dist.get("total_preguntas", 0),
        simple=dist.get("simple", 0),
        multiple=dist.get("multiple", 0),
        abierta=dist.get("abierta", 0),
        basico=dist.get("basico", 0),
        intermedio=dist.get("intermedio", 0),
        avanzado=dist.get("avanzado", 0),
    )


def _tema(exam_json: dict) -> str | None:
    """
    Extrae el tema principal desde metadata.fuente_conocimiento.subtemas[0].nombre.
    Retorna None si el exam_json no tiene esa estructura.
    """
    try:
        subtemas = exam_json["metadata"]["fuente_conocimiento"]["subtemas"]
        return subtemas[0]["nombre"] if subtemas else None
    except (KeyError, IndexError, TypeError):
        return None


def _estado_intento(intentos: list[dict]) -> str:
    """
    Determina el estado consolidado a partir de todos los intentos del alumno
    para un examen dado.

    Prioridad: EN_PROGRESO > COMPLETADO > EXPIRADO > PENDIENTE
    """
    estados = {i["inex_estado"] for i in intentos}
    if "EN_PROGRESO" in estados:
        return "EN_PROGRESO"
    if "COMPLETADO" in estados:
        return "COMPLETADO"
    if "EXPIRADO" in estados:
        return "EXPIRADO"
    return "PENDIENTE"


def _mejor_calificacion(intentos: list[dict]) -> float | None:
    """Retorna la mayor calificación entre los intentos COMPLETADOS, o None."""
    completados = [
        i for i in intentos
        if i["inex_estado"] == "COMPLETADO" and i.get("inex_calificacion") is not None
    ]
    if not completados:
        return None
    return max(float(i["inex_calificacion"]) for i in completados)


# =============================================================================
# listar_examenes()
# =============================================================================
async def listar_examenes(
    usuario_id: str,
    estado: str | None = None,
    capaci_id: str | None = None,
) -> ExamenesListadoResponse:
    """
    Lista todos los exámenes del alumno con filtros opcionales.

    Parámetros:
        usuario_id → del JWT.
        estado     → 'pendiente' | 'en_progreso' | 'completado' | None (todos).
        capaci_id  → filtra por capacitación específica.

    Flujo:
        1. Obtener capacitaciones activas del alumno.
        2. Obtener exámenes de esas capacitaciones.
        3. Obtener todos los intentos del alumno para esos exámenes.
        4. Combinar y calcular campos derivados.
        5. Filtrar por `estado` si se especificó.
    """

    # -----------------------------------------------------------------
    # 1. Capacitaciones inscritas del alumno
    # -----------------------------------------------------------------
    cap_query = f"select=capaci_id&usuario_id=eq.{usuario_id}"
    if capaci_id:
        cap_query += f"&capaci_id=eq.{capaci_id}"

    inscripciones = await supabase_get("capacitacion_usuario", cap_query)
    if not inscripciones:
        return ExamenesListadoResponse(items=[], total=0)

    capaci_ids = [c["capaci_id"] for c in inscripciones]
    ids_str = ",".join(capaci_ids)

    # -----------------------------------------------------------------
    # 2. Exámenes asociados a esas capacitaciones
    # -----------------------------------------------------------------
    examenes_raw = await supabase_get(
        "capacitacion_examenes",
        f"select=capaci_id,exam_id,"
        f"examenes(exam_nombre,exam_dificultad,exam_intentos_max,"
        f"exam_tiempo_limite,exam_fecha_vencimiento,"
        f"exam_calificacion_minima,exam_json),"
        f"capacitaciones(capaci_nombre)"
        f"&capaci_id=in.({ids_str})",
    )
    if not examenes_raw:
        return ExamenesListadoResponse(items=[], total=0)

    exam_ids = [e["exam_id"] for e in examenes_raw]
    exam_ids_str = ",".join(exam_ids)

    # -----------------------------------------------------------------
    # 3. Todos los intentos del alumno para esos exámenes
    # -----------------------------------------------------------------
    intentos_raw = await supabase_get(
        "intentos_examen",
        f"select=exam_id,inex_estado,inex_calificacion,inex_numero_intento"
        f"&usuario_id=eq.{usuario_id}"
        f"&exam_id=in.({exam_ids_str})",
    )

    # Indexar intentos por exam_id para acceso O(1)
    intentos_por_examen: dict[str, list[dict]] = {}
    for intento in intentos_raw:
        eid = intento["exam_id"]
        intentos_por_examen.setdefault(eid, []).append(intento)

    # -----------------------------------------------------------------
    # 4. Construir items
    # -----------------------------------------------------------------
    items: list[ExamenListadoItemSchema] = []

    for e in examenes_raw:
        exam_data = e.get("examenes") or {}
        capaci_data = e.get("capacitaciones") or {}
        exam_id = e["exam_id"]
        exam_json = exam_data.get("exam_json") or {}

        intentos = intentos_por_examen.get(exam_id, [])
        estado_calculado = _estado_intento(intentos)

        # Filtro por estado si se especificó
        if estado:
            mapa = {
                "pendiente": "PENDIENTE",
                "en_progreso": "EN_PROGRESO",
                "completado": "COMPLETADO",
                "expirado": "EXPIRADO",
            }
            estado_filtro = mapa.get(estado.lower())
            if estado_filtro and estado_calculado != estado_filtro:
                continue

        fecha_venc = exam_data.get("exam_fecha_vencimiento")

        items.append(
            ExamenListadoItemSchema(
                exam_id=exam_id,
                capaci_id=e["capaci_id"],
                capaci_nombre=capaci_data.get("capaci_nombre", "Sin nombre"),
                exam_nombre=exam_data.get("exam_nombre", "Sin nombre"),
                exam_dificultad=exam_data.get("exam_dificultad", "BASICO"),
                exam_tema=_tema(exam_json),
                exam_tiempo_limite=exam_data.get("exam_tiempo_limite", 60),
                exam_intentos_max=exam_data.get("exam_intentos_max", 3),
                intentos_realizados=len(intentos),
                mejor_calificacion=_mejor_calificacion(intentos),
                exam_fecha_vencimiento=str(fecha_venc) if fecha_venc else None,
                total_preguntas=_total_preguntas(exam_json),
                estado_intento=estado_calculado,
            )
        )

    return ExamenesListadoResponse(items=items, total=len(items))


# =============================================================================
# obtener_detalle_examen()
# =============================================================================
async def obtener_detalle_examen(
    exam_id: str,
    usuario_id: str,
) -> ExamenDetalleResponse:
    """
    Detalle pre-inicio de un examen específico.
    Verifica que el alumno está inscrito en la capacitación del examen.

    Parámetros:
        exam_id    → UUID del examen.
        usuario_id → del JWT.
    """

    # -----------------------------------------------------------------
    # 1. Datos del examen + capacitación
    # -----------------------------------------------------------------
    examen_raw = await supabase_get(
        "capacitacion_examenes",
        f"select=capaci_id,exam_id,"
        f"examenes(exam_nombre,exam_dificultad,exam_intentos_max,"
        f"exam_tiempo_limite,exam_fecha_vencimiento,"
        f"exam_calificacion_minima,exam_json),"
        f"capacitaciones(capaci_nombre)"
        f"&exam_id=eq.{exam_id}",
    )

    if not examen_raw:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Examen no encontrado.",
        )

    e = examen_raw[0]
    exam_data = e.get("examenes") or {}
    capaci_data = e.get("capacitaciones") or {}
    exam_json = exam_data.get("exam_json") or {}

    # -----------------------------------------------------------------
    # 2. Verificar que el alumno está inscrito en esa capacitación
    # -----------------------------------------------------------------
    inscripcion = await supabase_get(
        "capacitacion_usuario",
        f"select=capaci_id&usuario_id=eq.{usuario_id}&capaci_id=eq.{e['capaci_id']}",
    )
    if not inscripcion:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No estás inscrito en la capacitación de este examen.",
        )

    # -----------------------------------------------------------------
    # 3. Intentos del alumno para calcular campos derivados
    # -----------------------------------------------------------------
    intentos = await supabase_get(
        "intentos_examen",
        f"select=inex_estado,inex_calificacion"
        f"&usuario_id=eq.{usuario_id}&exam_id=eq.{exam_id}",
    )

    intentos_realizados = len(intentos)
    intentos_max = exam_data.get("exam_intentos_max", 3)
    fecha_venc = exam_data.get("exam_fecha_vencimiento")

    return ExamenDetalleResponse(
        exam_id=exam_id,
        capaci_id=e["capaci_id"],
        capaci_nombre=capaci_data.get("capaci_nombre", "Sin nombre"),
        exam_nombre=exam_data.get("exam_nombre", "Sin nombre"),
        exam_dificultad=exam_data.get("exam_dificultad", "BASICO"),
        exam_tema=_tema(exam_json),
        exam_tiempo_limite=exam_data.get("exam_tiempo_limite", 60),
        exam_intentos_max=intentos_max,
        exam_calificacion_minima=float(exam_data.get("exam_calificacion_minima", 70.0)),
        intentos_realizados=intentos_realizados,
        intentos_disponibles=max(0, intentos_max - intentos_realizados),
        mejor_calificacion=_mejor_calificacion(intentos),
        exam_fecha_vencimiento=str(fecha_venc) if fecha_venc else None,
        total_preguntas=_total_preguntas(exam_json),
        distribucion=_distribucion(exam_json),
        estado_intento=_estado_intento(intentos),
    )

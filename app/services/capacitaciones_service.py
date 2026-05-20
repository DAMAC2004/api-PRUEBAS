# =============================================================================
# app/services/capacitaciones_service.py
# Lógica de negocio para listado y detalle de capacitaciones — Fase C
# =============================================================================
from fastapi import HTTPException, status

from app.core.supabase import supabase_get
from app.schemas.schemas import (
    CapacitacionDetalleResponse,
    CapacitacionListadoItemSchema,
    CapacitacionesListadoResponse,
    CatedraticoDashboardSchema,
    ContenidoDetalleCapacitacionSchema,
    ExamenDetalleCapacitacionSchema,
)


# ---------------------------------------------------------------------------
# Helpers privados
# ---------------------------------------------------------------------------

def _str_or_none(value) -> str | None:
    return str(value) if value else None


def _estado_intento(intentos: list[dict]) -> str:
    estados = {i["inex_estado"] for i in intentos}
    if "EN_PROGRESO" in estados:
        return "EN_PROGRESO"
    if "COMPLETADO" in estados:
        return "COMPLETADO"
    if "EXPIRADO" in estados:
        return "EXPIRADO"
    return "PENDIENTE"


def _mejor_calificacion(intentos: list[dict]) -> float | None:
    completados = [
        i for i in intentos
        if i["inex_estado"] == "COMPLETADO" and i.get("inex_calificacion") is not None
    ]
    if not completados:
        return None
    return max(float(i["inex_calificacion"]) for i in completados)


async def _get_catedraticos(capaci_id: str) -> list[CatedraticoDashboardSchema]:
    """
    Obtiene los catedráticos asignados a una capacitación.
    Consulta catedratico_capacitacion + usuarios + catedratico_detalles.
    """
    asignaciones = await supabase_get(
        "catedratico_capacitacion",
        f"select=usuario_id,caca_rol,"
        f"usuarios(usuario_nombre,usuario_apellidos),"
        f"catedratico_detalles(cade_titulo,cade_especialidad,cade_avatar_url)"
        f"&capaci_id=eq.{capaci_id}",
    )

    result = []
    for a in asignaciones:
        u = a.get("usuarios") or {}
        d = a.get("catedratico_detalles") or {}
        # catedratico_detalles puede venir como lista en PostgREST
        if isinstance(d, list):
            d = d[0] if d else {}
        result.append(
            CatedraticoDashboardSchema(
                usuario_id=a["usuario_id"],
                usuario_nombre=u.get("usuario_nombre", ""),
                usuario_apellidos=u.get("usuario_apellidos"),
                cade_titulo=d.get("cade_titulo"),
                cade_especialidad=d.get("cade_especialidad"),
                cade_avatar_url=d.get("cade_avatar_url"),
                caca_rol=a.get("caca_rol", "catedratico"),
            )
        )
    return result


# =============================================================================
# listar_capacitaciones()
# =============================================================================
async def listar_capacitaciones(
    usuario_id: str,
    estado: str | None = None,
) -> CapacitacionesListadoResponse:
    """
    Lista todas las capacitaciones del alumno con filtro opcional por estado.

    Parámetros:
        usuario_id → del JWT.
        estado     → 'activas' | 'finalizadas' | None (todas).
                     'activas'    = inscrito + en_progreso
                     'finalizadas'= completado + abandonado

    Flujo de consultas:
        1. capacitacion_usuario + capacitaciones → inscripciones del alumno.
        2. capacitacion_examenes + intentos_examen → totales de exámenes.
        3. capacitacion_contenidos → total de contenidos.
        4. catedratico_capacitacion + usuarios + catedratico_detalles → catedráticos.
    """

    # -----------------------------------------------------------------
    # 1. Inscripciones del alumno
    # -----------------------------------------------------------------
    query = (
        f"select=capaci_id,caus_progreso,caus_estado,inscrito_en,completado_en,"
        f"capacitaciones(capaci_nombre,capaci_descripcion,capaci_disponibilidad,"
        f"capaci_fecha_inicio,capaci_fecha_fin)"
        f"&usuario_id=eq.{usuario_id}"
    )

    # Filtro por estado
    if estado == "activas":
        query += "&caus_estado=in.(inscrito,en_progreso)"
    elif estado == "finalizadas":
        query += "&caus_estado=in.(completado,abandonado)"

    inscripciones = await supabase_get("capacitacion_usuario", query)

    if not inscripciones:
        return CapacitacionesListadoResponse(total=0, items=[])

    capaci_ids = [i["capaci_id"] for i in inscripciones]
    ids_str = ",".join(capaci_ids)

    # -----------------------------------------------------------------
    # 2. Exámenes por capacitación
    # -----------------------------------------------------------------
    examenes_raw = await supabase_get(
        "capacitacion_examenes",
        f"select=capaci_id,exam_id&capaci_id=in.({ids_str})",
    )

    # exam_ids para consultar intentos
    exam_ids = list({e["exam_id"] for e in examenes_raw})
    examenes_por_capaci: dict[str, list[str]] = {}
    for e in examenes_raw:
        examenes_por_capaci.setdefault(e["capaci_id"], []).append(e["exam_id"])

    # Intentos del alumno para calcular examenes_aprobados
    intentos_raw = []
    if exam_ids:
        exam_ids_str = ",".join(exam_ids)
        intentos_raw = await supabase_get(
            "intentos_examen",
            f"select=exam_id,inex_estado,inex_calificacion"
            f"&usuario_id=eq.{usuario_id}"
            f"&exam_id=in.({exam_ids_str})",
        )

    # Indexar intentos por exam_id
    intentos_por_exam: dict[str, list[dict]] = {}
    for i in intentos_raw:
        intentos_por_exam.setdefault(i["exam_id"], []).append(i)

    # -----------------------------------------------------------------
    # 3. Total de contenidos por capacitación
    # -----------------------------------------------------------------
    contenidos_raw = await supabase_get(
        "capacitacion_contenidos",
        f"select=capaci_id,conten_id&capaci_id=in.({ids_str})",
    )
    contenidos_por_capaci: dict[str, int] = {}
    for c in contenidos_raw:
        cid = c["capaci_id"]
        contenidos_por_capaci[cid] = contenidos_por_capaci.get(cid, 0) + 1

    # -----------------------------------------------------------------
    # 4. Catedráticos (una consulta por capacitación — best-effort)
    # Para el listado traemos todos de una vez para eficiencia
    # -----------------------------------------------------------------
    catedraticos_raw = await supabase_get(
        "catedratico_capacitacion",
        f"select=capaci_id,usuario_id,caca_rol,"
        f"usuarios(usuario_nombre,usuario_apellidos),"
        f"catedratico_detalles(cade_titulo,cade_especialidad,cade_avatar_url)"
        f"&capaci_id=in.({ids_str})",
    )

    catedraticos_por_capaci: dict[str, list[CatedraticoDashboardSchema]] = {}
    for a in catedraticos_raw:
        u = a.get("usuarios") or {}
        d = a.get("catedratico_detalles") or {}
        if isinstance(d, list):
            d = d[0] if d else {}
        schema = CatedraticoDashboardSchema(
            usuario_id=a["usuario_id"],
            usuario_nombre=u.get("usuario_nombre", ""),
            usuario_apellidos=u.get("usuario_apellidos"),
            cade_titulo=d.get("cade_titulo"),
            cade_especialidad=d.get("cade_especialidad"),
            cade_avatar_url=d.get("cade_avatar_url"),
            caca_rol=a.get("caca_rol", "catedratico"),
        )
        catedraticos_por_capaci.setdefault(a["capaci_id"], []).append(schema)

    # -----------------------------------------------------------------
    # 5. Construir items
    # -----------------------------------------------------------------
    items: list[CapacitacionListadoItemSchema] = []

    for insc in inscripciones:
        capaci_id = insc["capaci_id"]
        cap = insc.get("capacitaciones") or {}

        exam_ids_cap = examenes_por_capaci.get(capaci_id, [])
        total_examenes = len(exam_ids_cap)
        examenes_aprobados = sum(
            1 for eid in exam_ids_cap
            for intento in intentos_por_exam.get(eid, [])
            if intento["inex_estado"] == "COMPLETADO"
            and intento.get("inex_calificacion") is not None
        )

        items.append(
            CapacitacionListadoItemSchema(
                capaci_id=capaci_id,
                capaci_nombre=cap.get("capaci_nombre", "Sin nombre"),
                capaci_descripcion=cap.get("capaci_descripcion"),
                capaci_disponibilidad=cap.get("capaci_disponibilidad", "activa"),
                capaci_fecha_inicio=_str_or_none(cap.get("capaci_fecha_inicio")),
                capaci_fecha_fin=_str_or_none(cap.get("capaci_fecha_fin")),
                progreso=float(insc["caus_progreso"]),
                estado_inscripcion=insc["caus_estado"],
                inscrito_en=_str_or_none(insc.get("inscrito_en")),
                completado_en=_str_or_none(insc.get("completado_en")),
                total_examenes=total_examenes,
                examenes_aprobados=examenes_aprobados,
                total_contenidos=contenidos_por_capaci.get(capaci_id, 0),
                contenidos_vistos=0,
                catedraticos=catedraticos_por_capaci.get(capaci_id, []),
            )
        )

    return CapacitacionesListadoResponse(total=len(items), items=items)


# =============================================================================
# obtener_detalle_capacitacion()
# =============================================================================
async def obtener_detalle_capacitacion(
    capaci_id: str,
    usuario_id: str,
) -> CapacitacionDetalleResponse:
    """
    Detalle completo de una capacitación: meta-información + catedráticos
    + contenidos con unidad/orden + exámenes con unidad/orden y estado del alumno.

    Verifica que el alumno esté inscrito en la capacitación.
    """

    # -----------------------------------------------------------------
    # 1. Inscripción del alumno + datos de la capacitación
    # -----------------------------------------------------------------
    inscripciones = await supabase_get(
        "capacitacion_usuario",
        f"select=capaci_id,caus_progreso,caus_estado,inscrito_en,completado_en,"
        f"capacitaciones(capaci_nombre,capaci_descripcion,capaci_disponibilidad,"
        f"capaci_fecha_inicio,capaci_fecha_fin)"
        f"&usuario_id=eq.{usuario_id}&capaci_id=eq.{capaci_id}",
    )

    if not inscripciones:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No estás inscrito en esta capacitación.",
        )

    insc = inscripciones[0]
    cap = insc.get("capacitaciones") or {}

    # -----------------------------------------------------------------
    # 2. Catedráticos
    # -----------------------------------------------------------------
    catedraticos = await _get_catedraticos(capaci_id)

    # -----------------------------------------------------------------
    # 3. Contenidos (con unidad y orden)
    # -----------------------------------------------------------------
    contenidos_raw = await supabase_get(
        "capacitacion_contenidos",
        f"select=conten_id,caco_unidad,caco_orden,"
        f"contenidos(conten_nombre,conten_descripcion,conten_tipo)"
        f"&capaci_id=eq.{capaci_id}"
        f"&order=caco_unidad.asc,caco_orden.asc",
    )

    contenidos: list[ContenidoDetalleCapacitacionSchema] = []
    for c in contenidos_raw:
        cont = c.get("contenidos") or {}
        contenidos.append(
            ContenidoDetalleCapacitacionSchema(
                conten_id=c["conten_id"],
                conten_nombre=cont.get("conten_nombre", "Sin nombre"),
                conten_descripcion=cont.get("conten_descripcion"),
                conten_tipo=cont.get("conten_tipo", "pdf"),
                caco_unidad=c["caco_unidad"],
                caco_orden=c["caco_orden"],
                visto=False,
            )
        )

    # -----------------------------------------------------------------
    # 4. Exámenes (con unidad, orden y estado del alumno)
    # -----------------------------------------------------------------
    examenes_raw = await supabase_get(
        "capacitacion_examenes",
        f"select=exam_id,caex_unidad,caex_orden,"
        f"examenes(exam_nombre,exam_dificultad,exam_tiempo_limite,"
        f"exam_intentos_max,exam_calificacion_minima)"
        f"&capaci_id=eq.{capaci_id}"
        f"&order=caex_unidad.asc,caex_orden.asc",
    )

    exam_ids = [e["exam_id"] for e in examenes_raw]
    intentos_por_exam: dict[str, list[dict]] = {}

    if exam_ids:
        exam_ids_str = ",".join(exam_ids)
        intentos_raw = await supabase_get(
            "intentos_examen",
            f"select=exam_id,inex_estado,inex_calificacion"
            f"&usuario_id=eq.{usuario_id}"
            f"&exam_id=in.({exam_ids_str})",
        )
        for i in intentos_raw:
            intentos_por_exam.setdefault(i["exam_id"], []).append(i)

    examenes: list[ExamenDetalleCapacitacionSchema] = []
    examenes_aprobados = 0

    for e in examenes_raw:
        exam = e.get("examenes") or {}
        exam_id = e["exam_id"]
        intentos = intentos_por_exam.get(exam_id, [])

        mejor = _mejor_calificacion(intentos)
        cal_minima = float(exam.get("exam_calificacion_minima", 70.0))
        if mejor is not None and mejor >= cal_minima:
            examenes_aprobados += 1

        examenes.append(
            ExamenDetalleCapacitacionSchema(
                exam_id=exam_id,
                exam_nombre=exam.get("exam_nombre", "Sin nombre"),
                exam_dificultad=exam.get("exam_dificultad", "BASICO"),
                exam_tiempo_limite=exam.get("exam_tiempo_limite", 60),
                exam_intentos_max=exam.get("exam_intentos_max", 3),
                exam_calificacion_minima=cal_minima,
                caex_unidad=e["caex_unidad"],
                caex_orden=e["caex_orden"],
                estado_intento=_estado_intento(intentos),
                mejor_calificacion=mejor,
                intentos_realizados=len(intentos),
            )
        )

    return CapacitacionDetalleResponse(
        capaci_id=capaci_id,
        capaci_nombre=cap.get("capaci_nombre", "Sin nombre"),
        capaci_descripcion=cap.get("capaci_descripcion"),
        capaci_disponibilidad=cap.get("capaci_disponibilidad", "activa"),
        capaci_fecha_inicio=_str_or_none(cap.get("capaci_fecha_inicio")),
        capaci_fecha_fin=_str_or_none(cap.get("capaci_fecha_fin")),
        progreso=float(insc["caus_progreso"]),
        estado_inscripcion=insc["caus_estado"],
        inscrito_en=_str_or_none(insc.get("inscrito_en")),
        completado_en=_str_or_none(insc.get("completado_en")),
        total_examenes=len(examenes),
        examenes_aprobados=examenes_aprobados,
        total_contenidos=len(contenidos),
        contenidos_vistos=0,
        catedraticos=catedraticos,
        contenidos=contenidos,
        examenes=examenes,
    )

# =============================================================================
# app/services/dashboard_service.py
# Lógica de negocio del dashboard del alumno.
#
# Este servicio orquesta 4 consultas independientes a Supabase y las
# combina en un único objeto DashboardAlumnoResponse.
# Todas las consultas usan el SERVICE_ROLE key, por lo que bypasean RLS.
# =============================================================================
from fastapi import HTTPException, status

from app.core.supabase import supabase_get
from app.schemas.schemas import (
    CursoPendienteSchema,
    DashboardAlumnoResponse,
    ExamenPendienteSchema,
    RachaSchema,
)


async def obtener_dashboard(usuario_id: str, nombre_usuario: str) -> DashboardAlumnoResponse:
    """
    Construye el dashboard completo del alumno en una sola llamada.

    Consultas a Supabase:
        1. metricas_usuario   → racha, promedio, estadísticas.
        2. capacitacion_usuario → cursos inscritos (no completados).
        3. capacitacion_examenes + intentos_examen → exámenes pendientes.

    Parámetros:
        usuario_id     → UUID del alumno autenticado (viene del JWT).
        nombre_usuario → Nombre del alumno para el saludo (viene del JWT).

    Retorna DashboardAlumnoResponse listo para serializar.
    """

    # -----------------------------------------------------------------
    # 1. Métricas de gamificación
    # -----------------------------------------------------------------
    metricas_raw = await supabase_get(
        "metricas_usuario",
        f"select=meus_racha_dias,meus_ultima_actividad,"
        f"meus_promedio_general,meus_examenes_aprobados,"
        f"meus_examenes_presentados"
        f"&usuario_id=eq.{usuario_id}",
    )

    if metricas_raw:
        m = metricas_raw[0]
        racha = RachaSchema(
            racha_dias=m["meus_racha_dias"],
            ultima_actividad=str(m["meus_ultima_actividad"]) if m["meus_ultima_actividad"] else None,
            promedio_general=float(m["meus_promedio_general"]),
            examenes_aprobados=m["meus_examenes_aprobados"],
            examenes_presentados=m["meus_examenes_presentados"],
        )
    else:
        # El alumno existe pero aún no tiene fila en metricas_usuario
        # (puede pasar si el seed no la creó). Devolvemos valores neutros.
        racha = RachaSchema(
            racha_dias=0,
            ultima_actividad=None,
            promedio_general=0.0,
            examenes_aprobados=0,
            examenes_presentados=0,
        )

    # -----------------------------------------------------------------
    # 2. Cursos pendientes (inscrito o en_progreso, no completados)
    # PostgREST permite filtros múltiples con & y operadores:
    #   neq → not equal
    # Para filtrar por dos valores usamos: caus_estado=neq.completado
    # y excluimos también 'abandonado'.
    # -----------------------------------------------------------------
    cursos_raw = await supabase_get(
        "capacitacion_usuario",
        f"select=capaci_id,caus_progreso,caus_estado,inscrito_en,"
        f"capacitaciones(capaci_nombre,capaci_descripcion,capaci_fecha_fin)"
        f"&usuario_id=eq.{usuario_id}"
        f"&caus_estado=neq.completado"
        f"&caus_estado=neq.abandonado",
    )

    cursos_pendientes: list[CursoPendienteSchema] = []
    capaci_ids_activos: list[str] = []

    for c in cursos_raw:
        capaci_data = c.get("capacitaciones") or {}
        capaci_ids_activos.append(c["capaci_id"])
        cursos_pendientes.append(
            CursoPendienteSchema(
                capaci_id=c["capaci_id"],
                capaci_nombre=capaci_data.get("capaci_nombre", "Sin nombre"),
                capaci_descripcion=capaci_data.get("capaci_descripcion"),
                progreso=float(c["caus_progreso"]),
                estado=c["caus_estado"],
                fecha_fin=capaci_data.get("capaci_fecha_fin"),
            )
        )

    # -----------------------------------------------------------------
    # 3. Exámenes pendientes
    #
    # Lógica:
    #   a) Obtener todos los exámenes de las capacitaciones activas
    #      del alumno (via capacitacion_examenes JOIN examenes).
    #   b) Obtener los intentos del alumno con estado COMPLETADO.
    #   c) Un examen está pendiente si:
    #        - No tiene ningún intento COMPLETADO, O
    #        - Los intentos usados < intentos_max (puede reintentar).
    # -----------------------------------------------------------------
    examenes_pendientes: list[ExamenPendienteSchema] = []

    if capaci_ids_activos:
        # a) Exámenes de las capacitaciones en las que está inscrito
        # PostgREST: in.(v1,v2,v3) para filtrar por lista
        ids_str = ",".join(capaci_ids_activos)
        examenes_raw = await supabase_get(
            "capacitacion_examenes",
            f"select=capaci_id,exam_id,"
            f"examenes(exam_nombre,exam_dificultad,exam_intentos_max),"
            f"capacitaciones(capaci_nombre)"
            f"&capaci_id=in.({ids_str})",
        )

        # b) Intentos del alumno agrupados por exam_id
        intentos_raw = await supabase_get(
            "intentos_examen",
            f"select=exam_id,inex_estado,inex_numero_intento"
            f"&usuario_id=eq.{usuario_id}",
        )

        # Agrupar intentos por exam_id para contar rápidamente
        intentos_por_examen: dict[str, list[dict]] = {}
        for intento in intentos_raw:
            eid = intento["exam_id"]
            intentos_por_examen.setdefault(eid, []).append(intento)

        # c) Filtrar exámenes pendientes
        for e in examenes_raw:
            exam_data = e.get("examenes") or {}
            capaci_data = e.get("capacitaciones") or {}
            exam_id = e["exam_id"]
            intentos_max = exam_data.get("exam_intentos_max", 3)

            intentos_del_examen = intentos_por_examen.get(exam_id, [])
            completados = [i for i in intentos_del_examen if i["inex_estado"] == "COMPLETADO"]
            intentos_usados = len(intentos_del_examen)

            # Pendiente si: sin completados O puede reintentar
            tiene_aprobado = any(
                i for i in completados
            )
            # Simplificación para demo: examen pendiente = no tiene ningún intento COMPLETADO
            # En producción agregarías lógica de calificación mínima para "aprobar"
            if not tiene_aprobado or intentos_usados < intentos_max:
                examenes_pendientes.append(
                    ExamenPendienteSchema(
                        exam_id=exam_id,
                        exam_nombre=exam_data.get("exam_nombre", "Sin nombre"),
                        exam_dificultad=exam_data.get("exam_dificultad", "BASICO"),
                        exam_intentos_max=intentos_max,
                        intentos_usados=intentos_usados,
                        intentos_restantes=max(0, intentos_max - intentos_usados),
                        capacitacion_nombre=capaci_data.get("capaci_nombre", "Sin nombre"),
                        capaci_id=e["capaci_id"],
                    )
                )

    # -----------------------------------------------------------------
    # 4. Saludo personalizado
    # -----------------------------------------------------------------
    saludo = f"¡Hola, {nombre_usuario}! 👋"

    return DashboardAlumnoResponse(
        saludo=saludo,
        nombre_completo=nombre_usuario,
        examenes_pendientes=examenes_pendientes,
        cursos_pendientes=cursos_pendientes,
        racha=racha,
    )

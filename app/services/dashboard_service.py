# =============================================================================
# app/services/dashboard_service.py
# Lógica de negocio del dashboard del alumno — Fase A
#
# Cambios respecto a v1:
#   - `metricas` ahora incluye totales de capacitaciones (completadas/total)
#     calculados en Python desde capacitacion_usuario — sin cambio en BD.
#   - `capacitaciones` reemplaza a `cursos_pendientes` con campos ampliados
#     (capaci_disponibilidad, capaci_fecha_inicio, catedraticos=[]).
#   - Se agrega consulta de `intento_en_progreso` desde intentos_examen.
#   - `examenes_pendientes` ahora incluye exam_tiempo_limite, total_preguntas
#     y estado_intento para alinearse con el contrato del frontend.
#   - `contenidos_recientes` siempre retorna [] en Fase A.
# =============================================================================
from app.core.supabase import supabase_get
from app.schemas.schemas import (
    CapacitacionDashboardSchema,
    DashboardAlumnoResponse,
    ExamenPendienteSchema,
    IntentoEnProgresoSchema,
    MetricasSchema,
)


async def obtener_dashboard(usuario_id: str, nombre_usuario: str) -> DashboardAlumnoResponse:
    """
    Construye el dashboard completo del alumno en una sola llamada.

    Consultas a Supabase (en orden):
        1. metricas_usuario        → racha, promedio, exámenes.
        2. capacitacion_usuario    → inscripciones activas + totales.
        3. intentos_examen         → intento EN_PROGRESO + conteos.
        4. capacitacion_examenes   → exámenes de las capacitaciones activas.

    Parámetros:
        usuario_id     → UUID del alumno (del JWT).
        nombre_usuario → Nombre para el saludo (del JWT).
    """

    # =================================================================
    # 1. MÉTRICAS DE GAMIFICACIÓN
    # =================================================================
    metricas_raw = await supabase_get(
        "metricas_usuario",
        f"select=meus_racha_dias,meus_ultima_actividad,"
        f"meus_promedio_general,meus_examenes_aprobados,"
        f"meus_examenes_presentados"
        f"&usuario_id=eq.{usuario_id}",
    )

    if metricas_raw:
        m = metricas_raw[0]
        racha_dias = m["meus_racha_dias"]
        ultima_actividad = str(m["meus_ultima_actividad"]) if m["meus_ultima_actividad"] else None
        promedio_actual = float(m["meus_promedio_general"])
        examenes_aprobados = m["meus_examenes_aprobados"]
        examenes_total = m["meus_examenes_presentados"]
    else:
        # Sin fila en metricas_usuario: alumno nuevo, valores neutros
        racha_dias = 0
        ultima_actividad = None
        promedio_actual = 0.0
        examenes_aprobados = 0
        examenes_total = 0

    # =================================================================
    # 2. CAPACITACIONES DEL ALUMNO
    # Traemos todas (incluyendo completadas/abandonadas) para calcular
    # los totales de métricas, luego filtramos para el array del dashboard.
    # =================================================================
    todas_inscripciones = await supabase_get(
        "capacitacion_usuario",
        f"select=capaci_id,caus_progreso,caus_estado,inscrito_en,completado_en,"
        f"capacitaciones(capaci_nombre,capaci_descripcion,"
        f"capaci_disponibilidad,capaci_fecha_inicio,capaci_fecha_fin)"
        f"&usuario_id=eq.{usuario_id}",
    )

    # Totales para métricas
    capacitaciones_total = len(todas_inscripciones)
    capacitaciones_completadas = sum(
        1 for c in todas_inscripciones if c["caus_estado"] == "completado"
    )

    # Tasa de aprobación
    tasa_aprobacion = (
        round((examenes_aprobados / examenes_total) * 100, 1)
        if examenes_total > 0
        else 0.0
    )

    # Construir MetricasSchema con todos los campos
    metricas = MetricasSchema(
        promedio_actual=promedio_actual,
        racha_dias=racha_dias,
        ultima_actividad=ultima_actividad,
        capacitaciones_completadas=capacitaciones_completadas,
        capacitaciones_total=capacitaciones_total,
        examenes_aprobados=examenes_aprobados,
        examenes_total=examenes_total,
        tasa_aprobacion=tasa_aprobacion,
    )

    # Filtrar solo las activas (inscrito o en_progreso) para el array
    activas = [
        c for c in todas_inscripciones
        if c["caus_estado"] not in ("completado", "abandonado")
    ]
    capaci_ids_activos = [c["capaci_id"] for c in activas]

    capacitaciones: list[CapacitacionDashboardSchema] = []
    for c in activas:
        cap = c.get("capacitaciones") or {}
        capacitaciones.append(
            CapacitacionDashboardSchema(
                capaci_id=c["capaci_id"],
                capaci_nombre=cap.get("capaci_nombre", "Sin nombre"),
                capaci_descripcion=cap.get("capaci_descripcion"),
                capaci_disponibilidad=cap.get("capaci_disponibilidad", "activa"),
                capaci_fecha_inicio=str(cap["capaci_fecha_inicio"]) if cap.get("capaci_fecha_inicio") else None,
                capaci_fecha_fin=str(cap["capaci_fecha_fin"]) if cap.get("capaci_fecha_fin") else None,
                progreso=float(c["caus_progreso"]),
                estado_inscripcion=c["caus_estado"],
                catedraticos=[],  # Se puebla en Fase B/C
            )
        )

    # =================================================================
    # 3. INTENTO EN PROGRESO
    # Busca si el alumno tiene algún examen con inex_estado = 'EN_PROGRESO'.
    # Solo puede haber uno a la vez (o ninguno).
    # =================================================================
    intento_en_progreso = None
    intentos_activos = await supabase_get(
        "intentos_examen",
        f"select=intento_id,exam_id,inex_fecha_inicio,inex_progreso_json,"
        f"examenes(exam_nombre)"
        f"&usuario_id=eq.{usuario_id}"
        f"&inex_estado=eq.EN_PROGRESO"
        f"&limit=1",
    )

    if intentos_activos:
        ia = intentos_activos[0]
        exam_data = ia.get("examenes") or {}

        # Extraer tiempo restante del JSON de autosave si existe
        progreso_json = ia.get("inex_progreso_json") or {}
        tiempo_restante = progreso_json.get("tiempo_restante_seg")

        intento_en_progreso = IntentoEnProgresoSchema(
            intento_id=ia["intento_id"],
            exam_id=ia["exam_id"],
            titulo=exam_data.get("exam_nombre", "Examen en progreso"),
            tiempo_restante_seg=tiempo_restante,
            fecha_inicio=str(ia["inex_fecha_inicio"]),
        )

    # =================================================================
    # 4. EXÁMENES PENDIENTES
    # Solo para las capacitaciones activas del alumno.
    # Un examen está pendiente si no tiene intentos COMPLETADOS
    # o si el alumno puede reintentar (intentos_usados < intentos_max).
    # =================================================================
    examenes_pendientes: list[ExamenPendienteSchema] = []

    if capaci_ids_activos:
        ids_str = ",".join(capaci_ids_activos)

        # a) Exámenes asociados a las capacitaciones activas
        examenes_raw = await supabase_get(
            "capacitacion_examenes",
            f"select=capaci_id,exam_id,"
            f"examenes(exam_nombre,exam_dificultad,exam_intentos_max,"
            f"exam_tiempo_limite,exam_fecha_vencimiento,exam_json),"
            f"capacitaciones(capaci_nombre)"
            f"&capaci_id=in.({ids_str})",
        )

        # b) Todos los intentos del alumno (para contar por exam_id)
        intentos_raw = await supabase_get(
            "intentos_examen",
            f"select=exam_id,inex_estado,inex_numero_intento"
            f"&usuario_id=eq.{usuario_id}",
        )

        # Indexar intentos por exam_id
        intentos_por_examen: dict[str, list[dict]] = {}
        for intento in intentos_raw:
            eid = intento["exam_id"]
            intentos_por_examen.setdefault(eid, []).append(intento)

        # c) Determinar estado y filtrar pendientes
        for e in examenes_raw:
            exam_data = e.get("examenes") or {}
            capaci_data = e.get("capacitaciones") or {}
            exam_id = e["exam_id"]
            intentos_max = exam_data.get("exam_intentos_max", 3)

            intentos_del_examen = intentos_por_examen.get(exam_id, [])
            intentos_realizados = len(intentos_del_examen)
            tiene_completado = any(
                i for i in intentos_del_examen if i["inex_estado"] == "COMPLETADO"
            )
            tiene_en_progreso = any(
                i for i in intentos_del_examen if i["inex_estado"] == "EN_PROGRESO"
            )

            # Estado consolidado del intento más relevante
            if tiene_en_progreso:
                estado_intento = "EN_PROGRESO"
            elif tiene_completado:
                estado_intento = "COMPLETADO"
            elif intentos_realizados > 0:
                estado_intento = "EXPIRADO"
            else:
                estado_intento = "PENDIENTE"

            # Contar preguntas desde exam_json
            exam_json = exam_data.get("exam_json") or {}
            preguntas = exam_json.get("preguntas") or []
            total_preguntas = len(preguntas)

            # Pendiente si: no completado O puede reintentar
            if not tiene_completado or intentos_realizados < intentos_max:
                fecha_venc = exam_data.get("exam_fecha_vencimiento")
                examenes_pendientes.append(
                    ExamenPendienteSchema(
                        exam_id=exam_id,
                        capaci_id=e["capaci_id"],
                        capaci_nombre=capaci_data.get("capaci_nombre", "Sin nombre"),
                        exam_nombre=exam_data.get("exam_nombre", "Sin nombre"),
                        exam_dificultad=exam_data.get("exam_dificultad", "BASICO"),
                        exam_tiempo_limite=exam_data.get("exam_tiempo_limite", 60),
                        exam_intentos_max=intentos_max,
                        intentos_realizados=intentos_realizados,
                        exam_fecha_vencimiento=str(fecha_venc) if fecha_venc else None,
                        estado_intento=estado_intento,
                        total_preguntas=total_preguntas,
                    )
                )

    # =================================================================
    # 5. SALUDO Y RESPUESTA FINAL
    # =================================================================
    saludo = f"Bienvenido, {nombre_usuario}"

    return DashboardAlumnoResponse(
        saludo=saludo,
        metricas=metricas,
        intento_en_progreso=intento_en_progreso,
        capacitaciones=capacitaciones,
        examenes_pendientes=examenes_pendientes,
        contenidos_recientes=[],  # Fase C
    )

# =============================================================================
# app/services/metricas_service.py
# Lógica de negocio para métricas del alumno — Fase D
# =============================================================================
from collections import defaultdict
from datetime import datetime, timezone, timedelta

from app.core.supabase import supabase_get
from app.schemas.schemas import (
    EvolucionPuntoSchema,
    MetricasDetalleResponse,
)


def _ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


def _calcular_evolucion(intentos: list[dict]) -> list[EvolucionPuntoSchema]:
    """
    Agrupa los intentos COMPLETADO con calificación por mes (YYYY-MM)
    y calcula el promedio mensual. Solo incluye los últimos 6 meses
    con al menos un intento calificado.

    Retorna lista ordenada cronológicamente (más antiguo primero)
    para que el frontend pueda graficar una línea de progreso.
    """
    ahora = _ahora_utc()
    limite = ahora - timedelta(days=180)  # ~6 meses

    # Agrupar calificaciones por mes
    calificaciones_por_mes: dict[str, list[float]] = defaultdict(list)

    for intento in intentos:
        if intento.get("inex_estado") != "COMPLETADO":
            continue
        cal = intento.get("inex_calificacion")
        if cal is None:
            continue
        fecha_fin_str = intento.get("inex_fecha_fin")
        if not fecha_fin_str:
            continue
        try:
            fecha = datetime.fromisoformat(str(fecha_fin_str))
            if fecha.tzinfo is None:
                fecha = fecha.replace(tzinfo=timezone.utc)
            if fecha < limite:
                continue
            periodo = fecha.strftime("%Y-%m")
            calificaciones_por_mes[periodo].append(float(cal))
        except Exception:
            continue

    if not calificaciones_por_mes:
        return []

    # Construir puntos ordenados cronológicamente
    puntos = []
    for periodo in sorted(calificaciones_por_mes.keys()):
        cals = calificaciones_por_mes[periodo]
        puntos.append(
            EvolucionPuntoSchema(
                periodo=periodo,
                promedio=round(sum(cals) / len(cals), 2),
                examenes_presentados=len(cals),
            )
        )

    return puntos


async def obtener_metricas(usuario_id: str) -> MetricasDetalleResponse:
    """
    Métricas completas del alumno incluyendo evolución mensual del promedio.

    Flujo:
        1. metricas_usuario → métricas base (racha, promedio, totales).
        2. capacitacion_usuario → totales de capacitaciones.
        3. intentos_examen (últimos 6 meses) → evolución_promedio.
    """

    # -----------------------------------------------------------------
    # 1. Métricas base
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
        racha_dias = m["meus_racha_dias"]
        ultima_actividad = str(m["meus_ultima_actividad"]) if m.get("meus_ultima_actividad") else None
        promedio_actual = float(m["meus_promedio_general"])
        examenes_aprobados = m["meus_examenes_aprobados"]
        examenes_total = m["meus_examenes_presentados"]
    else:
        racha_dias = 0
        ultima_actividad = None
        promedio_actual = 0.0
        examenes_aprobados = 0
        examenes_total = 0

    # -----------------------------------------------------------------
    # 2. Totales de capacitaciones
    # -----------------------------------------------------------------
    todas_inscripciones = await supabase_get(
        "capacitacion_usuario",
        f"select=caus_estado&usuario_id=eq.{usuario_id}",
    )
    capacitaciones_total = len(todas_inscripciones)
    capacitaciones_completadas = sum(
        1 for c in todas_inscripciones if c["caus_estado"] == "completado"
    )

    tasa_aprobacion = (
        round((examenes_aprobados / examenes_total) * 100, 1)
        if examenes_total > 0 else 0.0
    )

    # -----------------------------------------------------------------
    # 3. Intentos para evolución (últimos 6 meses)
    # -----------------------------------------------------------------
    ahora = _ahora_utc()
    limite_iso = (ahora - timedelta(days=180)).isoformat()

    intentos_raw = await supabase_get(
        "intentos_examen",
        f"select=inex_estado,inex_calificacion,inex_fecha_fin"
        f"&usuario_id=eq.{usuario_id}"
        f"&inex_estado=eq.COMPLETADO"
        f"&inex_fecha_fin=gte.{limite_iso}",
    )

    evolucion = _calcular_evolucion(intentos_raw)

    return MetricasDetalleResponse(
        promedio_actual=promedio_actual,
        racha_dias=racha_dias,
        ultima_actividad=ultima_actividad,
        capacitaciones_completadas=capacitaciones_completadas,
        capacitaciones_total=capacitaciones_total,
        examenes_aprobados=examenes_aprobados,
        examenes_total=examenes_total,
        tasa_aprobacion=tasa_aprobacion,
        evolucion_promedio=evolucion,
    )

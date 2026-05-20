# =============================================================================
# app/routers/capacitaciones.py
# Endpoints de capacitaciones para el alumno — Fase C
# =============================================================================
from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.core.deps import require_alumno
from app.schemas.schemas import (
    CapacitacionDetalleResponse,
    CapacitacionesListadoResponse,
    ErrorResponse,
)
from app.services import capacitaciones_service

router = APIRouter(prefix="/alumno/capacitaciones", tags=["Alumno — Capacitaciones"])


@router.get(
    "",
    response_model=CapacitacionesListadoResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Token inválido."},
        403: {"model": ErrorResponse, "description": "Solo para alumnos."},
    },
    summary="Listado de capacitaciones del alumno",
    description="""
Lista todas las capacitaciones en las que el alumno está inscrito.
Equivale a la página "Mis Capacitaciones" estilo Google Classroom.

**Filtro opcional:**
- `estado=activas` → inscrito + en_progreso.
- `estado=finalizadas` → completado + abandonado.
- Sin parámetro → todas.

**Incluye por ítem:**
- Progreso del alumno y estado de inscripción.
- Totales de exámenes y exámenes aprobados.
- Total de contenidos (`contenidos_vistos` siempre es 0 — pendiente de tracking).
- Array `catedraticos` con nombre, título, especialidad y avatar.
""",
)
async def listar_capacitaciones(
    estado: Optional[str] = Query(
        None,
        description="Filtrar por estado: activas | finalizadas. Omitir = todas.",
    ),
    usuario: dict = Depends(require_alumno),
) -> CapacitacionesListadoResponse:
    return await capacitaciones_service.listar_capacitaciones(
        usuario_id=usuario["sub"],
        estado=estado,
    )


@router.get(
    "/{capaci_id}",
    response_model=CapacitacionDetalleResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Token inválido."},
        403: {"model": ErrorResponse, "description": "No inscrito en la capacitación."},
        404: {"model": ErrorResponse, "description": "Capacitación no encontrada."},
    },
    summary="Detalle de una capacitación",
    description="""
Retorna el detalle completo de una capacitación incluyendo sus contenidos
y exámenes organizados por unidad y orden.

**Acceso restringido:** solo el alumno inscrito puede ver el detalle.

**Arrays incluidos:**

`contenidos[]` — material de estudio ordenado por `caco_unidad` y `caco_orden`.
El frontend puede agrupar visualmente por unidad usando esos campos.
`visto` siempre es `false` — pendiente de tabla de tracking.

`examenes[]` — evaluaciones con `caex_unidad` y `caex_orden` para
mostrarlos junto a los contenidos de la misma unidad.
Incluye `estado_intento` y `mejor_calificacion` del alumno.
""",
)
async def detalle_capacitacion(
    capaci_id: str,
    usuario: dict = Depends(require_alumno),
) -> CapacitacionDetalleResponse:
    return await capacitaciones_service.obtener_detalle_capacitacion(
        capaci_id=capaci_id,
        usuario_id=usuario["sub"],
    )

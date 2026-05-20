# =============================================================================
# app/routers/metricas.py
# Endpoint de métricas para el alumno — Fase D
# =============================================================================
from fastapi import APIRouter, Depends

from app.core.deps import require_alumno
from app.schemas.schemas import ErrorResponse, MetricasDetalleResponse
from app.services import metricas_service

router = APIRouter(prefix="/alumno/metricas", tags=["Alumno — Métricas"])


@router.get(
    "",
    response_model=MetricasDetalleResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Token inválido."},
        403: {"model": ErrorResponse, "description": "Solo para alumnos."},
    },
    summary="Métricas del alumno con evolución mensual",
    description="""
Retorna las métricas completas del alumno para la pantalla de estadísticas.

Extiende el objeto `metricas` del dashboard con `evolucion_promedio`:
array de hasta 6 puntos mensuales calculado en tiempo real desde
`intentos_examen` (últimos 6 meses con intentos COMPLETADO calificados).

**`evolucion_promedio`** — cada punto tiene:
- `periodo` → mes en formato `YYYY-MM`.
- `promedio` → promedio de calificaciones de ese mes.
- `examenes_presentados` → cantidad de intentos completados ese mes.

Lista vacía si el alumno no tiene intentos con calificación en los últimos 6 meses.
""",
)
async def metricas(
    usuario: dict = Depends(require_alumno),
) -> MetricasDetalleResponse:
    return await metricas_service.obtener_metricas(usuario_id=usuario["sub"])

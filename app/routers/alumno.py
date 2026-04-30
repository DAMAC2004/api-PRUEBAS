# =============================================================================
# app/routers/alumno.py
# Endpoints exclusivos para usuarios tipo 'alumno' — Fase A
#
# Cambios respecto a v1:
#   - response_model actualizado a DashboardAlumnoResponse (Fase A).
#   - Descripción del endpoint actualizada para reflejar los nuevos campos.
# =============================================================================
from fastapi import APIRouter, Depends

from app.core.deps import require_alumno
from app.schemas.schemas import DashboardAlumnoResponse, ErrorResponse
from app.services import dashboard_service

router = APIRouter(prefix="/alumno", tags=["Alumno — Dashboard"])


@router.get(
    "/dashboard",
    response_model=DashboardAlumnoResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Token ausente o inválido."},
        403: {"model": ErrorResponse, "description": "El usuario autenticado no es alumno."},
    },
    summary="Dashboard principal del alumno",
    description="""
Retorna toda la información necesaria para la pantalla de inicio del alumno
en una sola llamada, minimizando los round-trips del frontend.

**Requiere:** `Authorization: Bearer <token>` (obtenido en `/auth/login`).

**Incluye:**
- `saludo` — texto personalizado listo para mostrar.
- `metricas` — KPIs: racha, promedio, tasa de aprobación, totales de capacitaciones y exámenes.
- `intento_en_progreso` — si el alumno dejó un examen sin terminar, el frontend
  muestra el modal 'Retomar examen'. Es `null` si no hay ninguno activo.
- `capacitaciones` — cursos inscritos o en progreso con porcentaje de avance.
- `examenes_pendientes` — exámenes que el alumno puede presentar o reintentar.
- `contenidos_recientes` — siempre `[]` en Fase A (se puebla en Fase C).

**Nota:** solo aparecen capacitaciones con estado `inscrito` o `en_progreso`.
Los cursos `completados` o `abandonados` no están en esta vista.
""",
)
async def dashboard(usuario: dict = Depends(require_alumno)) -> DashboardAlumnoResponse:
    return await dashboard_service.obtener_dashboard(
        usuario_id=usuario["sub"],
        nombre_usuario=usuario["nombre"],
    )

# =============================================================================
# app/routers/alumno.py
# Endpoints exclusivos para usuarios tipo 'alumno'.
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
- Saludo personalizado (`saludo`).
- Lista de cursos pendientes con porcentaje de avance.
- Lista de exámenes pendientes con intentos disponibles.
- Métricas de gamificación: racha de días, promedio, estadísticas.

**Nota:** Solo devuelve cursos en estado `inscrito` o `en_progreso`.
Los cursos `completados` o `abandonados` no aparecen en esta vista.
""",
)
async def dashboard(usuario: dict = Depends(require_alumno)) -> DashboardAlumnoResponse:
    return await dashboard_service.obtener_dashboard(
        usuario_id=usuario["sub"],
        nombre_usuario=usuario["nombre"],
    )

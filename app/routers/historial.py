# =============================================================================
# app/routers/historial.py
# Endpoints de historial de intentos para el alumno — Fase D
# =============================================================================
from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.core.deps import require_alumno
from app.schemas.schemas import (
    ErrorResponse,
    HistorialDetalleResponse,
    HistorialListadoResponse,
)
from app.services import historial_service

router = APIRouter(prefix="/alumno/historial", tags=["Alumno — Historial"])


@router.get(
    "",
    response_model=HistorialListadoResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Token inválido."},
        403: {"model": ErrorResponse, "description": "Solo para alumnos."},
    },
    summary="Historial de intentos del alumno",
    description="""
Lista todos los intentos terminados del alumno: `COMPLETADO` y `EXPIRADO`.

**Filtros opcionales:**
- `estado` → `completado` | `expirado`. Sin parámetro = ambos.
- `capaci_id` → filtra por capacitación específica.

**Campo `resultados_disponibles`:**
- `true` si `exam_fecha_vencimiento` ya pasó — se muestran calificación y aciertos.
- `false` si el período aún no cerró — calificación y aciertos son `null`.
""",
)
async def listar_historial(
    estado: Optional[str] = Query(None, description="completado | expirado. Omitir = ambos."),
    capaci_id: Optional[str] = Query(None, description="UUID de capacitación para filtrar."),
    usuario: dict = Depends(require_alumno),
) -> HistorialListadoResponse:
    return await historial_service.listar_historial(
        usuario_id=usuario["sub"],
        estado=estado,
        capaci_id=capaci_id,
    )


@router.get(
    "/{intento_id}",
    response_model=HistorialDetalleResponse,
    responses={
        400: {"model": ErrorResponse, "description": "El intento aún está en curso."},
        401: {"model": ErrorResponse, "description": "Token inválido."},
        403: {"model": ErrorResponse, "description": "No tienes acceso a este intento."},
        404: {"model": ErrorResponse, "description": "Intento no encontrado."},
    },
    summary="Detalle de un intento pasado",
    description="""
Retorna el detalle completo de un intento terminado con feedback si el período cerró.

Si `resultados_disponibles` es `false`: calificación y feedback son null / [].
Si `resultados_disponibles` es `true`: calificación calculada + feedback por pregunta
con respuesta correcta y explicación del exam_json.
""",
)
async def detalle_historial(
    intento_id: str,
    usuario: dict = Depends(require_alumno),
) -> HistorialDetalleResponse:
    return await historial_service.obtener_detalle_historial(
        intento_id=intento_id,
        usuario_id=usuario["sub"],
    )

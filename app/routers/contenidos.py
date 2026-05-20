# =============================================================================
# app/routers/contenidos.py
# Endpoints de contenidos para el alumno — Fase C
# =============================================================================
from fastapi import APIRouter, Depends, Query

from app.core.deps import require_alumno
from app.schemas.schemas import (
    ContenidoUrlResponse,
    ContenidosListadoResponse,
    ErrorResponse,
)
from app.services import contenidos_service

router = APIRouter(prefix="/alumno/contenidos", tags=["Alumno — Contenidos"])


@router.get(
    "",
    response_model=ContenidosListadoResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Token inválido."},
        403: {"model": ErrorResponse, "description": "No inscrito en la capacitación."},
    },
    summary="Listado de contenidos de una capacitación",
    description="""
Lista todos los contenidos (PDF, guías, videos) de una capacitación
ordenados por unidad y posición.

**Parámetro requerido:** `capaci_id` — UUID de la capacitación.

**Acceso restringido:** solo alumnos inscritos en la capacitación.

El frontend puede agrupar los ítems por `caco_unidad` para mostrar
las secciones de la capacitación. El campo `visto` siempre es `false`
— se activará cuando se implemente el tracking de vistos.

Para acceder al archivo, llamar a `GET /alumno/contenidos/{conten_id}/url`.
""",
)
async def listar_contenidos(
    capaci_id: str = Query(..., description="UUID de la capacitación."),
    usuario: dict = Depends(require_alumno),
) -> ContenidosListadoResponse:
    return await contenidos_service.listar_contenidos(
        capaci_id=capaci_id,
        usuario_id=usuario["sub"],
    )


@router.get(
    "/{conten_id}/url",
    response_model=ContenidoUrlResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Token inválido."},
        403: {"model": ErrorResponse, "description": "No tienes acceso a este contenido."},
        404: {"model": ErrorResponse, "description": "Contenido no encontrado."},
    },
    summary="URL de acceso a un contenido",
    description="""
Devuelve la URL directa para abrir o descargar el archivo del contenido.

**Acceso restringido:** solo alumnos inscritos en la capacitación a la
que pertenece el contenido.

**Lógica de construcción de la URL:**
1. Si el contenido tiene `conten_url_publica` → se devuelve directamente.
2. Si no → se construye desde `conten_s3_key` usando el bucket público
   `contenidos` de Supabase Storage.

El campo `expira_en` es siempre `null` porque el bucket es público
y las URLs no tienen expiración.
""",
)
async def url_contenido(
    conten_id: str,
    usuario: dict = Depends(require_alumno),
) -> ContenidoUrlResponse:
    return await contenidos_service.obtener_url_contenido(
        conten_id=conten_id,
        usuario_id=usuario["sub"],
    )

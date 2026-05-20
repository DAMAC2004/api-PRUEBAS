# =============================================================================
# app/routers/perfil.py
# Endpoints de perfil del alumno — Fase E
# =============================================================================
from fastapi import APIRouter, Depends

from app.core.deps import require_alumno
from app.schemas.schemas import ErrorResponse, PerfilResponse, PerfilUpdateRequest
from app.services import perfil_service

router = APIRouter(prefix="/alumno/perfil", tags=["Alumno — Perfil"])


@router.get(
    "",
    response_model=PerfilResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Token inválido."},
        403: {"model": ErrorResponse, "description": "Solo para alumnos."},
        404: {"model": ErrorResponse, "description": "Usuario no encontrado."},
    },
    summary="Obtener perfil del alumno",
    description="""
Retorna el perfil completo del alumno autenticado ensamblando datos de
`usuarios` y `usuario_detalles`.

**Campos de solo lectura** (no editables vía esta API):
`usuario_nombre`, `usuario_apellidos`, `usuario_correo` — son datos
institucionales gestionados por el administrador.

**Campos editables** vía `PATCH /alumno/perfil`:
`usuario_idioma`, `usuario_modo_oscuro`, `usde_descripcion`, `avatar_url`.
""",
)
async def obtener_perfil(
    usuario: dict = Depends(require_alumno),
) -> PerfilResponse:
    return await perfil_service.obtener_perfil(usuario_id=usuario["sub"])


@router.patch(
    "",
    response_model=PerfilResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Token inválido."},
        403: {"model": ErrorResponse, "description": "Solo para alumnos."},
    },
    summary="Actualizar perfil del alumno",
    description="""
Actualiza los campos editables del perfil. Todos los campos son opcionales
— solo se actualizan los que se incluyan en el body.

**Campos disponibles:**
- `usuario_idioma` — código de idioma (`es`, `en`).
- `usuario_modo_oscuro` — preferencia de tema.
- `usde_descripcion` — bio o descripción personal.
- `avatar_url` — URL del avatar tras subirlo a Supabase Storage.

**Flujo de avatar:**
1. El frontend sube la imagen directamente a Supabase Storage desde el cliente.
2. Obtiene la URL pública del archivo.
3. Llama a este endpoint con `{ "avatar_url": "https://..." }`.
4. La API guarda la URL en `usde_avatar_url`.

Retorna el perfil completo actualizado.
""",
)
async def actualizar_perfil(
    body: PerfilUpdateRequest,
    usuario: dict = Depends(require_alumno),
) -> PerfilResponse:
    return await perfil_service.actualizar_perfil(
        usuario_id=usuario["sub"],
        body=body,
    )

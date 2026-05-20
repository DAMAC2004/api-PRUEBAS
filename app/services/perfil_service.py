# =============================================================================
# app/services/perfil_service.py
# Lógica de negocio para perfil del alumno — Fase E
# =============================================================================
from fastapi import HTTPException, status

from app.core.supabase import supabase_get, supabase_patch
from app.schemas.schemas import PerfilResponse, PerfilUpdateRequest


async def obtener_perfil(usuario_id: str) -> PerfilResponse:
    """
    Obtiene el perfil completo del alumno ensamblando
    datos de `usuarios` y `usuario_detalles`.
    """

    # -----------------------------------------------------------------
    # 1. Datos base del usuario
    # -----------------------------------------------------------------
    usuarios = await supabase_get(
        "usuarios",
        f"select=usuario_id,usuario_nombre,usuario_apellidos,"
        f"usuario_correo,usuario_idioma,usuario_modo_oscuro"
        f"&usuario_id=eq.{usuario_id}",
    )

    if not usuarios:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado.",
        )

    u = usuarios[0]

    # -----------------------------------------------------------------
    # 2. Detalles del perfil (puede no existir si nunca se ha editado)
    # -----------------------------------------------------------------
    detalles_raw = await supabase_get(
        "usuario_detalles",
        f"select=usde_username,usde_descripcion,usde_avatar_url"
        f"&usuario_id=eq.{usuario_id}",
    )
    d = detalles_raw[0] if detalles_raw else {}

    return PerfilResponse(
        usuario_id=u["usuario_id"],
        usuario_nombre=u["usuario_nombre"],
        usuario_apellidos=u.get("usuario_apellidos"),
        usuario_correo=u["usuario_correo"],
        usuario_idioma=u.get("usuario_idioma", "es"),
        usuario_modo_oscuro=u.get("usuario_modo_oscuro", False),
        usde_username=d.get("usde_username"),
        usde_descripcion=d.get("usde_descripcion"),
        usde_avatar_url=d.get("usde_avatar_url"),
    )


async def actualizar_perfil(
    usuario_id: str,
    body: PerfilUpdateRequest,
) -> PerfilResponse:
    """
    Actualiza los campos editables del perfil.
    Solo actualiza los campos que vienen en el body (PATCH parcial).

    Operaciones:
        - Si hay campos de `usuarios` → PATCH a `usuarios`.
        - Si hay campos de `usuario_detalles` → PATCH a `usuario_detalles`.
          Si la fila no existe (alumno nunca editó perfil), no falla —
          supabase_patch con 0 filas devuelve lista vacía sin error.
    """

    # -----------------------------------------------------------------
    # 1. Campos que van a la tabla `usuarios`
    # -----------------------------------------------------------------
    campos_usuario = {}
    if body.usuario_idioma is not None:
        campos_usuario["usuario_idioma"] = body.usuario_idioma
    if body.usuario_modo_oscuro is not None:
        campos_usuario["usuario_modo_oscuro"] = body.usuario_modo_oscuro

    if campos_usuario:
        await supabase_patch(
            "usuarios",
            f"usuario_id=eq.{usuario_id}",
            campos_usuario,
        )

    # -----------------------------------------------------------------
    # 2. Campos que van a la tabla `usuario_detalles`
    # -----------------------------------------------------------------
    campos_detalles = {}
    if body.usde_descripcion is not None:
        campos_detalles["usde_descripcion"] = body.usde_descripcion
    if body.avatar_url is not None:
        campos_detalles["usde_avatar_url"] = body.avatar_url

    if campos_detalles:
        await supabase_patch(
            "usuario_detalles",
            f"usuario_id=eq.{usuario_id}",
            campos_detalles,
        )

    # -----------------------------------------------------------------
    # 3. Devolver el perfil actualizado
    # -----------------------------------------------------------------
    return await obtener_perfil(usuario_id)

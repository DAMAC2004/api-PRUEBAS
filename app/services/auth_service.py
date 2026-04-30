# =============================================================================
# app/services/auth_service.py
# Lógica de negocio del módulo de autenticación — Fase A
#
# Cambios respecto a v1:
#   - login() ahora consulta también `organizaciones` y `usuario_detalles`
#     para devolver el branding y el avatar en la respuesta.
#   - Se agrega get_me() para rehidratación de sesión (GET /auth/me).
#     Reutiliza la misma lógica de ensamblado que login().
# =============================================================================
from datetime import datetime, timezone

from fastapi import HTTPException, status

from app.core.security import crear_token_acceso, verificar_password
from app.core.supabase import supabase_get, supabase_patch
from app.core.config import settings
from app.schemas.schemas import (
    LoginResponse,
    MeResponse,
    OrganizacionSchema,
    UsuarioSchema,
)


# ---------------------------------------------------------------------------
# Helper privado: construir OrganizacionSchema desde org_id
# ---------------------------------------------------------------------------
async def _get_organizacion(org_id: str) -> OrganizacionSchema:
    """
    Consulta la tabla `organizaciones` y retorna OrganizacionSchema.
    Si la org no se encuentra (no debería pasar), devuelve un objeto
    con valores por defecto para no romper el flujo del frontend.
    """
    orgs = await supabase_get(
        "organizaciones",
        f"select=org_id,org_nombre,org_color_primario,"
        f"org_color_secundario,org_logo_url"
        f"&org_id=eq.{org_id}",
    )

    if not orgs:
        # Fallback seguro: valores por defecto del schema
        return OrganizacionSchema(
            org_id=org_id,
            org_nombre="Organización",
        )

    o = orgs[0]
    return OrganizacionSchema(
        org_id=o["org_id"],
        org_nombre=o["org_nombre"],
        org_color_primario=o.get("org_color_primario", "#1565C0"),
        org_color_secundario=o.get("org_color_secundario", "#2E7D32"),
        org_logo_url=o.get("org_logo_url"),
    )


# ---------------------------------------------------------------------------
# Helper privado: construir UsuarioSchema desde datos de BD + avatar
# ---------------------------------------------------------------------------
async def _get_avatar_url(usuario_id: str) -> str | None:
    """
    Consulta `usuario_detalles` para obtener el avatar_url del alumno.
    Retorna None si el usuario no tiene fila en esa tabla (catedráticos,
    alumnos sin foto, etc.).
    """
    try:
        detalles = await supabase_get(
            "usuario_detalles",
            f"select=usde_avatar_url&usuario_id=eq.{usuario_id}",
        )
        if detalles:
            return detalles[0].get("usde_avatar_url")
    except Exception:
        pass  # Si falla, simplemente no hay avatar — no bloqueamos el login
    return None


# =============================================================================
# login()
# =============================================================================
async def login(correo: str, password: str) -> LoginResponse:
    """
    Valida credenciales y emite un JWT con el perfil completo.

    Pasos:
        1. Busca el usuario por correo en `usuarios`.
        2. Verifica el hash bcrypt.
        3. Actualiza `ultimo_acceso` (best-effort).
        4. Consulta la organización para branding.
        5. Consulta usuario_detalles para avatar (best-effort).
        6. Emite JWT y construye LoginResponse.
    """
    # -----------------------------------------------------------------
    # 1. Consultar usuario por correo
    # -----------------------------------------------------------------
    query = (
        "select=usuario_id,usuario_correo,usuario_password,"
        "usuario_tipo,usuario_rol,usuario_nombre,usuario_apellidos,"
        "usuario_idioma,usuario_modo_oscuro,org_id"
        f"&usuario_correo=eq.{correo}"
    )
    resultados = await supabase_get("usuarios", query)

    if not resultados:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Correo o contraseña incorrectos.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    u = resultados[0]

    # -----------------------------------------------------------------
    # 2. Verificar contraseña bcrypt
    # -----------------------------------------------------------------
    if not verificar_password(password, u["usuario_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Correo o contraseña incorrectos.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # -----------------------------------------------------------------
    # 3. Actualizar último acceso (best-effort)
    # -----------------------------------------------------------------
    try:
        ahora = datetime.now(timezone.utc).isoformat()
        await supabase_patch(
            "usuarios",
            f"usuario_id=eq.{u['usuario_id']}",
            {"ultimo_acceso": ahora},
        )
    except Exception:
        pass

    # -----------------------------------------------------------------
    # 4. Organización (branding)
    # -----------------------------------------------------------------
    organizacion = await _get_organizacion(u["org_id"])

    # -----------------------------------------------------------------
    # 5. Avatar (best-effort; solo aplica a alumnos)
    # -----------------------------------------------------------------
    avatar_url = await _get_avatar_url(u["usuario_id"])

    # -----------------------------------------------------------------
    # 6. Emitir JWT
    # Payload mínimo: lo que los endpoints protegidos necesitan del token
    # sin hacer una consulta extra a la BD.
    # -----------------------------------------------------------------
    payload = {
        "sub": u["usuario_id"],
        "tipo": u["usuario_tipo"],
        "rol": u["usuario_rol"],
        "org_id": u["org_id"],
        "nombre": u["usuario_nombre"],
    }
    token = crear_token_acceso(payload)

    usuario_schema = UsuarioSchema(
        usuario_id=u["usuario_id"],
        usuario_tipo=u["usuario_tipo"],
        usuario_rol=u["usuario_rol"],
        usuario_nombre=u["usuario_nombre"],
        usuario_apellidos=u.get("usuario_apellidos"),
        usuario_correo=u["usuario_correo"],
        usuario_idioma=u.get("usuario_idioma", "es"),
        usuario_modo_oscuro=u.get("usuario_modo_oscuro", False),
        avatar_url=avatar_url,
    )

    return LoginResponse(
        access_token=token,
        token_type="bearer",
        expires_in=settings.JWT_EXPIRE_MINUTES * 60,
        usuario=usuario_schema,
        organizacion=organizacion,
    )


# =============================================================================
# get_me()
# =============================================================================
async def get_me(usuario_id: str, org_id: str) -> MeResponse:
    """
    Rehidrata la sesión del usuario autenticado.
    Llamado desde GET /auth/me cuando la app se recarga.

    No re-verifica el password — el JWT ya fue validado por el dependency
    `get_usuario_actual` antes de llegar aquí.

    Pasos:
        1. Consulta el perfil actualizado del usuario desde `usuarios`.
        2. Consulta la organización para branding.
        3. Consulta avatar (best-effort).
        4. Construye y retorna MeResponse.
    """
    # -----------------------------------------------------------------
    # 1. Perfil del usuario (datos frescos desde BD, no del JWT)
    # Usamos datos frescos por si el usuario actualizó su perfil
    # después de emitir el token.
    # -----------------------------------------------------------------
    usuarios = await supabase_get(
        "usuarios",
        f"select=usuario_id,usuario_correo,usuario_tipo,usuario_rol,"
        f"usuario_nombre,usuario_apellidos,usuario_idioma,"
        f"usuario_modo_oscuro,org_id"
        f"&usuario_id=eq.{usuario_id}",
    )

    if not usuarios:
        # El usuario fue eliminado después de emitir el token
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no encontrado. Inicia sesión de nuevo.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    u = usuarios[0]

    # -----------------------------------------------------------------
    # 2. Organización
    # -----------------------------------------------------------------
    organizacion = await _get_organizacion(org_id)

    # -----------------------------------------------------------------
    # 3. Avatar
    # -----------------------------------------------------------------
    avatar_url = await _get_avatar_url(usuario_id)

    usuario_schema = UsuarioSchema(
        usuario_id=u["usuario_id"],
        usuario_tipo=u["usuario_tipo"],
        usuario_rol=u["usuario_rol"],
        usuario_nombre=u["usuario_nombre"],
        usuario_apellidos=u.get("usuario_apellidos"),
        usuario_correo=u["usuario_correo"],
        usuario_idioma=u.get("usuario_idioma", "es"),
        usuario_modo_oscuro=u.get("usuario_modo_oscuro", False),
        avatar_url=avatar_url,
    )

    return MeResponse(
        usuario=usuario_schema,
        organizacion=organizacion,
    )

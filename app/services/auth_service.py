# =============================================================================
# app/services/auth_service.py
# Lógica de negocio del módulo de autenticación.
#
# Los servicios mantienen los routers limpios: el router solo recibe la
# petición, llama al servicio y devuelve la respuesta. Toda la lógica
# (consultar BD, verificar hash, emitir token) vive aquí.
# =============================================================================
from datetime import datetime, timezone

from fastapi import HTTPException, status

from app.core.security import crear_token_acceso, verificar_password
from app.core.supabase import supabase_get, supabase_patch
from app.core.config import settings
from app.schemas.schemas import TokenResponse


async def login(correo: str, password: str) -> TokenResponse:
    """
    Valida credenciales contra Supabase y emite un JWT.

    Pasos:
        1. Busca el usuario por correo en la tabla `usuarios`.
        2. Si no existe → 401 (mensaje genérico para no revelar si el correo existe).
        3. Verifica el hash bcrypt con passlib.
        4. Si falla → 401.
        5. Actualiza `ultimo_acceso` en Supabase.
        6. Emite JWT con los campos mínimos necesarios.

    Retorna TokenResponse con el JWT y metadatos.
    """
    # -----------------------------------------------------------------
    # 1. Consultar usuario por correo
    # PostgREST filtra con: columna=eq.valor
    # select= especifica qué columnas traer (mínimas necesarias)
    # -----------------------------------------------------------------
    query = (
        "select=usuario_id,usuario_correo,usuario_password,"
        "usuario_tipo,usuario_rol,usuario_nombre,usuario_apellidos,org_id"
        f"&usuario_correo=eq.{correo}"
    )
    resultados = await supabase_get("usuarios", query)

    if not resultados:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Correo o contraseña incorrectos.",
        )

    usuario = resultados[0]

    # -----------------------------------------------------------------
    # 2. Verificar contraseña bcrypt
    # -----------------------------------------------------------------
    if not verificar_password(password, usuario["usuario_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Correo o contraseña incorrectos.",
        )

    # -----------------------------------------------------------------
    # 3. Actualizar último acceso (best-effort; no falla el login si falla)
    # -----------------------------------------------------------------
    try:
        ahora = datetime.now(timezone.utc).isoformat()
        await supabase_patch(
            "usuarios",
            f"usuario_id=eq.{usuario['usuario_id']}",
            {"ultimo_acceso": ahora},
        )
    except Exception:
        pass  # No bloquear el login por una actualización de auditoría

    # -----------------------------------------------------------------
    # 4. Emitir JWT
    # -----------------------------------------------------------------
    payload = {
        "sub": usuario["usuario_id"],          # identificador principal
        "tipo": usuario["usuario_tipo"],       # alumno | catedratico
        "rol": usuario["usuario_rol"],         # estudiante | administrador
        "org_id": usuario["org_id"],           # para filtros multi-tenant
        "nombre": usuario["usuario_nombre"],   # cómodo para el frontend
    }

    token = crear_token_acceso(payload)

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=settings.JWT_EXPIRE_MINUTES * 60,
        usuario_tipo=usuario["usuario_tipo"],
        usuario_rol=usuario["usuario_rol"],
    )

# =============================================================================
# app/core/deps.py
# FastAPI Dependencies (inyección de dependencias).
#
# El patrón Depends() de FastAPI permite reutilizar lógica de autenticación
# en cualquier endpoint sin repetir código. Si el token falla, FastAPI
# devuelve 401 automáticamente antes de ejecutar el handler.
# =============================================================================
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.security import decodificar_token

# Extrae el token del header: Authorization: Bearer <token>
_bearer = HTTPBearer()


async def get_usuario_actual(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> dict:
    """
    Dependency reutilizable: verifica el JWT y retorna el payload.

    Uso en cualquier endpoint protegido:
        @router.get("/ruta")
        async def mi_ruta(usuario: dict = Depends(get_usuario_actual)):
            ...

    El payload contiene: sub (usuario_id), tipo, rol, org_id.
    Lanza 401 si el token es inválido o expiró.
    """
    try:
        payload = decodificar_token(credentials.credentials)
        return payload
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado. Inicia sesión de nuevo.",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def require_alumno(
    usuario: dict = Depends(get_usuario_actual),
) -> dict:
    """
    Variante restrictiva: solo permite acceso a usuarios tipo 'alumno'.
    Lanza 403 si el usuario autenticado es catedrático u otro tipo.
    """
    if usuario.get("tipo") != "alumno":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Este endpoint es exclusivo para alumnos.",
        )
    return usuario

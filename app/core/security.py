# =============================================================================
# app/core/security.py
# Utilidades JWT y bcrypt.
#
# Flujo de autenticación:
#   1. Login recibe correo + contraseña en texto plano.
#   2. Se consulta el usuario en Supabase y se verifica el hash bcrypt.
#   3. Si es válido, se emite un JWT firmado con JWT_SECRET.
#   4. El frontend envía ese JWT en cada petición como:
#        Authorization: Bearer <token>
#   5. El dependency `get_usuario_actual` verifica y decodifica el token.
# =============================================================================
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

# Contexto bcrypt — compatible con los hashes generados por pgcrypto de PostgreSQL
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ---------------------------------------------------------------------------
# Contraseñas
# ---------------------------------------------------------------------------

def verificar_password(password_plano: str, hash_almacenado: str) -> bool:
    """
    Verifica si password_plano coincide con el hash bcrypt de la BD.
    passlib normaliza automáticamente el prefijo $2a$ / $2b$.
    """
    return _pwd_context.verify(password_plano, hash_almacenado)


# ---------------------------------------------------------------------------
# Tokens JWT
# ---------------------------------------------------------------------------

def crear_token_acceso(datos: dict) -> str:
    """
    Emite un JWT firmado con los datos del usuario autenticado.

    El payload incluye:
        sub          → usuario_id (identificador único)
        tipo         → 'alumno' | 'catedratico'
        rol          → 'estudiante' | 'administrador'
        org_id       → UUID de la organización
        exp          → timestamp de expiración (UTC)
    """
    payload = datos.copy()
    expira = datetime.now(timezone.utc) + timedelta(
        minutes=settings.JWT_EXPIRE_MINUTES
    )
    payload["exp"] = expira

    return jwt.encode(
        payload,
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )


def decodificar_token(token: str) -> dict:
    """
    Decodifica y valida el JWT.
    Lanza JWTError si el token es inválido o expiró.
    """
    return jwt.decode(
        token,
        settings.JWT_SECRET,
        algorithms=[settings.JWT_ALGORITHM],
    )

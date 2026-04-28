# app/core/security.py
from datetime import datetime, timedelta, timezone
import bcrypt
from jose import jwt
from app.core.config import settings


def verificar_password(password_plano: str, hash_almacenado: str) -> bool:
    """
    Verifica si password_plano coincide con el hash bcrypt de la BD.
    Usa bcrypt directamente, compatible con hashes $2a$ de pgcrypto.
    """
    return bcrypt.checkpw(
        password_plano.encode("utf-8"),
        hash_almacenado.encode("utf-8"),
    )


def crear_token_acceso(datos: dict) -> str:
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
    return jwt.decode(
        token,
        settings.JWT_SECRET,
        algorithms=[settings.JWT_ALGORITHM],
    )
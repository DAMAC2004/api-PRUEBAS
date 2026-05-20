# =============================================================================
# app/core/supabase.py
# Cliente HTTP que encapsula todas las llamadas a la REST API de Supabase.
#
# Fase B — nuevas funciones:
#   supabase_post()  → INSERT en una tabla (crea intento, etc.).
#   supabase_rpc()   → Llama a funciones PostgreSQL (actualizar_racha).
# =============================================================================
import httpx
from app.core.config import settings


def _headers() -> dict:
    return {
        "apikey": settings.SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _url(table: str, query: str = "") -> str:
    base = f"{settings.SUPABASE_URL}/rest/v1/{table}"
    return f"{base}?{query}" if query else base


async def supabase_get(table: str, query: str = "") -> list[dict]:
    """GET genérico — filtra filas de una tabla con query PostgREST."""
    async with httpx.AsyncClient() as client:
        response = await client.get(_url(table, query), headers=_headers())
        response.raise_for_status()
        return response.json()


async def supabase_post(table: str, payload: dict) -> dict:
    """
    INSERT una fila en la tabla y retorna la fila creada.
    Usa Prefer: return=representation para obtener la fila con defaults de BD.
    Lanza httpx.HTTPStatusError si Supabase responde con error (ej: UNIQUE violation).
    """
    async with httpx.AsyncClient() as client:
        response = await client.post(
            _url(table),
            headers=_headers(),
            json=payload,
        )
        response.raise_for_status()
        resultado = response.json()
        # Supabase devuelve lista con la fila insertada
        return resultado[0] if isinstance(resultado, list) else resultado


async def supabase_patch(table: str, query: str, payload: dict) -> list[dict]:
    """PATCH (actualización parcial) sobre filas que cumplan el filtro."""
    headers = {**_headers(), "Prefer": "return=representation"}
    async with httpx.AsyncClient() as client:
        response = await client.patch(
            _url(table, query),
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        return response.json()


async def supabase_rpc(funcion: str, params: dict) -> dict | list:
    """
    Llama a una función PostgreSQL vía POST /rest/v1/rpc/{funcion}.
    Se usa para actualizar_racha() y otras funciones de BD.

    Parámetros:
        funcion → nombre de la función en PostgreSQL.
        params  → dict con los argumentos de la función.

    Retorna el resultado de la función (puede ser dict, lista o escalar).
    """
    url = f"{settings.SUPABASE_URL}/rest/v1/rpc/{funcion}"
    async with httpx.AsyncClient() as client:
        response = await client.post(
            url,
            headers=_headers(),
            json=params,
        )
        response.raise_for_status()
        return response.json()

# =============================================================================
# app/core/supabase.py
# Cliente HTTP que encapsula todas las llamadas a la REST API de Supabase.
#
# Por qué usamos la REST API directamente en vez del SDK oficial:
#   - Evita instalar el SDK de Supabase (que arrastra muchas dependencias).
#   - Las llamadas son idénticas a las que ya probaste en Postman.
#   - El SERVICE_ROLE key bypasea RLS, lo que es correcto para operaciones
#     desde el servidor. El frontend NUNCA debe tener esta llave.
# =============================================================================
import httpx
from app.core.config import settings


def _headers() -> dict:
    """
    Cabeceras requeridas por Supabase para cada petición.
    apikey  → identifica el proyecto.
    Authorization → Bearer con service_role bypasea las políticas RLS.
    """
    return {
        "apikey": settings.SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _url(table: str, query: str = "") -> str:
    """Construye la URL del endpoint REST de Supabase para una tabla."""
    base = f"{settings.SUPABASE_URL}/rest/v1/{table}"
    return f"{base}?{query}" if query else base


async def supabase_get(table: str, query: str = "") -> list[dict]:
    """
    GET genérico sobre cualquier tabla de Supabase.

    Parámetros:
        table  — nombre de la tabla en PostgreSQL.
        query  — filtros PostgREST, ej: "select=*&usuario_id=eq.uuid123"

    Retorna lista de dicts (puede estar vacía).
    Lanza httpx.HTTPStatusError si Supabase responde con error HTTP.
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(_url(table, query), headers=_headers())
        response.raise_for_status()
        return response.json()


async def supabase_patch(table: str, query: str, payload: dict) -> list[dict]:
    """
    PATCH (actualización parcial) sobre filas que cumplan el filtro.

    Se usa para actualizar 'ultimo_acceso' del usuario tras un login exitoso.
    """
    headers = {**_headers(), "Prefer": "return=representation"}
    async with httpx.AsyncClient() as client:
        response = await client.patch(
            _url(table, query),
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        return response.json()

# =============================================================================
# app/services/contenidos_service.py
# Lógica de negocio para listado y acceso a contenidos — Fase C
# =============================================================================
from fastapi import HTTPException, status

from app.core.supabase import supabase_get
from app.core.config import settings
from app.schemas.schemas import (
    ContenidoListadoItemSchema,
    ContenidoUrlResponse,
    ContenidosListadoResponse,
)


def _construir_url(conten_url_publica: str | None, conten_s3_key: str) -> str:
    """
    Construye la URL de acceso al archivo del contenido.

    Prioridad:
        1. conten_url_publica si tiene valor — se devuelve directo.
        2. Si es null — se construye con el bucket público de Supabase Storage:
           {SUPABASE_URL}/storage/v1/object/public/contenidos/{conten_s3_key}

    El bucket 'contenidos' es público en Supabase Storage, por lo que
    no se necesitan URLs prefirmadas ni llamadas extra a la API de Storage.
    """
    if conten_url_publica:
        return conten_url_publica

    base = settings.SUPABASE_URL.rstrip("/")
    key = conten_s3_key.lstrip("/")
    return f"{base}/storage/v1/object/public/contenidos/{key}"


# =============================================================================
# listar_contenidos()
# =============================================================================
async def listar_contenidos(
    capaci_id: str,
    usuario_id: str,
) -> ContenidosListadoResponse:
    """
    Lista todos los contenidos de una capacitación.

    Verifica que el alumno esté inscrito en la capacitación antes de
    devolver los contenidos — un alumno no inscrito no debe ver el material.

    Ordena por caco_unidad ASC, caco_orden ASC para que el frontend
    reciba los ítems en el orden correcto sin tener que reordenar.
    """

    # -----------------------------------------------------------------
    # Verificar inscripción
    # -----------------------------------------------------------------
    inscripcion = await supabase_get(
        "capacitacion_usuario",
        f"select=capaci_id&usuario_id=eq.{usuario_id}&capaci_id=eq.{capaci_id}",
    )
    if not inscripcion:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No estás inscrito en esta capacitación.",
        )

    # -----------------------------------------------------------------
    # Contenidos de la capacitación
    # -----------------------------------------------------------------
    contenidos_raw = await supabase_get(
        "capacitacion_contenidos",
        f"select=conten_id,caco_unidad,caco_orden,"
        f"contenidos(conten_nombre,conten_descripcion,conten_tipo)"
        f"&capaci_id=eq.{capaci_id}"
        f"&order=caco_unidad.asc,caco_orden.asc",
    )

    items: list[ContenidoListadoItemSchema] = []
    for c in contenidos_raw:
        cont = c.get("contenidos") or {}
        items.append(
            ContenidoListadoItemSchema(
                conten_id=c["conten_id"],
                capaci_id=capaci_id,
                conten_nombre=cont.get("conten_nombre", "Sin nombre"),
                conten_descripcion=cont.get("conten_descripcion"),
                conten_tipo=cont.get("conten_tipo", "pdf"),
                caco_unidad=c["caco_unidad"],
                caco_orden=c["caco_orden"],
                conten_tamanio_kb=None,
                visto=False,
            )
        )

    return ContenidosListadoResponse(
        capaci_id=capaci_id,
        total=len(items),
        items=items,
    )


# =============================================================================
# obtener_url_contenido()
# =============================================================================
async def obtener_url_contenido(
    conten_id: str,
    usuario_id: str,
) -> ContenidoUrlResponse:
    """
    Devuelve la URL de acceso al archivo de un contenido.

    Verifica que el alumno esté inscrito en la capacitación a la que
    pertenece el contenido antes de revelar la URL.

    La URL se construye sin llamadas extra a la API de Storage porque
    el bucket 'contenidos' es público en Supabase.
    """

    # -----------------------------------------------------------------
    # 1. Datos del contenido
    # -----------------------------------------------------------------
    contenidos = await supabase_get(
        "contenidos",
        f"select=conten_id,conten_nombre,conten_tipo,"
        f"conten_s3_key,conten_url_publica"
        f"&conten_id=eq.{conten_id}",
    )

    if not contenidos:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contenido no encontrado.",
        )

    cont = contenidos[0]

    # -----------------------------------------------------------------
    # 2. Verificar que el alumno tiene acceso (está inscrito en la
    #    capacitación a la que pertenece este contenido)
    # -----------------------------------------------------------------
    pertenencia = await supabase_get(
        "capacitacion_contenidos",
        f"select=capaci_id&conten_id=eq.{conten_id}&limit=1",
    )

    if not pertenencia:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Este contenido no pertenece a ninguna capacitación.",
        )

    capaci_id = pertenencia[0]["capaci_id"]

    inscripcion = await supabase_get(
        "capacitacion_usuario",
        f"select=capaci_id&usuario_id=eq.{usuario_id}&capaci_id=eq.{capaci_id}",
    )

    if not inscripcion:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes acceso a este contenido.",
        )

    # -----------------------------------------------------------------
    # 3. Construir URL
    # -----------------------------------------------------------------
    url = _construir_url(
        cont.get("conten_url_publica"),
        cont.get("conten_s3_key", ""),
    )

    return ContenidoUrlResponse(
        conten_id=conten_id,
        conten_nombre=cont["conten_nombre"],
        conten_tipo=cont["conten_tipo"],
        url=url,
        expira_en=None,
    )

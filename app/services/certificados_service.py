# =============================================================================
# app/services/certificados_service.py
# Lógica de negocio para listado de certificados — Fase D
# =============================================================================
from app.core.supabase import supabase_get
from app.schemas.schemas import (
    CertificadoItemSchema,
    CertificadosListadoResponse,
)


async def listar_certificados(usuario_id: str) -> CertificadosListadoResponse:
    """
    Lista todos los certificados del alumno.

    Para obtener el nombre de la capacitación navega:
        exam_id → capacitacion_examenes → capaci_id → capacitaciones

    Los catedráticos firmantes (catedratico_certificado) NO se incluyen
    en el listado — solo se mostrarán en el detalle individual (Fase E).
    """

    # -----------------------------------------------------------------
    # 1. Certificados del alumno
    # -----------------------------------------------------------------
    certificados_raw = await supabase_get(
        "certificados",
        f"select=cert_id,cert_folio,exam_id,intento_id,"
        f"cert_emitido_en,cert_pdf_url,cert_qr_url"
        f"&usuario_id=eq.{usuario_id}"
        f"&order=cert_emitido_en.desc",
    )

    if not certificados_raw:
        return CertificadosListadoResponse(total=0, items=[])

    # -----------------------------------------------------------------
    # 2. Nombre del examen y capacitación para cada certificado
    # -----------------------------------------------------------------
    exam_ids = list({c["exam_id"] for c in certificados_raw})
    exam_ids_str = ",".join(exam_ids)

    # JOIN: capacitacion_examenes → capacitaciones + examenes
    cap_examenes_raw = await supabase_get(
        "capacitacion_examenes",
        f"select=exam_id,capaci_id,"
        f"examenes(exam_nombre),"
        f"capacitaciones(capaci_nombre)"
        f"&exam_id=in.({exam_ids_str})",
    )

    # Indexar por exam_id
    info_por_exam: dict[str, dict] = {}
    for ce in cap_examenes_raw:
        exam_data = ce.get("examenes") or {}
        cap_data = ce.get("capacitaciones") or {}
        if isinstance(cap_data, list):
            cap_data = cap_data[0] if cap_data else {}
        info_por_exam[ce["exam_id"]] = {
            "capaci_id": ce.get("capaci_id"),
            "capaci_nombre": cap_data.get("capaci_nombre"),
            "exam_nombre": exam_data.get("exam_nombre", "Sin nombre"),
        }

    # -----------------------------------------------------------------
    # 3. Construir items
    # -----------------------------------------------------------------
    items: list[CertificadoItemSchema] = []

    for cert in certificados_raw:
        exam_id = cert["exam_id"]
        info = info_por_exam.get(exam_id, {})

        items.append(
            CertificadoItemSchema(
                cert_id=cert["cert_id"],
                cert_folio=cert["cert_folio"],
                exam_id=exam_id,
                exam_nombre=info.get("exam_nombre", "Sin nombre"),
                capaci_id=info.get("capaci_id"),
                capaci_nombre=info.get("capaci_nombre"),
                cert_emitido_en=str(cert["cert_emitido_en"]),
                cert_pdf_url=cert.get("cert_pdf_url"),
                cert_qr_url=cert.get("cert_qr_url"),
            )
        )

    return CertificadosListadoResponse(total=len(items), items=items)

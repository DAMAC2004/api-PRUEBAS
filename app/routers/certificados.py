# =============================================================================
# app/routers/certificados.py
# Endpoint de certificados para el alumno — Fase D
# =============================================================================
from fastapi import APIRouter, Depends

from app.core.deps import require_alumno
from app.schemas.schemas import CertificadosListadoResponse, ErrorResponse
from app.services import certificados_service

router = APIRouter(prefix="/alumno/certificados", tags=["Alumno — Certificados"])


@router.get(
    "",
    response_model=CertificadosListadoResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Token inválido."},
        403: {"model": ErrorResponse, "description": "Solo para alumnos."},
    },
    summary="Certificados del alumno",
    description="""
Lista todos los certificados emitidos al alumno, ordenados del más reciente
al más antiguo.

**Incluye por certificado:**
- `cert_folio` — folio único del certificado.
- `cert_pdf_url` — URL directa al PDF. Puede ser `null` si aún no se generó.
- `cert_qr_url` — URL del código QR de verificación. Puede ser `null`.
- `capaci_nombre` — nombre de la capacitación (obtenido navegando
  `exam_id → capacitacion_examenes → capacitaciones`).

Los catedráticos firmantes solo aparecen en el detalle individual
(fuera del scope de Fase D).
""",
)
async def certificados(
    usuario: dict = Depends(require_alumno),
) -> CertificadosListadoResponse:
    return await certificados_service.listar_certificados(usuario_id=usuario["sub"])

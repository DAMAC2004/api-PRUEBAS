# =============================================================================
# app/routers/intentos.py
# Endpoints del motor de intento: autosave, entregar y retomar — Fase B
# =============================================================================
from fastapi import APIRouter, Depends, Response

from app.core.deps import require_alumno
from app.schemas.schemas import (
    AutosaveRequest,
    AutosaveResponse,
    EntregarRequest,
    EntregarResponse,
    ErrorResponse,
    IntentoEnProgresoDetalleResponse,
)
from app.services import intentos_service

router = APIRouter(prefix="/alumno/intentos", tags=["Alumno — Motor de Examen"])


@router.get(
    "/en_progreso",
    responses={
        200: {"model": IntentoEnProgresoDetalleResponse},
        204: {"description": "No hay ningún intento EN_PROGRESO activo."},
        401: {"model": ErrorResponse, "description": "Token inválido."},
        403: {"model": ErrorResponse, "description": "Solo para alumnos."},
    },
    summary="Obtener intento en progreso",
    description="""
Retorna el intento EN_PROGRESO del alumno con todo el detalle necesario
para que el frontend muestre el modal 'Retomar examen' o restaure el
estado exacto del examen.

**Respuesta 204** si no hay ningún intento activo (el alumno no tiene
ningún examen pendiente de terminar).

**Incluye:**
- Preguntas completas del examen (sin respuestas correctas).
- `progreso_guardado` — último autosave con respuestas marcadas hasta ese momento.
- `tiempo_restante_seg` — calculado por la API desde el último sync.
""",
)
async def intento_en_progreso(
    response: Response,
    usuario: dict = Depends(require_alumno),
):
    resultado = await intentos_service.obtener_intento_en_progreso(
        usuario_id=usuario["sub"],
    )
    if resultado is None:
        response.status_code = 204
        return None
    return resultado


@router.patch(
    "/{intento_id}/autosave",
    response_model=AutosaveResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Token inválido."},
        403: {"model": ErrorResponse, "description": "No eres el dueño del intento."},
        404: {"model": ErrorResponse, "description": "Intento no encontrado."},
        409: {
            "model": ErrorResponse,
            "description": "Estado inválido para autosave (INVALID_STATE).",
        },
    },
    summary="Autosave del progreso del examen",
    description="""
Guarda el estado actual del examen. El frontend llama este endpoint
automáticamente cada 30 segundos mientras el alumno está respondiendo.

**Verificaciones:**
- El intento pertenece al alumno autenticado.
- El intento está en estado `EN_PROGRESO`.

**Body:**
```json
{
  "respuestas": {
    "a1b2c3d4-e5f6-7890-abcd-ef1234567801": "B",
    "b2c3d4e5-f6a7-8901-bcde-f12345678902": "A"
  },
  "marcadas": ["c3d4e5f6-a7b8-9012-cdef-123456789003"]
}
```
Las keys de `respuestas` son los `id_pregunta` UUID del examen.
`marcadas` son preguntas que el alumno quiere revisar antes de entregar.

**`tiempo_restante_seg`** es calculado por la API y devuelto en la respuesta
para que el frontend sincronice su timer.
""",
)
async def autosave(
    intento_id: str,
    body: AutosaveRequest,
    usuario: dict = Depends(require_alumno),
) -> AutosaveResponse:
    return await intentos_service.autosave_intento(
        intento_id=intento_id,
        usuario_id=usuario["sub"],
        body=body,
    )


@router.post(
    "/{intento_id}/entregar",
    response_model=EntregarResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Token inválido."},
        403: {"model": ErrorResponse, "description": "No eres el dueño del intento."},
        404: {"model": ErrorResponse, "description": "Intento no encontrado."},
        409: {
            "model": ErrorResponse,
            "description": "El intento no está EN_PROGRESO (INVALID_STATE).",
        },
    },
    summary="Entregar examen",
    description="""
Hace la entrega final del examen. Equivale a un último autosave que
adicionalmente marca el intento como `COMPLETADO`.

**La calificación y el feedback NO se calculan en este momento.**
Los resultados solo se disponibilizan cuando el período de evaluación
cierra (`exam_fecha_vencimiento`). Hasta entonces el alumno ve
la pantalla de 'Examen entregado — resultados pendientes'.

**Body:** mismo contrato que autosave (estado final de las respuestas).

**Efectos colaterales:**
- Incrementa `meus_examenes_presentados` en `metricas_usuario`.
- Llama a `actualizar_racha()` en la BD vía RPC.
""",
)
async def entregar(
    intento_id: str,
    body: EntregarRequest,
    usuario: dict = Depends(require_alumno),
) -> EntregarResponse:
    return await intentos_service.entregar_intento(
        intento_id=intento_id,
        usuario_id=usuario["sub"],
        body=body,
    )

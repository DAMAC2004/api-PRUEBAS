# =============================================================================
# app/routers/examenes.py
# Endpoints de consulta de exámenes para el alumno — Fase B
# =============================================================================
from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.core.deps import require_alumno
from app.schemas.schemas import (
    ErrorResponse,
    ExamenDetalleResponse,
    ExamenesListadoResponse,
    IniciarIntentoResponse,
)
from app.services import examenes_service, intentos_service

router = APIRouter(prefix="/alumno/examenes", tags=["Alumno — Exámenes"])


@router.get(
    "",
    response_model=ExamenesListadoResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Token inválido."},
        403: {"model": ErrorResponse, "description": "Solo para alumnos."},
    },
    summary="Listado de exámenes del alumno",
    description="""
Lista todos los exámenes de las capacitaciones en las que el alumno está inscrito.

**Filtros opcionales (query params):**
- `estado` — `pendiente` | `en_progreso` | `completado` | `expirado` (omitir = todos).
- `capaci_id` — filtrar por capacitación específica.

**La respuesta es una lista plana.** El frontend agrupa visualmente por
capacitación y por estado (Pendientes / Terminados).

**Campos clave:**
- `estado_intento` — estado consolidado del alumno en ese examen.
- `mejor_calificacion` — mayor calificación obtenida. `null` si no ha completado ninguno.
- `exam_tema` — subtema principal extraído del exam_json (generado por Bedrock).
""",
)
async def listar_examenes(
    estado: Optional[str] = Query(
        None,
        description="Filtrar por estado: pendiente | en_progreso | completado | expirado.",
    ),
    capaci_id: Optional[str] = Query(
        None, description="UUID de la capacitación para filtrar."
    ),
    usuario: dict = Depends(require_alumno),
) -> ExamenesListadoResponse:
    return await examenes_service.listar_examenes(
        usuario_id=usuario["sub"],
        estado=estado,
        capaci_id=capaci_id,
    )


@router.get(
    "/{exam_id}",
    response_model=ExamenDetalleResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Token inválido."},
        403: {"model": ErrorResponse, "description": "No inscrito en la capacitación."},
        404: {"model": ErrorResponse, "description": "Examen no encontrado."},
    },
    summary="Detalle pre-inicio de un examen",
    description="""
Retorna la información completa del examen para la pantalla de preparación
antes de que el alumno decida iniciar.

**No revela las preguntas** — esas se entregan en `POST /{exam_id}/iniciar`.

**Incluye:**
- Meta-información: nombre, dificultad, tiempo límite, calificación mínima.
- `distribución` — desglose por tipo (simple/múltiple) y dificultad.
- `intentos_disponibles` — cuántos le quedan al alumno.
- `mejor_calificacion` — su mejor marca si ya intentó antes.
""",
)
async def detalle_examen(
    exam_id: str,
    usuario: dict = Depends(require_alumno),
) -> ExamenDetalleResponse:
    return await examenes_service.obtener_detalle_examen(
        exam_id=exam_id,
        usuario_id=usuario["sub"],
    )


@router.post(
    "/{exam_id}/iniciar",
    response_model=IniciarIntentoResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Token inválido."},
        403: {
            "model": ErrorResponse,
            "description": "No inscrito, intentos agotados (MAX_ATTEMPTS_REACHED) o examen cerrado (EXAM_EXPIRED).",
        },
        404: {"model": ErrorResponse, "description": "Examen no encontrado."},
        409: {"model": ErrorResponse, "description": "Intento duplicado (DUPLICATE_ATTEMPT)."},
    },
    summary="Iniciar o retomar un examen",
    description="""
Crea un nuevo intento o recupera el intento EN_PROGRESO existente.

**Verificaciones en orden:**
1. El alumno está inscrito en la capacitación del examen.
2. No hay intento EN_PROGRESO duplicado (race condition).
3. **Caso A** — sin intentos → crea uno nuevo.
4. **Caso B** — tiene EN_PROGRESO → retorna ese intento con el progreso guardado (`es_retoma: true`).
5. **Caso C** — intentos >= intentos_max → 403 `MAX_ATTEMPTS_REACHED`.
6. **Caso D** — intento EXPIRADO con fecha_fin ya pasada → 403 `EXAM_EXPIRED`.

**La respuesta incluye las preguntas** (sin revelar respuestas correctas)
y `progreso_guardado` con el último autosave si es retoma.

**`tiempo_restante_seg`** es calculado por la API, no viene del cliente.
""",
)
async def iniciar_examen(
    exam_id: str,
    usuario: dict = Depends(require_alumno),
) -> IniciarIntentoResponse:
    return await intentos_service.iniciar_intento(
        exam_id=exam_id,
        usuario_id=usuario["sub"],
    )

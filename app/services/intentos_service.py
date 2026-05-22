# =============================================================================
# app/services/intentos_service.py
# Lógica del motor de examen: iniciar, autosave, entregar y retomar — Fase B
# =============================================================================
import uuid
from datetime import datetime, timezone, timedelta

from fastapi import HTTPException, status

from app.core.supabase import supabase_get, supabase_post, supabase_patch, supabase_rpc
from app.schemas.schemas import (
    AutosaveRequest,
    AutosaveResponse,
    EntregarRequest,
    EntregarResponse,
    IniciarIntentoResponse,
    IntentoEnProgresoDetalleResponse,
    OpcionSchema,
    PreguntaExamenSchema,
)


# ---------------------------------------------------------------------------
# Helpers privados
# ---------------------------------------------------------------------------

def _ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _parsear_preguntas(exam_json: dict) -> list[PreguntaExamenSchema]:
    """
    Convierte el array 'preguntas' del exam_json en una lista de
    PreguntaExamenSchema para enviar al alumno.

    IMPORTANTE: no incluye `es_correcta` ni `explicacion` —
    esos campos solo se revelan post fecha_fin del examen.
    """
    preguntas_raw = exam_json.get("preguntas", [])
    resultado = []
    for p in preguntas_raw:
        opciones = [
            OpcionSchema(letra=o["letra"], texto=o["texto"])
            for o in p.get("opciones", [])
        ]
        resultado.append(
            PreguntaExamenSchema(
                id_pregunta=p["id_pregunta"],
                enunciado=p["enunciado"],
                tipo_pregunta=p.get("tipo_pregunta", "simple"),
                opciones=opciones,
                tiempo_estimado=p.get("tiempo_estimado"),
                svg=p.get("svg"),
            )
        )
    return resultado


def _calcular_tiempo_restante(
    fecha_inicio_str: str,
    tiempo_limite_min: int,
    progreso_json: dict | None,
) -> int:
    """
    Calcula los segundos restantes para el examen.

    Si hay un autosave previo con `tiempo_restante_seg`, lo usa como base
    y descuenta el tiempo transcurrido desde `inex_ultima_sync`.
    Si no hay autosave, calcula desde fecha_inicio.

    Retorna 0 si el tiempo ya expiró.
    """
    ahora = _ahora_utc()
    tiempo_total_seg = tiempo_limite_min * 60

    if progreso_json and "tiempo_restante_seg" in progreso_json:
        # Hay autosave — estimar desde última sincronización
        ultima_sync_str = progreso_json.get("ultima_sync")
        if ultima_sync_str:
            try:
                ultima_sync = datetime.fromisoformat(ultima_sync_str)
                if ultima_sync.tzinfo is None:
                    ultima_sync = ultima_sync.replace(tzinfo=timezone.utc)
                transcurrido = (ahora - ultima_sync).total_seconds()
                restante = int(progreso_json["tiempo_restante_seg"] - transcurrido)
                return max(0, restante)
            except Exception:
                pass

    # Sin autosave o sin sync — calcular desde fecha_inicio
    try:
        fecha_inicio = datetime.fromisoformat(fecha_inicio_str)
        if fecha_inicio.tzinfo is None:
            fecha_inicio = fecha_inicio.replace(tzinfo=timezone.utc)
        transcurrido = (ahora - fecha_inicio).total_seconds()
        return max(0, int(tiempo_total_seg - transcurrido))
    except Exception:
        return tiempo_total_seg


# =============================================================================
# iniciar_intento()
# =============================================================================
async def iniciar_intento(exam_id: str, usuario_id: str) -> IniciarIntentoResponse:
    """
    Crea un nuevo intento o retoma el EN_PROGRESO existente.

    Verificaciones en orden:
        0. Anti-duplicado en Python (el índice único de BD es la red de seguridad).
        A. Sin intentos → crear nuevo.
        B. Tiene EN_PROGRESO → retomar.
        C. Intentos >= max → 403 MAX_ATTEMPTS_REACHED.
        D. Tiene EXPIRADO y fecha_fin < ahora → 403 EXAM_EXPIRED.
    """

    # -----------------------------------------------------------------
    # Cargar datos del examen
    # -----------------------------------------------------------------
    examen_raw = await supabase_get(
        "capacitacion_examenes",
        f"select=capaci_id,exam_id,"
        f"examenes(exam_nombre,exam_intentos_max,exam_tiempo_limite,"
        f"exam_fecha_vencimiento,exam_json)"
        f"&exam_id=eq.{exam_id}",
    )
    if not examen_raw:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Examen no encontrado.")

    e = examen_raw[0]
    exam_data = e.get("examenes") or {}
    exam_json = exam_data.get("exam_json") or {}
    intentos_max = exam_data.get("exam_intentos_max", 3)
    tiempo_limite_min = exam_data.get("exam_tiempo_limite", 60)
    tiempo_limite_seg = tiempo_limite_min * 60

    # Verificar inscripción
    inscripcion = await supabase_get(
        "capacitacion_usuario",
        f"select=capaci_id&usuario_id=eq.{usuario_id}&capaci_id=eq.{e['capaci_id']}",
    )
    if not inscripcion:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No estás inscrito en la capacitación de este examen.",
        )

    # -----------------------------------------------------------------
    # Cargar intentos existentes del alumno para este examen
    # -----------------------------------------------------------------
    intentos = await supabase_get(
        "intentos_examen",
        f"select=intento_id,inex_estado,inex_numero_intento,"
        f"inex_fecha_inicio,inex_fecha_fin,inex_progreso_json,inex_ultima_sync"
        f"&usuario_id=eq.{usuario_id}&exam_id=eq.{exam_id}"
        f"&order=inex_numero_intento.desc",
    )

    # -----------------------------------------------------------------
    # Caso B — tiene EN_PROGRESO → retomar
    # -----------------------------------------------------------------
    en_progreso = next(
        (i for i in intentos if i["inex_estado"] == "EN_PROGRESO"), None
    )
    if en_progreso:
        progreso_json = en_progreso.get("inex_progreso_json") or {}
        tiempo_restante = _calcular_tiempo_restante(
            en_progreso["inex_fecha_inicio"],
            tiempo_limite_min,
            progreso_json,
        )
        preguntas = _parsear_preguntas(exam_json)

        return IniciarIntentoResponse(
            intento_id=en_progreso["intento_id"],
            exam_id=exam_id,
            numero_intento=en_progreso["inex_numero_intento"],
            es_retoma=True,
            fecha_inicio=str(en_progreso["inex_fecha_inicio"]),
            tiempo_limite_seg=tiempo_limite_seg,
            tiempo_restante_seg=tiempo_restante,
            preguntas=preguntas,
            progreso_guardado=progreso_json if progreso_json else None,
        )

    # -----------------------------------------------------------------
    # Caso C — agotó intentos (EXPIRADOS cuentan)
    # -----------------------------------------------------------------
    if len(intentos) >= intentos_max:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Has agotado el número máximo de intentos para este examen.",
            headers={"X-Error-Code": "MAX_ATTEMPTS_REACHED"},
        )

    # -----------------------------------------------------------------
    # Caso D — tiene intento EXPIRADO con fecha_fin < ahora
    # -----------------------------------------------------------------
    ahora = _ahora_utc()
    for intento in intentos:
        if intento["inex_estado"] == "EXPIRADO":
            fecha_fin_str = intento.get("inex_fecha_fin")
            if fecha_fin_str:
                try:
                    fecha_fin = datetime.fromisoformat(str(fecha_fin_str))
                    if fecha_fin.tzinfo is None:
                        fecha_fin = fecha_fin.replace(tzinfo=timezone.utc)
                    if ahora >= fecha_fin:
                        raise HTTPException(
                            status_code=status.HTTP_403_FORBIDDEN,
                            detail="El período de evaluación de este examen ha cerrado.",
                            headers={"X-Error-Code": "EXAM_EXPIRED"},
                        )
                except HTTPException:
                    raise
                except Exception:
                    pass

    # -----------------------------------------------------------------
    # Caso A — crear nuevo intento
    # -----------------------------------------------------------------
    numero_intento = len(intentos) + 1
    ahora_iso = _iso(ahora)
    nuevo_intento_id = str(uuid.uuid4())

    try:
        fila = await supabase_post(
            "intentos_examen",
            {
                "intento_id": nuevo_intento_id,
                "usuario_id": usuario_id,
                "exam_id": exam_id,
                "inex_estado": "EN_PROGRESO",
                "inex_numero_intento": numero_intento,
                "inex_fecha_inicio": ahora_iso,
                "inex_progreso_json": {},
            },
        )
    except Exception as exc:
        # El índice único (usuario_id, exam_id, EN_PROGRESO) detectó race condition
        if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ya existe un intento en progreso para este examen. Recarga la app.",
                headers={"X-Error-Code": "DUPLICATE_ATTEMPT"},
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al crear el intento. Intenta de nuevo.",
        )

    preguntas = _parsear_preguntas(exam_json)

    return IniciarIntentoResponse(
        intento_id=fila.get("intento_id", nuevo_intento_id),
        exam_id=exam_id,
        numero_intento=numero_intento,
        es_retoma=False,
        fecha_inicio=ahora_iso,
        tiempo_limite_seg=tiempo_limite_seg,
        tiempo_restante_seg=tiempo_limite_seg,
        preguntas=preguntas,
        progreso_guardado=None,
    )


# =============================================================================
# autosave_intento()
# =============================================================================
async def autosave_intento(
    intento_id: str,
    usuario_id: str,
    body: AutosaveRequest,
) -> AutosaveResponse:
    """
    Guarda el progreso actual del examen (heartbeat cada 30s).

    Verificaciones:
        - El intento existe.
        - Pertenece al usuario del JWT (previene que un usuario guarde en el intento de otro).
        - Estado es EN_PROGRESO (no COMPLETADO ni EXPIRADO).
    """

    # -----------------------------------------------------------------
    # Cargar el intento
    # -----------------------------------------------------------------
    intentos = await supabase_get(
        "intentos_examen",
        f"select=intento_id,usuario_id,exam_id,inex_estado,"
        f"inex_fecha_inicio,examenes(exam_tiempo_limite)"
        f"&intento_id=eq.{intento_id}",
    )
    if not intentos:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Intento no encontrado.")

    intento = intentos[0]

    # Verificar propiedad
    if intento["usuario_id"] != usuario_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permiso para modificar este intento.",
        )

    # Verificar estado
    if intento["inex_estado"] != "EN_PROGRESO":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"No se puede autosave: el intento está en estado '{intento['inex_estado']}'.",
            headers={"X-Error-Code": "INVALID_STATE"},
        )

    # -----------------------------------------------------------------
    # Calcular tiempo restante
    # -----------------------------------------------------------------
    exam_data = intento.get("examenes") or {}
    tiempo_limite_min = exam_data.get("exam_tiempo_limite", 60)
    ahora = _ahora_utc()
    ahora_iso = _iso(ahora)

    tiempo_restante = _calcular_tiempo_restante(
        str(intento["inex_fecha_inicio"]),
        tiempo_limite_min,
        None,  # calculamos desde fecha_inicio para consistencia
    )

    # -----------------------------------------------------------------
    # Construir progreso_json con timestamp de sync
    # -----------------------------------------------------------------
    progreso_json = {
        "respuestas": body.respuestas,
        "marcadas": body.marcadas,
        "tiempo_restante_seg": tiempo_restante,
        "ultima_sync": ahora_iso,
    }

    # -----------------------------------------------------------------
    # PATCH al intento
    # -----------------------------------------------------------------
    await supabase_patch(
        "intentos_examen",
        f"intento_id=eq.{intento_id}",
        {
            "inex_progreso_json": progreso_json,
            "inex_ultima_sync": ahora_iso,
        },
    )

    return AutosaveResponse(
        intento_id=intento_id,
        synced_at=ahora_iso,
        tiempo_restante_seg=tiempo_restante,
    )


# =============================================================================
# entregar_intento()
# =============================================================================
async def entregar_intento(
    intento_id: str,
    usuario_id: str,
    body: EntregarRequest,
) -> EntregarResponse:
    """
    Entrega final del examen.

    Flujo:
        1. Verificar propiedad y estado EN_PROGRESO.
        2. Guardar respuestas finales en inex_progreso_json.
        3. Marcar intento como COMPLETADO con inex_fecha_fin = NOW().
        4. Incrementar meus_examenes_presentados en metricas_usuario.
        5. Llamar actualizar_racha() via RPC.
        6. Retornar confirmación con fecha de disponibilidad de resultados.

    La calificación y el feedback NO se calculan aquí.
    Se disponibilizan cuando inex_fecha_fin del examen supere la fecha actual.
    """

    # -----------------------------------------------------------------
    # 1. Cargar y verificar el intento
    # -----------------------------------------------------------------
    intentos = await supabase_get(
        "intentos_examen",
        f"select=intento_id,usuario_id,exam_id,inex_estado,"
        f"inex_fecha_inicio,examenes(exam_tiempo_limite,exam_fecha_vencimiento)"
        f"&intento_id=eq.{intento_id}",
    )
    if not intentos:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Intento no encontrado.")

    intento = intentos[0]

    if intento["usuario_id"] != usuario_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permiso para entregar este intento.",
        )

    if intento["inex_estado"] != "EN_PROGRESO":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"No se puede entregar: el intento está en estado '{intento['inex_estado']}'.",
            headers={"X-Error-Code": "INVALID_STATE"},
        )

    # -----------------------------------------------------------------
    # 2 + 3. Guardar respuestas finales y marcar COMPLETADO
    # -----------------------------------------------------------------
    ahora = _ahora_utc()
    ahora_iso = _iso(ahora)

    exam_data = intento.get("examenes") or {}
    tiempo_limite_min = exam_data.get("exam_tiempo_limite", 60)

    progreso_final = {
        "respuestas": body.respuestas,
        "marcadas": body.marcadas,
        "tiempo_restante_seg": _calcular_tiempo_restante(
            str(intento["inex_fecha_inicio"]),
            tiempo_limite_min,
            None,
        ),
        "ultima_sync": ahora_iso,
        "entregado_manualmente": True,
    }

    await supabase_patch(
        "intentos_examen",
        f"intento_id=eq.{intento_id}",
        {
            "inex_estado": "COMPLETADO",
            "inex_fecha_fin": ahora_iso,
            "inex_progreso_json": progreso_final,
            "inex_ultima_sync": ahora_iso,
        },
    )

    # -----------------------------------------------------------------
    # 4. Incrementar examenes_presentados en metricas_usuario
    # -----------------------------------------------------------------
    try:
        metricas = await supabase_get(
            "metricas_usuario",
            f"select=meus_examenes_presentados&usuario_id=eq.{usuario_id}",
        )
        if metricas:
            nuevo_total = (metricas[0].get("meus_examenes_presentados") or 0) + 1
            await supabase_patch(
                "metricas_usuario",
                f"usuario_id=eq.{usuario_id}",
                {"meus_examenes_presentados": nuevo_total},
            )
    except Exception:
        pass  # No bloquear la entrega por error en métricas

    # -----------------------------------------------------------------
    # 5. Actualizar racha via RPC
    # -----------------------------------------------------------------
    try:
        await supabase_rpc("actualizar_racha", {"p_usuario_id": usuario_id})
    except Exception:
        pass  # No bloquear la entrega por error en racha

    # -----------------------------------------------------------------
    # 6. Construir respuesta con fecha de resultados
    # -----------------------------------------------------------------
    fecha_venc = exam_data.get("exam_fecha_vencimiento")
    resultados_en = str(fecha_venc) if fecha_venc else None

    return EntregarResponse(
        intento_id=intento_id,
        estado="COMPLETADO",
        entregado_en=ahora_iso,
        resultados_disponibles_en=resultados_en,
    )


# =============================================================================
# obtener_intento_en_progreso()
# =============================================================================
async def obtener_intento_en_progreso(
    usuario_id: str,
) -> IntentoEnProgresoDetalleResponse | None:
    """
    Retorna el intento EN_PROGRESO del alumno con detalle completo,
    incluyendo preguntas y progreso guardado para restaurar el estado.

    Retorna None si no hay ningún intento activo
    (el router devuelve 204 en ese caso).
    """

    intentos = await supabase_get(
        "intentos_examen",
        f"select=intento_id,exam_id,inex_estado,inex_numero_intento,"
        f"inex_fecha_inicio,inex_progreso_json,"
        f"examenes(exam_nombre,exam_tiempo_limite,exam_json)"
        f"&usuario_id=eq.{usuario_id}"
        f"&inex_estado=eq.EN_PROGRESO"
        f"&limit=1",
    )

    if not intentos:
        return None

    ia = intentos[0]
    exam_id = ia.get("exam_id")

    # Segunda query para obtener capaci_id
    cap_exam_rows = await supabase_get(
        "capacitacion_examenes",
        f"select=capaci_id,capacitaciones(capaci_nombre)&exam_id=eq.{exam_id}&limit=1",
    )
    cap_exam = cap_exam_rows[0] if cap_exam_rows else {}
    capaci_data = cap_exam.get("capacitaciones") or {}

    tiempo_limite_min = exam_data.get("exam_tiempo_limite", 60)
    progreso_json = ia.get("inex_progreso_json") or {}

    tiempo_restante = _calcular_tiempo_restante(
        str(ia["inex_fecha_inicio"]),
        tiempo_limite_min,
        progreso_json,
    )

    preguntas = _parsear_preguntas(exam_json)

    return IntentoEnProgresoDetalleResponse(
        intento_id=ia["intento_id"],
        exam_id=ia["exam_id"],
        exam_nombre=exam_data.get("exam_nombre", "Sin nombre"),
        capaci_id=cap_exam.get("capaci_id", ""),
        capaci_nombre=capaci_data.get("capaci_nombre", "Sin nombre"),
        numero_intento=ia["inex_numero_intento"],
        fecha_inicio=str(ia["inex_fecha_inicio"]),
        tiempo_limite_seg=tiempo_limite_min * 60,
        tiempo_restante_seg=tiempo_restante,
        preguntas=preguntas,
        progreso_guardado=progreso_json if progreso_json else None,
    )

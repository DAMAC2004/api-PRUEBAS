# =============================================================================
# app/schemas/schemas.py
# Modelos Pydantic v2 — Fase A
#
# Convención de nombres:
#   *Request  → Body que llega del cliente (POST/PUT).
#   *Response → Lo que la API devuelve al cliente.
#
# Cambios Fase A respecto a la versión anterior:
#   - LoginResponse ampliado: incluye objeto `usuario` y `organizacion`
#     para que el frontend aplique el branding y redirigir correctamente.
#   - Nuevos schemas: UsuarioSchema, OrganizacionSchema, MeResponse.
#   - DashboardAlumnoResponse reestructurado para coincidir con el contrato
#     que espera el frontend de Lovable (mockDashboardResponse):
#       · `racha` → renombrado a `metricas` y expandido con totales de capacitaciones.
#       · `cursos_pendientes` → renombrado a `capacitaciones`.
#       · Se agrega `intento_en_progreso` (nullable).
#       · Se agrega `contenidos_recientes` (lista vacía en Fase A, se puebla en Fase C).
# =============================================================================

from typing import Optional
from pydantic import BaseModel, EmailStr, Field


# =============================================================================
# SHARED — Bloques reutilizables en varios endpoints
# =============================================================================

class UsuarioSchema(BaseModel):
    """
    Perfil público del usuario autenticado.
    Se incluye en el login y en /auth/me para que el frontend
    tenga los datos del usuario sin necesidad de una llamada extra.
    avatar_url puede ser null si el alumno no ha subido foto.
    """

    usuario_id: str = Field(..., description="UUID del usuario.")
    usuario_tipo: str = Field(..., description="'alumno' o 'catedratico'.")
    usuario_rol: str = Field(..., description="'estudiante' o 'administrador'.")
    usuario_nombre: str = Field(..., description="Nombre de pila.")
    usuario_apellidos: Optional[str] = Field(None, description="Apellidos. Puede ser null.")
    usuario_correo: str = Field(..., description="Correo institucional.")
    usuario_idioma: str = Field(default="es", description="Código de idioma. Default 'es'.")
    usuario_modo_oscuro: bool = Field(default=False, description="Preferencia de tema.")
    avatar_url: Optional[str] = Field(
        None,
        description="URL del avatar en Supabase Storage. Null si no se ha subido.",
    )


class OrganizacionSchema(BaseModel):
    """
    Datos de branding de la organización.
    El frontend los usa para aplicar colores y logo al iniciar sesión.
    Los campos de color tienen defaults para no romper el frontend si
    la org no ha configurado su branding.
    """

    org_id: str = Field(..., description="UUID de la organización.")
    org_nombre: str = Field(..., description="Nombre de la institución.")
    org_color_primario: str = Field(
        default="#1565C0",
        description="Color primario en hex. Usado en botones y encabezados.",
    )
    org_color_secundario: str = Field(
        default="#2E7D32",
        description="Color secundario en hex. Usado en acentos.",
    )
    org_logo_url: Optional[str] = Field(
        None,
        description="URL del logo. Null si la org no ha configurado uno.",
    )


# =============================================================================
# AUTH — /auth/login  y  /auth/me
# =============================================================================

class LoginRequest(BaseModel):
    """Credenciales enviadas por el cliente al iniciar sesión."""

    correo: EmailStr = Field(
        ...,
        description="Correo institucional del usuario.",
        examples=["alumno_f2_01@primaria-bj.edu.mx"],
    )
    password: str = Field(
        ...,
        min_length=6,
        description="Contraseña en texto plano. Se compara contra el hash bcrypt en BD.",
        examples=["Test1234"],
    )


class LoginResponse(BaseModel):
    """
    Respuesta completa del login — Fase A.

    Contiene el JWT más el perfil del usuario y el branding de la
    organización para que el frontend pueda:
      1. Almacenar el token y usarlo en peticiones futuras.
      2. Aplicar colores y logo de la institución inmediatamente.
      3. Redirigir a la pantalla correcta según `usuario.usuario_tipo`.
    """

    status: str = Field(default="success", description="Siempre 'success' en respuesta 200.")
    access_token: str = Field(..., description="JWT firmado. Incluir en Authorization: Bearer.")
    token_type: str = Field(default="bearer", description="Tipo de token. Siempre 'bearer'.")
    expires_in: int = Field(..., description="Segundos hasta expiración del token.")
    usuario: UsuarioSchema = Field(..., description="Perfil del usuario autenticado.")
    organizacion: OrganizacionSchema = Field(..., description="Branding de la organización.")


class MeResponse(BaseModel):
    """
    Respuesta de GET /auth/me.
    Mismo contrato que LoginResponse pero sin el token —
    el cliente ya lo tiene; solo necesita rehidratar el estado de sesión
    tras una recarga de la app.
    """

    usuario: UsuarioSchema = Field(..., description="Perfil actualizado del usuario.")
    organizacion: OrganizacionSchema = Field(..., description="Branding de la organización.")


# =============================================================================
# DASHBOARD DEL ALUMNO — /alumno/dashboard
# =============================================================================

class MetricasSchema(BaseModel):
    """
    Métricas de gamificación y progreso general del alumno.
    Renombrado y expandido desde RachaSchema (v1).

    `tasa_aprobacion` se calcula en el servicio como:
        (examenes_aprobados / examenes_total * 100) si examenes_total > 0, else 0.0

    `capacitaciones_completadas` y `capacitaciones_total` se obtienen
    haciendo COUNT sobre capacitacion_usuario — no requieren columna
    extra en la BD.
    """

    promedio_actual: float = Field(..., description="Promedio ponderado de calificaciones (0–100).")
    racha_dias: int = Field(..., description="Días consecutivos con actividad registrada.")
    ultima_actividad: Optional[str] = Field(
        None,
        description="Fecha de la última actividad (YYYY-MM-DD). Null si no hay actividad.",
    )
    capacitaciones_completadas: int = Field(
        ..., description="Cantidad de capacitaciones con estado 'completado'."
    )
    capacitaciones_total: int = Field(
        ..., description="Total de capacitaciones en las que el alumno está inscrito."
    )
    examenes_aprobados: int = Field(..., description="Total de exámenes aprobados.")
    examenes_total: int = Field(..., description="Total de exámenes presentados.")
    tasa_aprobacion: float = Field(
        ..., description="Porcentaje de aprobación: aprobados / total * 100."
    )


class IntentoEnProgresoSchema(BaseModel):
    """
    Examen que el alumno dejó sin terminar (inex_estado = 'EN_PROGRESO').
    Si este campo es distinto de null, el frontend muestra el modal
    'Retomar examen' al abrir la app.
    """

    intento_id: str = Field(..., description="UUID del intento en progreso.")
    exam_id: str = Field(..., description="UUID del examen.")
    titulo: str = Field(..., description="Nombre del examen para mostrar en el modal.")
    tiempo_restante_seg: Optional[int] = Field(
        None,
        description="Segundos restantes según el último autosave. Null si no hay registro.",
    )
    fecha_inicio: str = Field(..., description="ISO timestamp de cuando se inició el intento.")


class CapacitacionDashboardSchema(BaseModel):
    """
    Resumen de una capacitación activa del alumno para el dashboard.
    Solo aparecen capacitaciones con estado 'inscrito' o 'en_progreso'.
    Renombrado desde CursoPendienteSchema (v1).
    `catedraticos` se puebla en Fase B/C; por ahora siempre es [].
    """

    capaci_id: str = Field(..., description="UUID de la capacitación.")
    capaci_nombre: str = Field(..., description="Nombre de la capacitación.")
    capaci_descripcion: Optional[str] = Field(None, description="Descripción breve.")
    capaci_disponibilidad: str = Field(
        default="activa",
        description="'activa' | 'inactiva' | 'archivada'.",
    )
    capaci_fecha_inicio: Optional[str] = Field(None, description="ISO datetime de inicio.")
    capaci_fecha_fin: Optional[str] = Field(None, description="ISO datetime de cierre.")
    progreso: float = Field(..., ge=0, le=100, description="Porcentaje de avance (0–100).")
    estado_inscripcion: str = Field(
        ..., description="'inscrito' | 'en_progreso' | 'completado' | 'abandonado'."
    )
    catedraticos: list[dict] = Field(
        default_factory=list,
        description="Catedráticos asignados. Siempre [] en Fase A.",
    )


class ExamenPendienteSchema(BaseModel):
    """
    Resumen de un examen que el alumno puede presentar o reintentar.
    Aparece en la sección 'Exámenes pendientes' del dashboard.
    `total_preguntas` se extrae del campo exam_json de la BD.
    """

    exam_id: str = Field(..., description="UUID del examen.")
    capaci_id: str = Field(..., description="UUID de la capacitación a la que pertenece.")
    capaci_nombre: str = Field(..., description="Nombre de la capacitación.")
    exam_nombre: str = Field(..., description="Nombre descriptivo del examen.")
    exam_dificultad: str = Field(..., description="'BASICO' | 'INTERMEDIO' | 'AVANZADO'.")
    exam_tiempo_limite: int = Field(
        default=60, description="Tiempo límite en minutos."
    )
    exam_intentos_max: int = Field(..., description="Número máximo de intentos permitidos.")
    intentos_realizados: int = Field(..., description="Intentos ya consumidos por el alumno.")
    exam_fecha_vencimiento: Optional[str] = Field(
        None, description="ISO datetime de vencimiento. Null si sin límite de fecha."
    )
    estado_intento: str = Field(
        default="PENDIENTE",
        description="'PENDIENTE' | 'EN_PROGRESO' | 'COMPLETADO' | 'EXPIRADO'.",
    )
    total_preguntas: int = Field(
        default=0, description="Número de preguntas. Se cuenta desde exam_json."
    )


class ContenidoRecienteSchema(BaseModel):
    """
    Vista previa de un contenido para el dashboard.
    En Fase A la lista siempre llega vacía [].
    Se puebla en Fase C al implementar la tabla contenido_visto.
    """

    conten_id: str = Field(..., description="UUID del contenido.")
    capaci_id: str = Field(..., description="UUID de la capacitación.")
    capaci_nombre: str = Field(..., description="Nombre de la capacitación.")
    conten_nombre: str = Field(..., description="Título del contenido.")
    conten_tipo: str = Field(..., description="'pdf' | 'guia' | 'video'.")
    tamanio_kb: Optional[int] = Field(None, description="Tamaño en KB.")
    visto: bool = Field(..., description="Si el alumno ya lo revisó.")


class DashboardAlumnoResponse(BaseModel):
    """
    Respuesta completa del dashboard del alumno — Fase A.

    Una sola llamada alimenta toda la pantalla de inicio del frontend.

    Cambios respecto a v1:
      · `racha` → `metricas` (renombrado y expandido con totales de capacitaciones).
      · `cursos_pendientes` → `capacitaciones` (renombrado, campos ampliados).
      · Se agrega `intento_en_progreso` — null si no hay examen en curso.
      · Se agrega `contenidos_recientes` — siempre [] en Fase A.
    """

    saludo: str = Field(
        ...,
        description="Saludo personalizado. Ej: 'Bienvenido, Luis'.",
        examples=["Bienvenido, Luis"],
    )
    metricas: MetricasSchema = Field(
        ..., description="KPIs de gamificación y progreso general."
    )
    intento_en_progreso: Optional[IntentoEnProgresoSchema] = Field(
        None,
        description="Examen sin terminar. El frontend muestra modal 'Retomar' si no es null.",
    )
    capacitaciones: list[CapacitacionDashboardSchema] = Field(
        ...,
        description="Capacitaciones activas del alumno (inscrito o en_progreso).",
    )
    examenes_pendientes: list[ExamenPendienteSchema] = Field(
        ...,
        description="Exámenes que el alumno puede presentar o reintentar.",
    )
    contenidos_recientes: list[ContenidoRecienteSchema] = Field(
        default_factory=list,
        description="Últimos contenidos vistos. Siempre [] en Fase A.",
    )


# =============================================================================
# ERRORES GENÉRICOS
# =============================================================================

class ErrorResponse(BaseModel):
    """
    Estructura estándar para todas las respuestas de error.
    `codigo` es un string legible por el frontend para manejo programático.
    Códigos: INVALID_CREDENTIALS, TOKEN_EXPIRED, FORBIDDEN,
    NOT_ENROLLED, EXAM_EXPIRED, MAX_ATTEMPTS_REACHED, VALIDATION_ERROR.
    """

    status: str = Field(default="error", description="Siempre 'error' en respuestas 4xx/5xx.")
    detalle: str = Field(..., description="Descripción del error para el desarrollador.")
    codigo: Optional[str] = Field(
        None, description="Código interno para manejo programático en el frontend."
    )


# =============================================================================
# FASE B — EXÁMENES Y MOTOR DE INTENTO
# =============================================================================

# ---------------------------------------------------------------------------
# Sub-schemas del exam_json
# ---------------------------------------------------------------------------

class OpcionSchema(BaseModel):
    """
    Una opción de respuesta dentro de una pregunta.
    `es_correcta` y `explicacion` NO se envían al alumno durante el examen
    — solo se incluyen en la respuesta de resultados (post fecha_fin).
    """
    letra: str = Field(..., description="Identificador de la opción: A, B, C, D.")
    texto: str = Field(..., description="Texto de la opción.")


class OpcionResultadoSchema(BaseModel):
    """Opción enriquecida con la respuesta correcta y explicación. Solo post fecha_fin."""
    letra: str
    texto: str
    es_correcta: bool
    explicacion: Optional[str] = None


class PreguntaExamenSchema(BaseModel):
    """
    Pregunta del examen tal como se entrega al alumno al iniciar.
    No incluye cuál opción es correcta — eso se guarda en exam_json
    y solo se revela cuando el examen cierra (inex_fecha_fin).
    """
    id_pregunta: str = Field(..., description="UUID de la pregunta. Es la key del autosave.")
    enunciado: str = Field(..., description="Texto de la pregunta.")
    tipo_pregunta: str = Field(..., description="'simple' | 'multiple'.")
    opciones: list[OpcionSchema] = Field(..., description="Opciones sin revelar la correcta.")
    tiempo_estimado: Optional[int] = Field(
        None, description="Segundos estimados para resolver esta pregunta."
    )
    svg: Optional[str] = Field(None, description="Diagrama SVG adjunto, si existe.")


class DistribucionSchema(BaseModel):
    """Distribución de tipos y dificultades del examen. Se muestra en el detalle pre-inicio."""
    total_preguntas: int
    simple: int = 0
    multiple: int = 0
    abierta: int = 0
    basico: int = 0
    intermedio: int = 0
    avanzado: int = 0


# ---------------------------------------------------------------------------
# GET /alumno/examenes — Listado
# ---------------------------------------------------------------------------

class ExamenListadoItemSchema(BaseModel):
    """
    Resumen de un examen para el listado agrupado por capacitación.
    `mejor_calificacion` es null si el alumno no ha completado ningún intento.
    `exam_tema` se extrae de metadata.fuente_conocimiento.subtemas[0].nombre
    dentro del exam_json — no es columna de la tabla examenes.
    """
    exam_id: str
    capaci_id: str
    capaci_nombre: str
    exam_nombre: str
    exam_dificultad: str = Field(..., description="'BASICO' | 'INTERMEDIO' | 'AVANZADO'.")
    exam_tema: Optional[str] = Field(
        None, description="Subtema principal extraído del exam_json."
    )
    exam_tiempo_limite: int = Field(..., description="Minutos disponibles para resolver.")
    exam_intentos_max: int
    intentos_realizados: int
    mejor_calificacion: Optional[float] = Field(
        None, description="Mayor calificación obtenida en intentos COMPLETADOS. Null si ninguno."
    )
    exam_fecha_vencimiento: Optional[str] = None
    total_preguntas: int = Field(..., description="Desde metadata.distribucion.total_preguntas.")
    estado_intento: str = Field(
        ..., description="'PENDIENTE' | 'EN_PROGRESO' | 'COMPLETADO' | 'EXPIRADO'."
    )


class ExamenesListadoResponse(BaseModel):
    """
    Respuesta del listado de exámenes.
    La API devuelve lista plana — el frontend agrupa visualmente
    por capacitación y por estado (pendientes / terminados).
    """
    items: list[ExamenListadoItemSchema]
    total: int = Field(..., description="Total de ítems en la lista (para paginación futura).")


# ---------------------------------------------------------------------------
# GET /alumno/examenes/{exam_id} — Detalle pre-inicio
# ---------------------------------------------------------------------------

class ExamenDetalleResponse(BaseModel):
    """
    Detalle completo del examen para la pantalla de preparación pre-inicio.
    Incluye toda la meta-información pero NO revela las preguntas todavía
    (esas se entregan al hacer POST /iniciar).
    """
    exam_id: str
    capaci_id: str
    capaci_nombre: str
    exam_nombre: str
    exam_dificultad: str
    exam_tema: Optional[str] = None
    exam_tiempo_limite: int = Field(..., description="Minutos.")
    exam_intentos_max: int
    exam_calificacion_minima: float = Field(
        ..., description="Calificación mínima para aprobar. Default 70."
    )
    intentos_realizados: int
    intentos_disponibles: int = Field(
        ..., description="exam_intentos_max - intentos_realizados."
    )
    mejor_calificacion: Optional[float] = None
    exam_fecha_vencimiento: Optional[str] = None
    total_preguntas: int
    distribucion: DistribucionSchema
    estado_intento: str


# ---------------------------------------------------------------------------
# POST /alumno/examenes/{exam_id}/iniciar — Crear o recuperar intento
# ---------------------------------------------------------------------------

class IniciarIntentoResponse(BaseModel):
    """
    Respuesta al iniciar o retomar un examen.
    Incluye las preguntas completas (sin respuestas correctas) y
    el progreso guardado en el último autosave si el alumno retoma.

    `es_retoma` indica al frontend si debe restaurar `progreso_guardado`
    o iniciar con todas las preguntas en blanco.
    """
    intento_id: str
    exam_id: str
    numero_intento: int
    es_retoma: bool = Field(
        ..., description="True si el alumno retoma un intento EN_PROGRESO existente."
    )
    fecha_inicio: str
    tiempo_limite_seg: int = Field(
        ..., description="Tiempo total del examen en segundos (exam_tiempo_limite * 60)."
    )
    tiempo_restante_seg: int = Field(
        ..., description="Segundos restantes. Si es retoma, calculado desde el último autosave."
    )
    preguntas: list[PreguntaExamenSchema] = Field(
        ..., description="Preguntas sin revelar respuestas correctas."
    )
    progreso_guardado: Optional[dict] = Field(
        None,
        description=(
            "Contenido de inex_progreso_json del último autosave. "
            "Null si es intento nuevo. "
            "Estructura: {respuestas: {uuid: 'A'}, marcadas: ['uuid']}."
        ),
    )


# ---------------------------------------------------------------------------
# PATCH /alumno/intentos/{intento_id}/autosave — Heartbeat
# ---------------------------------------------------------------------------

class AutosaveRequest(BaseModel):
    """
    Body del heartbeat de autosave enviado por el frontend cada 30 segundos.
    Las keys de `respuestas` son los UUID de las preguntas (id_pregunta).
    `marcadas` es lista de UUIDs de preguntas que el alumno marcó para revisar.
    El tiempo restante lo calcula la API — no viene en el body.
    """
    respuestas: dict[str, str] = Field(
        ...,
        description="Mapa id_pregunta → letra de respuesta. Ej: {'a1b2...': 'B'}.",
        examples=[{"a1b2c3d4-e5f6-7890-abcd-ef1234567801": "A"}],
    )
    marcadas: list[str] = Field(
        default_factory=list,
        description="UUIDs de preguntas marcadas para revisar después.",
    )


class AutosaveResponse(BaseModel):
    """Confirmación del autosave. El frontend usa `synced_at` para mostrar el timestamp."""
    intento_id: str
    synced_at: str = Field(..., description="ISO timestamp de cuando se guardó.")
    tiempo_restante_seg: int = Field(
        ..., description="Segundos restantes calculados por la API."
    )


# ---------------------------------------------------------------------------
# POST /alumno/intentos/{intento_id}/entregar — Entrega final
# ---------------------------------------------------------------------------

class EntregarRequest(BaseModel):
    """
    Body de la entrega final del examen.
    Mismo contrato que AutosaveRequest — es el último guardado antes de cerrar.
    La API marca el intento como COMPLETADO pero NO califica todavía.
    La calificación y feedback solo se disponibilizan cuando inex_fecha_fin
    supere la fecha actual (el examen cerró para todos los alumnos).
    """
    respuestas: dict[str, str] = Field(
        ..., description="Estado final del examen. Keys = UUID de preguntas."
    )
    marcadas: list[str] = Field(
        default_factory=list,
        description="Preguntas marcadas al momento de entregar (para registro).",
    )


class EntregarResponse(BaseModel):
    """
    Confirmación de entrega. El frontend muestra pantalla de 'Examen entregado'.
    `resultados_disponibles_en` es cuándo el alumno podrá ver su calificación.
    """
    intento_id: str
    estado: str = Field(default="COMPLETADO", description="Siempre COMPLETADO en respuesta 200.")
    entregado_en: str = Field(..., description="ISO timestamp de la entrega.")
    resultados_disponibles_en: Optional[str] = Field(
        None,
        description=(
            "ISO timestamp de inex_fecha_fin del examen. "
            "Null si el examen no tiene fecha de cierre definida."
        ),
    )
    mensaje: str = Field(
        default="Tu examen fue entregado correctamente. Los resultados estarán disponibles cuando el período de evaluación cierre.",
        description="Mensaje amigable para mostrar al alumno.",
    )


# ---------------------------------------------------------------------------
# GET /alumno/intentos/en_progreso — Modal de retomar
# ---------------------------------------------------------------------------

class IntentoEnProgresoDetalleResponse(BaseModel):
    """
    Detalle completo del intento EN_PROGRESO para el modal 'Retomar examen'.
    Incluye preguntas y el progreso guardado para que el frontend restaure
    el estado exacto donde el alumno lo dejó.
    """
    intento_id: str
    exam_id: str
    exam_nombre: str
    capaci_id: str
    capaci_nombre: str
    numero_intento: int
    fecha_inicio: str
    tiempo_limite_seg: int
    tiempo_restante_seg: int
    preguntas: list[PreguntaExamenSchema]
    progreso_guardado: Optional[dict] = Field(
        None, description="Último autosave: {respuestas: {...}, marcadas: [...]}."
    )


# =============================================================================
# FASE C — CAPACITACIONES Y CONTENIDOS
# =============================================================================

# ---------------------------------------------------------------------------
# Sub-schemas compartidos
# ---------------------------------------------------------------------------

class CatedraticoDashboardSchema(BaseModel):
    """
    Resumen de un catedrático asignado a una capacitación.
    En Fases A y B se devolvía como [] — aquí se puebla desde
    catedratico_capacitacion JOIN usuarios JOIN catedratico_detalles.
    """
    usuario_id: str
    usuario_nombre: str
    usuario_apellidos: Optional[str] = None
    cade_titulo: Optional[str] = Field(
        None, description="Ej: 'Dr.', 'Mtro.', 'Ing.'"
    )
    cade_especialidad: Optional[str] = None
    cade_avatar_url: Optional[str] = None
    caca_rol: str = Field(
        ..., description="Rol del catedrático en esta capacitación."
    )


# ---------------------------------------------------------------------------
# GET /alumno/capacitaciones — Listado
# ---------------------------------------------------------------------------

class CapacitacionListadoItemSchema(BaseModel):
    """
    Ítem del listado de capacitaciones del alumno.

    `contenidos_vistos` siempre es 0 — la BD no tiene tabla de tracking
    de vistos. Se incluye en el schema para compatibilidad con el contrato
    del frontend; se poblará cuando se agregue la tabla contenido_visto.

    `total_examenes` y `examenes_aprobados` se calculan en Python contando
    sobre capacitacion_examenes e intentos_examen respectivamente.
    """
    capaci_id: str
    capaci_nombre: str
    capaci_descripcion: Optional[str] = None
    capaci_disponibilidad: str
    capaci_fecha_inicio: Optional[str] = None
    capaci_fecha_fin: Optional[str] = None
    progreso: float = Field(..., ge=0, le=100)
    estado_inscripcion: str
    inscrito_en: Optional[str] = None
    completado_en: Optional[str] = None
    total_examenes: int = 0
    examenes_aprobados: int = 0
    total_contenidos: int = 0
    contenidos_vistos: int = Field(
        default=0,
        description="Siempre 0 — requiere tabla contenido_visto (pendiente).",
    )
    catedraticos: list[CatedraticoDashboardSchema] = Field(default_factory=list)


class CapacitacionesListadoResponse(BaseModel):
    """Respuesta del listado de capacitaciones del alumno."""
    total: int
    items: list[CapacitacionListadoItemSchema]


# ---------------------------------------------------------------------------
# GET /alumno/capacitaciones/{capaci_id} — Detalle
# ---------------------------------------------------------------------------

class ContenidoDetalleCapacitacionSchema(BaseModel):
    """
    Contenido dentro del detalle de una capacitación.
    `caco_unidad` y `caco_orden` vienen de capacitacion_contenidos
    y permiten al frontend agrupar por unidad y ordenar.
    `visto` siempre es False — sin tabla de tracking.
    """
    conten_id: str
    conten_nombre: str
    conten_descripcion: Optional[str] = None
    conten_tipo: str = Field(..., description="'pdf' | 'guia' | 'video'.")
    caco_unidad: int = Field(..., description="Número de unidad temática.")
    caco_orden: int = Field(..., description="Posición dentro de la unidad.")
    visto: bool = Field(
        default=False,
        description="Siempre False — requiere tabla contenido_visto (pendiente).",
    )


class ExamenDetalleCapacitacionSchema(BaseModel):
    """
    Examen dentro del detalle de una capacitación.
    Incluye `caex_unidad` y `caex_orden` para que el frontend los agrupe
    junto a los contenidos de la misma unidad.
    """
    exam_id: str
    exam_nombre: str
    exam_dificultad: str
    exam_tiempo_limite: int
    exam_intentos_max: int
    exam_calificacion_minima: float
    caex_unidad: int
    caex_orden: int
    estado_intento: str = Field(
        ..., description="'PENDIENTE' | 'EN_PROGRESO' | 'COMPLETADO' | 'EXPIRADO'."
    )
    mejor_calificacion: Optional[float] = None
    intentos_realizados: int = 0


class CapacitacionDetalleResponse(BaseModel):
    """
    Detalle completo de una capacitación para la vista individual.
    Contiene toda la meta-información más los arrays de contenidos
    y exámenes con sus campos de unidad y orden para que el frontend
    pueda agruparlos por unidad temática.
    """
    capaci_id: str
    capaci_nombre: str
    capaci_descripcion: Optional[str] = None
    capaci_disponibilidad: str
    capaci_fecha_inicio: Optional[str] = None
    capaci_fecha_fin: Optional[str] = None
    progreso: float
    estado_inscripcion: str
    inscrito_en: Optional[str] = None
    completado_en: Optional[str] = None
    total_examenes: int
    examenes_aprobados: int
    total_contenidos: int
    contenidos_vistos: int = Field(
        default=0,
        description="Siempre 0 — requiere tabla contenido_visto (pendiente).",
    )
    catedraticos: list[CatedraticoDashboardSchema] = Field(default_factory=list)
    contenidos: list[ContenidoDetalleCapacitacionSchema] = Field(default_factory=list)
    examenes: list[ExamenDetalleCapacitacionSchema] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# GET /alumno/contenidos — Listado de contenidos
# ---------------------------------------------------------------------------

class ContenidoListadoItemSchema(BaseModel):
    """
    Ítem del listado de contenidos filtrado por capacitación.
    `conten_tamanio_kb` no existe en la BD — se devuelve null siempre.
    `visto` no se puede calcular sin tabla de tracking — siempre False.
    """
    conten_id: str
    capaci_id: str
    conten_nombre: str
    conten_descripcion: Optional[str] = None
    conten_tipo: str
    caco_unidad: int
    caco_orden: int
    conten_tamanio_kb: Optional[int] = Field(
        default=None,
        description="No disponible — columna no existe en la BD actual.",
    )
    visto: bool = Field(
        default=False,
        description="Siempre False — requiere tabla contenido_visto (pendiente).",
    )


class ContenidosListadoResponse(BaseModel):
    """Respuesta del listado de contenidos de una capacitación."""
    capaci_id: str
    total: int
    items: list[ContenidoListadoItemSchema]


# ---------------------------------------------------------------------------
# GET /alumno/contenidos/{conten_id}/url — URL de acceso
# ---------------------------------------------------------------------------

class ContenidoUrlResponse(BaseModel):
    """
    URL de acceso al archivo del contenido.

    Lógica de construcción (sin llamadas extra a Storage):
      1. Si conten_url_publica tiene valor → se devuelve directamente.
      2. Si es null → se construye como:
         {SUPABASE_URL}/storage/v1/object/public/contenidos/{conten_s3_key}
         (el bucket 'contenidos' es público en Supabase Storage).

    `expira_en` es null porque el bucket es público y las URLs no expiran.
    """
    conten_id: str
    conten_nombre: str
    conten_tipo: str
    url: str = Field(..., description="URL directa de acceso al archivo.")
    expira_en: Optional[str] = Field(
        default=None,
        description="Null — bucket público, URLs sin expiración.",
    )


# =============================================================================
# FASE D — HISTORIAL, MÉTRICAS Y CERTIFICADOS
# =============================================================================

# ---------------------------------------------------------------------------
# GET /alumno/historial — Listado
# ---------------------------------------------------------------------------

class HistorialItemSchema(BaseModel):
    """
    Ítem del historial de intentos del alumno.
    Incluye intentos COMPLETADO y EXPIRADO.
    `calificacion` puede ser null si exam_fecha_vencimiento aún no pasó
    (los resultados no se revelan antes del cierre del período).
    """
    intento_id: str
    exam_id: str
    exam_nombre: str
    exam_dificultad: str
    capaci_id: Optional[str] = None
    capaci_nombre: Optional[str] = None
    inex_estado: str = Field(..., description="'COMPLETADO' | 'EXPIRADO'.")
    inex_numero_intento: int
    inex_fecha_inicio: str
    inex_fecha_fin: Optional[str] = None
    calificacion: Optional[float] = Field(
        None,
        description="Null si exam_fecha_vencimiento aún no llegó.",
    )
    aciertos: Optional[int] = None
    total_preguntas: Optional[int] = None
    resultados_disponibles: bool = Field(
        ...,
        description="True si exam_fecha_vencimiento < ahora. Determina si se muestran resultados.",
    )


class HistorialListadoResponse(BaseModel):
    """Respuesta del listado de historial de intentos."""
    total: int
    items: list[HistorialItemSchema]


# ---------------------------------------------------------------------------
# GET /alumno/historial/{intento_id} — Detalle
# ---------------------------------------------------------------------------

class RespuestaFeedbackSchema(BaseModel):
    """
    Feedback por pregunta una vez que el período de evaluación cerró.
    Incluye la respuesta del alumno, la correcta y la explicación del exam_json.
    """
    id_pregunta: str
    enunciado: str
    tipo_pregunta: str
    respuesta_alumno: Optional[str] = Field(
        None, description="Letra que eligió el alumno. Null si no respondió."
    )
    respuesta_correcta: str = Field(..., description="Letra de la opción correcta.")
    es_correcto: bool
    explicacion: Optional[str] = Field(
        None, description="Explicación de la respuesta correcta del exam_json."
    )
    opciones: list[OpcionResultadoSchema] = Field(
        default_factory=list,
        description="Todas las opciones con es_correcta y explicacion reveladas.",
    )


class HistorialDetalleResponse(BaseModel):
    """
    Detalle completo de un intento pasado.

    Si `resultados_disponibles` es False (exam_fecha_vencimiento aún no llegó):
      - `calificacion`, `aciertos`, `total_preguntas` son null.
      - `feedback` es lista vacía.
      - El frontend muestra: 'Resultados disponibles el {resultados_disponibles_en}'.

    Si `resultados_disponibles` es True:
      - Se calculan calificación y aciertos (desde BD si existen, o desde
        inex_progreso_json vs exam_json en tiempo real).
      - `feedback` contiene una entrada por pregunta con respuesta correcta
        y explicación extraída del exam_json.
    """
    intento_id: str
    exam_id: str
    exam_nombre: str
    exam_dificultad: str
    exam_calificacion_minima: float
    capaci_id: Optional[str] = None
    capaci_nombre: Optional[str] = None
    inex_estado: str
    inex_numero_intento: int
    inex_fecha_inicio: str
    inex_fecha_fin: Optional[str] = None
    resultados_disponibles: bool
    resultados_disponibles_en: Optional[str] = Field(
        None,
        description="ISO timestamp de exam_fecha_vencimiento. Null si el examen no tiene fecha de cierre.",
    )
    calificacion: Optional[float] = None
    aciertos: Optional[int] = None
    total_preguntas: Optional[int] = None
    aprobado: Optional[bool] = Field(
        None,
        description="True si calificacion >= exam_calificacion_minima. Null si resultados no disponibles.",
    )
    feedback: list[RespuestaFeedbackSchema] = Field(
        default_factory=list,
        description="Feedback por pregunta. Lista vacía si resultados_disponibles es False.",
    )


# ---------------------------------------------------------------------------
# GET /alumno/metricas — Métricas con evolución
# ---------------------------------------------------------------------------

class EvolucionPuntoSchema(BaseModel):
    """
    Punto de la curva de evolución del promedio mensual.
    Se calcula en Python agrupando intentos COMPLETADO por mes
    (últimos 6 meses). Meses sin intentos se omiten.
    """
    periodo: str = Field(..., description="Formato YYYY-MM. Ej: '2026-03'.")
    promedio: float = Field(..., description="Promedio de calificaciones de ese mes.")
    examenes_presentados: int = Field(..., description="Intentos COMPLETADO en ese mes.")


class MetricasDetalleResponse(BaseModel):
    """
    Métricas completas del alumno para la pantalla de estadísticas.
    Extiende el objeto `metricas` del dashboard con la evolución mensual.
    `evolucion_promedio` contiene hasta 6 puntos (últimos 6 meses con actividad).
    Lista vacía si el alumno no tiene intentos COMPLETADO con calificación.
    """
    promedio_actual: float
    racha_dias: int
    ultima_actividad: Optional[str] = None
    capacitaciones_completadas: int
    capacitaciones_total: int
    examenes_aprobados: int
    examenes_total: int
    tasa_aprobacion: float
    evolucion_promedio: list[EvolucionPuntoSchema] = Field(
        default_factory=list,
        description="Últimos 6 meses con al menos un intento COMPLETADO calificado.",
    )


# ---------------------------------------------------------------------------
# GET /alumno/certificados — Listado
# ---------------------------------------------------------------------------

class CertificadoItemSchema(BaseModel):
    """
    Ítem del listado de certificados del alumno.
    La capacitación se obtiene navegando:
    exam_id → capacitacion_examenes → capaci_id → capacitaciones.
    `cert_pdf_url` y `cert_qr_url` pueden ser null si aún no se generaron.
    Los catedráticos firmantes NO se incluyen en el listado — solo en el
    detalle individual (fuera del scope de Fase D).
    """
    cert_id: str
    cert_folio: str
    exam_id: str
    exam_nombre: str
    capaci_id: Optional[str] = None
    capaci_nombre: Optional[str] = None
    cert_emitido_en: str
    cert_pdf_url: Optional[str] = None
    cert_qr_url: Optional[str] = None


class CertificadosListadoResponse(BaseModel):
    """Respuesta del listado de certificados del alumno."""
    total: int
    items: list[CertificadoItemSchema]

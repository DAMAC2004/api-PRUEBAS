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

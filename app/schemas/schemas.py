# =============================================================================
# app/schemas/schemas.py
# Modelos Pydantic v2 para validación de entrada y serialización de salida.
#
# Convención de nombres:
#   *Request  → Body que llega del cliente (POST/PUT).
#   *Response → Lo que la API devuelve al cliente.
#
# BaseModel de Pydantic hace:
#   - Validación automática de tipos y restricciones.
#   - Serialización a JSON limpia (sin campos internos / contraseñas).
#   - Documentación automática en /docs (Swagger UI).
# =============================================================================
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field


# =============================================================================
# AUTH — /auth/login
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


class TokenResponse(BaseModel):
    """
    Respuesta exitosa de login.
    El campo 'access_token' debe guardarse en el cliente y enviarse
    como `Authorization: Bearer <token>` en cada petición protegida.
    """

    access_token: str = Field(..., description="JWT firmado. Expira según JWT_EXPIRE_MINUTES.")
    token_type: str = Field(default="bearer", description="Tipo de token. Siempre 'bearer'.")
    expires_in: int = Field(..., description="Segundos hasta que expire el token.")
    usuario_tipo: str = Field(..., description="'alumno' o 'catedratico'. El frontend usa esto para redirigir a la pantalla correcta.")
    usuario_rol: str = Field(..., description="'estudiante' o 'administrador'.")


# =============================================================================
# DASHBOARD DEL ALUMNO — /alumno/dashboard
# =============================================================================

class ExamenPendienteSchema(BaseModel):
    """Resumen de un examen que el alumno aún no ha completado."""

    exam_id: str = Field(..., description="UUID del examen.")
    exam_nombre: str = Field(..., description="Nombre descriptivo del examen.")
    exam_dificultad: str = Field(..., description="BASICO | INTERMEDIO | AVANZADO")
    exam_intentos_max: int = Field(..., description="Número máximo de intentos permitidos.")
    intentos_usados: int = Field(..., description="Cuántos intentos ya consumió el alumno.")
    intentos_restantes: int = Field(..., description="exam_intentos_max - intentos_usados.")
    capacitacion_nombre: str = Field(..., description="Nombre del curso al que pertenece el examen.")
    capaci_id: str = Field(..., description="UUID de la capacitación padre.")


class CursoPendienteSchema(BaseModel):
    """Resumen de una capacitación en la que el alumno está inscrito y no ha completado."""

    capaci_id: str = Field(..., description="UUID de la capacitación.")
    capaci_nombre: str = Field(..., description="Nombre de la capacitación.")
    capaci_descripcion: Optional[str] = Field(None, description="Descripción breve.")
    progreso: float = Field(
        ...,
        ge=0,
        le=100,
        description="Porcentaje de avance del alumno (0.00 – 100.00).",
    )
    estado: str = Field(..., description="inscrito | en_progreso | completado | abandonado")
    fecha_fin: Optional[datetime] = Field(None, description="Fecha límite de la capacitación.")


class RachaSchema(BaseModel):
    """Datos de gamificación: racha de días consecutivos de actividad."""

    racha_dias: int = Field(..., description="Días consecutivos con actividad registrada.")
    ultima_actividad: Optional[str] = Field(
        None,
        description="Fecha de la última actividad (YYYY-MM-DD). Null si nunca ha tenido actividad.",
    )
    promedio_general: float = Field(..., description="Promedio de calificaciones (0.00 – 100.00).")
    examenes_aprobados: int = Field(..., description="Total de exámenes aprobados.")
    examenes_presentados: int = Field(..., description="Total de exámenes presentados.")


class DashboardAlumnoResponse(BaseModel):
    """
    Respuesta completa del dashboard del alumno.
    Agrupa toda la información necesaria para la pantalla principal en una sola llamada,
    evitando múltiples round-trips desde el frontend.
    """

    saludo: str = Field(
        ...,
        description="Saludo personalizado listo para mostrar. Ej: '¡Hola, Luis! 👋'",
        examples=["¡Hola, Luis! 👋"],
    )
    nombre_completo: str = Field(..., description="Nombre + apellidos del alumno.")
    examenes_pendientes: list[ExamenPendienteSchema] = Field(
        ...,
        description="Lista de exámenes que el alumno aún no ha completado en sus cursos activos.",
    )
    cursos_pendientes: list[CursoPendienteSchema] = Field(
        ...,
        description="Capacitaciones inscritas que no han sido completadas.",
    )
    racha: RachaSchema = Field(..., description="Métricas de gamificación del alumno.")


# =============================================================================
# ERRORES GENÉRICOS
# =============================================================================

class ErrorResponse(BaseModel):
    """Estructura estándar para respuestas de error."""

    detalle: str = Field(..., description="Descripción del error para el desarrollador.")
    codigo: Optional[str] = Field(None, description="Código interno opcional para el cliente.")

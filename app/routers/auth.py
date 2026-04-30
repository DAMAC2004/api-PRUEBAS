# =============================================================================
# app/routers/auth.py
# Endpoints de autenticación — Fase A
#
# Cambios respecto a v1:
#   - POST /auth/login ahora devuelve LoginResponse (incluye usuario + org).
#   - Se agrega GET /auth/me para rehidratación de sesión.
# =============================================================================
from fastapi import APIRouter, Depends

from app.core.deps import get_usuario_actual
from app.schemas.schemas import ErrorResponse, LoginRequest, LoginResponse, MeResponse
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["Autenticación"])


@router.post(
    "/login",
    response_model=LoginResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Credenciales incorrectas."},
    },
    summary="Iniciar sesión",
    description="""
Autentica a un usuario (alumno o catedrático) con su correo y contraseña.

**Respuesta exitosa:** devuelve el JWT más el perfil del usuario y el
branding de la organización.

**Flujo del frontend:**
1. `POST /auth/login` con `{ correo, password }`.
2. Guardar `access_token` en almacenamiento seguro.
3. Aplicar `organizacion.org_color_primario` y `org_logo_url` al tema.
4. Leer `usuario.usuario_tipo` para redirigir:
   - `alumno` → Dashboard del estudiante.
   - `catedratico` → Panel de gestión.
""",
)
async def login(body: LoginRequest) -> LoginResponse:
    return await auth_service.login(body.correo, body.password)


@router.get(
    "/me",
    response_model=MeResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Token ausente, inválido o expirado."},
    },
    summary="Rehidratar sesión",
    description="""
Devuelve el perfil actualizado del usuario autenticado y el branding
de su organización.

**Cuándo usarlo:**
Al recargar la app, el frontend tiene el token almacenado pero necesita
volver a obtener los datos del usuario (nombre, modo oscuro, colores)
sin pedir las credenciales de nuevo.

**Requiere:** `Authorization: Bearer <token>` (obtenido en `/auth/login`).

**Nota:** este endpoint lee datos frescos desde la BD, por lo que refleja
cambios en el perfil hechos después de emitir el token original.
""",
)
async def me(usuario: dict = Depends(get_usuario_actual)) -> MeResponse:
    return await auth_service.get_me(
        usuario_id=usuario["sub"],
        org_id=usuario["org_id"],
    )

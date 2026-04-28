# =============================================================================
# app/routers/auth.py
# Endpoints de autenticación.
# =============================================================================
from fastapi import APIRouter
from app.schemas.schemas import LoginRequest, TokenResponse, ErrorResponse
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["Autenticación"])


@router.post(
    "/login",
    response_model=TokenResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Credenciales incorrectas."},
    },
    summary="Iniciar sesión",
    description="""
Autentica a un usuario (alumno o catedrático) con su correo y contraseña.

**Respuesta exitosa:** devuelve un JWT Bearer que debe incluirse en el
header `Authorization` de todas las peticiones protegidas.

**Flujo del frontend:**
1. POST /auth/login con `{ correo, password }`.
2. Guardar `access_token` en almacenamiento seguro.
3. Leer `usuario_tipo` para redirigir a la pantalla correcta:
   - `alumno` → Dashboard del estudiante.
   - `catedratico` → Panel de gestión.
""",
)
async def login(body: LoginRequest) -> TokenResponse:
    return await auth_service.login(body.correo, body.password)

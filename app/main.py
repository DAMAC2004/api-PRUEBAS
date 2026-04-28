# =============================================================================
# app/main.py
# Punto de entrada de la aplicación FastAPI.
#
# Para correr localmente:
#   uvicorn app.main:app --reload
#
# Documentación interactiva disponible en:
#   http://127.0.0.1:8000/docs   ← Swagger UI
#   http://127.0.0.1:8000/redoc  ← ReDoc
# =============================================================================
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import auth, alumno

# ---------------------------------------------------------------------------
# Metadata de la API (aparece en /docs y /redoc)
# ---------------------------------------------------------------------------
app = FastAPI(
    title="CognitaAI Mobile — API",
    description="""
## API de backend para CognitaAI Mobile

Maneja autenticación JWT y entrega datos al frontend móvil.

### Módulos disponibles
| Módulo | Descripción |
|--------|-------------|
| `/auth` | Login y emisión de tokens JWT |
| `/alumno` | Dashboard y datos del estudiante |

### Cómo autenticarse
1. Llama a `POST /auth/login` con tu correo y contraseña.
2. Copia el valor de `access_token` en la respuesta.
3. Haz clic en **Authorize** (candado arriba a la derecha) e ingresa:
   ```
   Bearer <tu_access_token>
   ```
4. Todos los endpoints protegidos ya funcionarán en esta sesión de Swagger.
""",
    version="1.0.0",
    contact={
        "name": "Radikal Systems",
        "email": "dev@radikalsystems.com",
    },
    license_info={
        "name": "Privado — uso interno",
    },
)

# ---------------------------------------------------------------------------
# CORS
# En desarrollo permitimos cualquier origen para facilitar las pruebas.
# En producción reemplazar "*" por la URL exacta del frontend.
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # TODO: cambiar a URL del frontend en producción
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Registrar routers
# ---------------------------------------------------------------------------
app.include_router(auth.router)
app.include_router(alumno.router)


# ---------------------------------------------------------------------------
# Health check — útil para que Render verifique que el servicio está vivo
# ---------------------------------------------------------------------------
@app.get(
    "/health",
    tags=["Sistema"],
    summary="Estado del servicio",
    description="Endpoint de verificación de vida. Render y otros servicios lo usan para health checks.",
)
async def health():
    return {"status": "ok", "version": "1.0.0"}

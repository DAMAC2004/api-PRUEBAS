# =============================================================================
# app/core/config.py
# Configuración centralizada con pydantic-settings.
# Todas las variables sensibles viven en .env; nunca en el código.
# =============================================================================
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Lee las variables del archivo .env (o del entorno del sistema).
    Pydantic valida tipos automáticamente; si falta una variable
    obligatoria, la app falla al iniciar con un mensaje claro.
    """

    # --- Supabase REST API ---
    SUPABASE_URL: str
    SUPABASE_SERVICE_KEY: str

    # --- JWT (tokens que emite ESTA API al hacer login) ---
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60

    # --- Entorno ---
    APP_ENV: str = "development"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )


# Instancia global — importar desde aquí en todos los módulos
settings = Settings()

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- Credentials: no default. Missing in the environment -> Settings() fails
    # at startup with a validation error. Secrets never get a default. ---
    auth_password: str

    # --- Own services: the address depends on the deployment, so it has no
    # default and must come from the environment (a localhost default would
    # silently mask missing config in production). ---
    mqtt_host: str

    # --- Optional broker credentials (the broker may allow anonymous access). ---
    mqtt_username: str | None = None
    mqtt_password: str | None = None

    # --- Optional session secret. Falls back to auth_password (see
    # effective_secret_key) so no extra variable is required. ---
    secret_key: str | None = None

    # --- Non-secret configuration: sane defaults are fine. ---
    mqtt_port: int = 1883
    z2m_base: str = "zigbee2mqtt"
    app_title: str = "Z2M Floorplan"
    port: int = 8000
    log_level: str = "INFO"
    session_max_age: int = 60 * 60 * 24 * 365  # 1 year
    cookie_secure: bool = True  # set COOKIE_SECURE=false for local HTTP dev

    # --- Runtime state always lives under data/ (mounted as a docker volume). ---
    config_path: str = "data/config.json"
    icon_path: str = "data/icon.png"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def effective_secret_key(self) -> str:
        """Session signing key: explicit SECRET_KEY or fall back to AUTH_PASSWORD."""
        return self.secret_key or self.auth_password

    @field_validator("log_level")
    @classmethod
    def _normalize_log_level(cls, v: str) -> str:
        """Normalize to uppercase and reject unknown levels at startup."""
        level = v.upper()
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if level not in allowed:
            raise ValueError(f"log_level must be one of {sorted(allowed)}")
        return level


settings = Settings()

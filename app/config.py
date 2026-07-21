# app/config.py
# =====================================================================
# BharatOS — Shahdol Anganwadi MVP
# Environment Configuration — Pydantic Settings
# All settings are loaded from .env file automatically.
# =====================================================================

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    Uses Pydantic v2 BaseSettings for automatic .env parsing and validation.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",         # Ignore extra env vars not defined here
    )

    # --- Application ---
    app_name: str = Field(
        default="Shahdol Anganwadi Digital Verification System",
        description="Application display name",
    )
    app_version: str = Field(default="1.0.0")
    debug: bool = Field(default=False, description="Enable debug mode")
    log_level: str = Field(default="INFO", description="Logging level")

    # --- Server ---
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)

    # --- Database ---
    database_url: str = Field(
        default="sqlite+aiosqlite:///./shahdol_anganwadi.db",
        description="SQLAlchemy async database connection URL",
    )

    # --- Meta WhatsApp Cloud API ---
    whatsapp_verify_token: str = Field(
        default="bharat_os_shahdol_verify_token_2026",
        description="Custom webhook verification token set in Meta Developer Console",
    )
    whatsapp_access_token: str = Field(
        default="",
        description="Meta System User permanent access token",
    )
    whatsapp_phone_number_id: str = Field(
        default="",
        description="WhatsApp Business Phone Number ID from Meta Console",
    )
    whatsapp_api_version: str = Field(default="v19.0")
    whatsapp_api_base_url: str = Field(
        default="https://graph.facebook.com",
        description="Meta Graph API base URL",
    )

    # --- Security ---
    secret_key: str = Field(
        default="change_this_in_production_to_a_long_random_string",
        description="Application secret key — CHANGE IN PRODUCTION",
    )

    # --- Pilot Centre Configuration ---
    pilot_awc_id: str = Field(default="AWC-SHA-1042")
    pilot_center_name: str = Field(default="रामपुर")
    pilot_block_name: str = Field(default="सोहागपुर")
    pilot_district: str = Field(default="Shahdol")

    @property
    def whatsapp_api_url(self) -> str:
        """Full base URL for WhatsApp Cloud API messages endpoint."""
        return (
            f"{self.whatsapp_api_base_url}/"
            f"{self.whatsapp_api_version}/"
            f"{self.whatsapp_phone_number_id}/messages"
        )

    @property
    def is_whatsapp_configured(self) -> bool:
        """Returns True if WhatsApp credentials are configured."""
        return bool(self.whatsapp_access_token and self.whatsapp_phone_number_id)


@lru_cache()
def get_settings() -> Settings:
    """
    Returns a cached Settings instance.
    Using @lru_cache ensures environment is read only once,
    improving performance and preventing multiple .env reads.
    """
    return Settings()


# Convenience singleton — import this throughout the app
settings: Settings = get_settings()

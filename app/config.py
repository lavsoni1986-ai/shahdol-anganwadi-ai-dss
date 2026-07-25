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
        populate_by_name=True,
    )

    # --- Application ---
    app_name: str = Field(
        default="Shahdol Anganwadi Digital Verification System",
        description="Application display name",
    )
    app_version: str = Field(default="1.0.0")
    app_public_url: str = Field(
        default="https://api.bharatosdemo24.com",
        description="Public HTTPS base URL of the application for Meta Cloud API callbacks and media links",
    )
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
        default="",
        alias="WHATSAPP_VERIFY_TOKEN",
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
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY", description="Google Gemini API Key")
    groq_api_key: str = Field(default="", alias="GROQ_API_KEY", description="Groq Cloud Vision API Key")
    demo_ceo_phone: str = Field(default="", alias="DEMO_CEO_PHONE", description="VIP CEO Live Demo Phone Number")

    # --- Virtual Broadcast Officer Recipients ---
    officer_recipient_numbers: str = Field(
        default="{}",
        description="JSON dict or comma-separated list of officer phone numbers for virtual broadcast",
    )

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

    @property
    def officer_recipient_numbers_dict(self) -> dict[str, str]:
        """Parses officer_recipient_numbers setting into a dictionary."""
        if not self.officer_recipient_numbers:
            return {}
        try:
            import json
            if self.officer_recipient_numbers.startswith("{"):
                return json.loads(self.officer_recipient_numbers)
            res = {}
            for item in self.officer_recipient_numbers.split(","):
                if "=" in item:
                    k, v = item.split("=", 1)
                    res[k.strip()] = v.strip()
            return res
        except Exception:
            return {}


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

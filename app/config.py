# app/config.py
# =====================================================================
# BharatOS — Shahdol Anganwadi MVP
# Environment Configuration — Pydantic Settings
# All settings are loaded from .env file automatically.
# =====================================================================

from functools import lru_cache
import os

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator


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
    port: int = Field(default=8000, description="Server port (Cloud Run injects PORT)")

    @field_validator("port", mode="before")
    @classmethod
    def _resolve_port_from_env(cls, v):
        """Prefer the Cloud Run $PORT environment variable, preserving local default 8000."""
        env_port = os.getenv("PORT")
        if env_port and str(env_port).strip().isdigit():
            return int(env_port)
        return v if v is not None else 8000

    # --- CORS ---
    cors_allowed_origins: str = Field(
        default="",
        alias="CORS_ALLOWED_ORIGINS",
        description="Comma-separated list of allowed CORS origins for production "
        "(never combined with credentials wildcard). APP_PUBLIC_URL is also allowed.",
    )

    # --- Database ---
    database_url: str = Field(
        default="sqlite+aiosqlite:///./shahdol_anganwadi.db",
        description="SQLAlchemy async database connection URL",
    )
    db_pool_size: int = Field(
        default=5,
        alias="DB_POOL_SIZE",
        description="SQLAlchemy connection pool size (PostgreSQL only)",
    )
    db_max_overflow: int = Field(
        default=10,
        alias="DB_MAX_OVERFLOW",
        description="SQLAlchemy connection pool max overflow (PostgreSQL only)",
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
    whatsapp_app_secret: str = Field(
        default="",
        alias="WHATSAPP_APP_SECRET",
        description="Meta WhatsApp App Secret used to verify x-hub-signature-256 webhook signatures "
        "(NOT the access token, NOT the verify token)",
    )
    whatsapp_signature_check_enabled: bool = Field(
        default=False,
        alias="WHATSAPP_SIGNATURE_CHECK_ENABLED",
        description="Enable x-hub-signature-256 verification on the WhatsApp webhook. "
        "Keep False in local dev; enable in production.",
    )
    officer_recipient_numbers: str = Field(
        default="",
        description="Comma-separated list of officer phone numbers for virtual broadcast",
    )

    # --- Security ---
    secret_key: str = Field(
        default="change_this_in_production_to_a_long_random_string",
        description="Application secret key — CHANGE IN PRODUCTION",
    )

    # --- AI Keys ---
    groq_api_key: str = Field(default="", alias="GROQ_API_KEY", description="Groq Cloud Vision API Key")

    # --- Gemini AI (Google Gen AI SDK) ---
    gemini_api_key: str = Field(
        default="",
        alias="GEMINI_API_KEY",
        description="Google Gemini API Key (AI Studio)",
    )
    gemini_model: str = Field(
        default="gemini-3.6-flash",
        alias="GEMINI_MODEL",
        description="Gemini model name for multimodal vision verification",
    )

    # --- Vision Provider Router ---
    vision_router_enabled: bool = Field(
        default=False,
        alias="VISION_ROUTER_ENABLED",
        description="Enable vision provider routing (VISION_PROVIDER_PRIMARY/FALLBACK)",
    )
    vision_provider_primary: str = Field(
        default="gemini",
        alias="VISION_PROVIDER_PRIMARY",
        description="Primary vision provider: gemini | groq | gemma",
    )
    vision_provider_fallback: str = Field(
        default="groq",
        alias="VISION_PROVIDER_FALLBACK",
        description="Fallback vision provider used when the primary provider fails",
    )

    # --- YOLO Model ---
    yolo_model_path: str = Field(
        default="app/models/yolo11m.pt",
        alias="YOLO_MODEL_PATH",
        description="Path to the YOLO11 model weights. In Docker/Cloud Run set to "
        "/app/app/models/yolo11m.pt. The model is baked into the image; it is not "
        "downloaded at runtime.",
    )

    # --- Firebase Authentication (Officer/Admin dashboard) ---
    firebase_credentials_path: str = Field(
        default="",
        alias="FIREBASE_CREDENTIALS_PATH",
        description="Path to a Firebase Admin service-account JSON (local dev). "
        "If empty, Application Default Credentials (GOOGLE_APPLICATION_CREDENTIALS) are used.",
    )

    # --- Google Cloud Secret Manager ---
    gcp_project_id: str = Field(
        default="",
        alias="GCP_PROJECT_ID",
        description="Google Cloud project ID used by Secret Manager. "
        "If empty, derived from Application Default Credentials / GOOGLE_CLOUD_PROJECT.",
    )

    # --- Google Cloud Storage (Object Storage for Evidence & Reports) ---
    gcs_enabled: bool = Field(
        default=False,
        alias="GCS_ENABLED",
        description="Enable Google Cloud Storage backend for permanent media and PDF reports. "
        "False for local development (filesystem fallback); True for Cloud Run production.",
    )
    gcs_bucket_name: str = Field(
        default="",
        alias="GCS_BUCKET_NAME",
        description="Google Cloud Storage bucket name for storing evidence photos and generated reports.",
    )
    gcs_project_id: str = Field(
        default="",
        alias="GCS_PROJECT_ID",
        description="Google Cloud project ID for Cloud Storage. If empty, falls back to GCP_PROJECT_ID.",
    )

    # --- Virtual Broadcast Officer Recipients ---
    officer_recipient_numbers: str = Field(
        default="{}",
        description="JSON dict or comma-separated list of officer phone numbers for virtual broadcast",
    )

    # --- Pilot Centre Configuration (Shahdol Day 1 Pilot) ---
    pilot_district: str = Field(
        default="Shahdol",
        alias="PILOT_DISTRICT",
        description="Pilot district name for the MVP",
    )
    pilot_awc_id: str = Field(
        default="AWC-SHA-1042",
        alias="PILOT_AWC_ID",
        description="Pilot Anganwadi Centre ID",
    )
    pilot_center_name: str = Field(
        default="रामपुर",
        alias="PILOT_CENTER_NAME",
        description="Pilot centre name (Hindi)",
    )
    pilot_block_name: str = Field(
        default="सोहागपुर",
        alias="PILOT_BLOCK_NAME",
        description="Pilot block name (Hindi)",
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

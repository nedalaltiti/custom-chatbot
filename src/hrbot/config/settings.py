import logging
from dataclasses import dataclass, field
from typing import Optional, List
from hrbot.config.environment import (
    get_env_var, get_env_var_bool, get_env_var_float, get_env_var_int, get_env_var_list
)

logger = logging.getLogger("hrbot.config")

@dataclass(frozen=True)
class GeminiSettings:
    model_name: str = "gemini-2.0-flash-001"
    temperature: float = 0.0
    max_output_tokens: int = 1024
    api_key: Optional[str] = None  # Prefer explicit API key over default credentials

    @classmethod
    def from_environment(cls) -> "GeminiSettings":
        return cls(
            model_name=get_env_var("GEMINI_MODEL_NAME", cls.model_name),
            temperature=get_env_var_float("GEMINI_TEMPERATURE", cls.temperature),
            max_output_tokens=get_env_var_int("GEMINI_MAX_OUTPUT_TOKENS", cls.max_output_tokens),
            api_key=get_env_var("GOOGLE_API_KEY"),
        )

@dataclass(frozen=True)
class EmbeddingSettings:
    model_name: str = "text-embedding-005"
    dimensions: int = 768
    
    @classmethod
    def from_environment(cls) -> "EmbeddingSettings":
        return cls(
            model_name=get_env_var("EMBEDDING_MODEL_NAME", cls.model_name),
            dimensions=get_env_var_int("EMBEDDING_DIMENSIONS", cls.dimensions),
        )

@dataclass(frozen=True)
class TeamsSettings:
    app_id: Optional[str] = None
    app_password: Optional[str] = None
    tenant_id: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None

    @classmethod
    def from_environment(cls) -> "TeamsSettings":
        return cls(
            app_id=get_env_var("MICROSOFT_APP_ID"),
            app_password=get_env_var("MICROSOFT_APP_PASSWORD"),
            tenant_id=get_env_var("TENANT_ID"),
            client_id=get_env_var("CLIENT_ID"),
            client_secret=get_env_var("CLIENT_SECRET"),
        )

@dataclass(frozen=True)
class GoogleCloudSettings:
    project_id: Optional[str] = None
    location: str = "us-central1"

    @classmethod
    def from_environment(cls) -> "GoogleCloudSettings":
        return cls(
            project_id=get_env_var("GOOGLE_CLOUD_PROJECT"),
            location=get_env_var("GOOGLE_CLOUD_LOCATION", cls.location),
        )

@dataclass(frozen=True)
class FeedbackSettings:
    admin_token: str = "your-strong-secret-token"
    feedback_timeout_minutes: int = 10

    @classmethod
    def from_environment(cls) -> "FeedbackSettings":
        return cls(
            admin_token=get_env_var("ADMIN_TOKEN", cls.admin_token),
            feedback_timeout_minutes=get_env_var_int("FEEDBACK_TIMEOUT_MINUTES", cls.feedback_timeout_minutes),
        )
@dataclass(frozen=True)
class HRSupportSettings:
    url: str = "https://hrsupport.usclarity.com/support/home"
    domain: str = "hrsupport.usclarity.com"

    @classmethod
    def from_environment(cls) -> "HRSupportSettings":
        return cls(
            url=get_env_var("HR_SUPPORT_URL", cls.url),
            domain=get_env_var("HR_SUPPORT_DOMAIN", cls.domain),
        )

@dataclass(frozen=True)
class AppSettings:
    app_name: str = "HR Teams Bot"
    host: str = "0.0.0.0"
    port: int = 3978
    debug: bool = False  # Set to False for production
    cors_origins: List[str] = field(default_factory=lambda: ["*"])  # Secure this for production
    gemini: GeminiSettings = field(default_factory=GeminiSettings.from_environment)
    embeddings: EmbeddingSettings = field(default_factory=EmbeddingSettings.from_environment)
    teams: TeamsSettings = field(default_factory=TeamsSettings.from_environment)
    google_cloud: GoogleCloudSettings = field(default_factory=GoogleCloudSettings.from_environment)
    feedback: FeedbackSettings = field(default_factory=FeedbackSettings.from_environment)
    hr_support: HRSupportSettings = field(default_factory=HRSupportSettings.from_environment)

    @classmethod
    def from_environment(cls) -> "AppSettings":
        # Default CORS origins if not specified in environment
        default_cors_origins = ["*"]
        
        return cls(
            app_name=get_env_var("APP_NAME", cls.app_name),
            host=get_env_var("HOST", cls.host),
            port=get_env_var_int("PORT", cls.port),
            debug=get_env_var_bool("DEBUG", cls.debug),
            cors_origins=get_env_var_list("CORS_ORIGINS", default_cors_origins),
        )

settings = AppSettings.from_environment()
import logging
from dataclasses import dataclass, field
from typing import Optional, List
from hrbot.config.environment import (
    get_env_var, get_env_var_bool, get_env_var_float, get_env_var_int, get_env_var_list
)


logger = logging.getLogger("hrbot.config")

@dataclass(frozen=True)
class DatabaseSettings:
    name: str
    user: str
    password: str
    host: str
    port: int
    sslmode: str = "require"
    pool_size: int = 5
    max_overflow: int = 10
    pool_timeout: int = 30
    pool_recycle: int = 1800
    
    @property
    def url(self) -> str:
        """
        Assemble a SQLAlchemy URL using asyncpg.  
        Example: postgresql+asyncpg://user:pass@host:5432/dbname?sslmode=require
        """
        creds = f"{self.user}:{self.password}" if self.password else self.user
        return (
            f"postgresql+asyncpg://{creds}@{self.host}:{self.port}/{self.name}"
        )

    @property
    def engine_kwargs(self) -> dict:
        return dict(
            pool_size=self.pool_size,
            max_overflow=self.max_overflow,
            pool_timeout=self.pool_timeout,
            pool_recycle=self.pool_recycle,
        )
    
    @classmethod
    def from_environment(cls) -> "DatabaseSettings":
        # Prefer AWS Secrets Manager unless the caller explicitly disables it
        use_aws_secrets = get_env_var_bool("USE_AWS_SECRETS", True)
        
        if use_aws_secrets:
            try:
                from hrbot.utils.secret_manager import get_database_credentials, get_aws_region
                
                # Get AWS configuration
                region = get_aws_region()
                secret_name = get_env_var("AWS_DB_SECRET_NAME", "chatbot-clarity-db-dev-postgres")
                
                logger.info(f"Loading database credentials from AWS Secrets Manager: {secret_name}")
                db_creds = get_database_credentials(secret_name, region)
                
                return cls(
                    name=db_creds["database"],
                    user=db_creds["username"],
                    password=db_creds["password"],
                    host=db_creds["host"],
                    port=int(db_creds["port"]),
                    sslmode=db_creds.get("sslmode", "disable"),  # Default to disable if not present
                    pool_size=get_env_var_int("DB_POOL_SIZE", 5),
                    max_overflow=get_env_var_int("DB_MAX_OVERFLOW", 10),
                    pool_timeout=get_env_var_int("DB_POOL_TIMEOUT", 30),
                    pool_recycle=get_env_var_int("DB_POOL_RECYCLE", 1800),
                )
                
            except Exception as e:
                logger.error(f"Failed to load database credentials from AWS Secrets Manager: {e}")
                logger.info("Falling back to environment variables for database configuration")
                # Fall through to environment variable method
        
        # Default: Use environment variables
        return cls(
            name=get_env_var("DB_NAME", "nedal"),
            user=get_env_var("DB_USER", "postgres"),
            password=get_env_var("DB_PASSWORD", ""),
            host=get_env_var("DB_HOST", "localhost"),
            port=get_env_var_int("DB_PORT", 5432),
            sslmode=get_env_var("DB_SSLMODE", "disable"),  # Only used when not leveraging AWS Secrets
            pool_size=get_env_var_int("DB_POOL_SIZE", 5),
            max_overflow=get_env_var_int("DB_MAX_OVERFLOW", 10),
            pool_timeout=get_env_var_int("DB_POOL_TIMEOUT", 30),
            pool_recycle=get_env_var_int("DB_POOL_RECYCLE", 1800),
        )
    
@dataclass(frozen=True)
class GeminiSettings:
    model_name: str = "gemini-2.0-flash-001"
    temperature: float = 0.0
    max_output_tokens: int = 1024
    api_key: Optional[str] = None  # Prefer explicit API key over default credentials
    use_aws_secrets: bool = False
    credentials_path: Optional[str] = None  # Path to temp credentials file

    @classmethod
    def from_environment(cls) -> "GeminiSettings":
        # Prefer AWS Secrets Manager unless explicitly disabled
        use_aws_secrets = get_env_var_bool("USE_AWS_SECRETS", True)
        credentials_path = None
        
        if use_aws_secrets:
            try:
                from hrbot.utils.secret_manager import load_gemini_credentials, get_aws_region
                
                # Get AWS configuration
                region = get_aws_region()
                secret_name = get_env_var("AWS_GEMINI_SECRET_NAME", "genai-gemini-vertex-prod-api")
                
                logger.info(f"Loading Gemini credentials from AWS Secrets Manager: {secret_name}")
                credentials_path = load_gemini_credentials(secret_name, region)
                
                return cls(
                    model_name=get_env_var("GEMINI_MODEL_NAME", cls.model_name),
                    temperature=get_env_var_float("GEMINI_TEMPERATURE", cls.temperature),
                    max_output_tokens=get_env_var_int("GEMINI_MAX_OUTPUT_TOKENS", cls.max_output_tokens),
                    api_key=None,  # Will use service account from AWS
                    use_aws_secrets=True,
                    credentials_path=credentials_path,
                )
                
            except Exception as e:
                logger.error(f"Failed to load Gemini credentials from AWS Secrets Manager: {e}")
                logger.info("Falling back to environment variables for Gemini configuration")
                # Fall through to environment variable method
        
        # Default: Use environment variables
        return cls(
            model_name=get_env_var("GEMINI_MODEL_NAME", cls.model_name),
            temperature=get_env_var_float("GEMINI_TEMPERATURE", cls.temperature),
            max_output_tokens=get_env_var_int("GEMINI_MAX_OUTPUT_TOKENS", cls.max_output_tokens),
            api_key=get_env_var("GOOGLE_API_KEY"),
            use_aws_secrets=False,
            credentials_path=None,
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
class AWSSettings:
    """AWS-specific configuration settings."""
    use_secrets_manager: bool = False
    region: str = "us-west-1"
    db_secret_name: str = "chatbot-clarity-db-dev-postgres"
    gemini_secret_name: str = "genai-gemini-vertex-prod-api"
    
    @classmethod
    def from_environment(cls) -> "AWSSettings":
        return cls(
            use_secrets_manager=get_env_var_bool("USE_AWS_SECRETS", cls.use_secrets_manager),
            region=get_env_var("AWS_REGION", get_env_var("AWS_DEFAULT_REGION", cls.region)),
            db_secret_name=get_env_var("AWS_DB_SECRET_NAME", cls.db_secret_name),
            gemini_secret_name=get_env_var("AWS_GEMINI_SECRET_NAME", cls.gemini_secret_name),
        )

@dataclass(frozen=True)
class PerformanceSettings:
    """Performance optimization settings for Microsoft Teams streaming"""
    use_intent_classification: bool = False  # Skip Gemini-based intent classification
    cache_embeddings: bool = True
    cache_ttl_seconds: int = 3600
    min_streaming_length: int = 200  # Lowered from 400 to enable streaming for more responses
    show_acknowledgment_threshold: int = 10  # Show "looking into it" for queries > 10 words
    enable_streaming: bool = True  # Enable/disable streaming responses
    streaming_delay: float = 1.2  # Delay between chunks (Microsoft requires 1+ seconds)
    max_chunk_size: int = 150  # Maximum characters per chunk for optimal readability
    
    # Semantic similarity settings for HR topic detection
    hr_similarity_threshold: float = 0.55  # Lowered to be less restrictive for HR topics
    hr_borderline_threshold_offset: float = 0.20  # Increased range for borderline checks
    
    # Enhanced document processing settings
    chunk_size: int = 1500  # Increased for more comprehensive chunks
    chunk_overlap: int = 300  # Increased overlap to preserve context
    max_chunks_per_query: int = 12  # More chunks for comprehensive responses
    enable_table_extraction: bool = True  # Extract tables from PDFs
    enable_structure_preservation: bool = True  # Preserve document structure
    ocr_fallback: bool = False  # Use OCR for scanned documents (requires tesseract)
    
    @classmethod
    def from_environment(cls) -> "PerformanceSettings":
        return cls(
            use_intent_classification=get_env_var_bool("USE_INTENT_CLASSIFICATION", cls.use_intent_classification),
            cache_embeddings=get_env_var_bool("CACHE_EMBEDDINGS", cls.cache_embeddings),
            cache_ttl_seconds=get_env_var_int("CACHE_TTL_SECONDS", cls.cache_ttl_seconds),
            min_streaming_length=get_env_var_int("MIN_STREAMING_LENGTH", cls.min_streaming_length),
            show_acknowledgment_threshold=get_env_var_int("SHOW_ACK_THRESHOLD", cls.show_acknowledgment_threshold),
            enable_streaming=get_env_var_bool("ENABLE_STREAMING", cls.enable_streaming),
            streaming_delay=get_env_var_float("STREAMING_DELAY", cls.streaming_delay),
            max_chunk_size=get_env_var_int("MAX_CHUNK_SIZE", cls.max_chunk_size),
            hr_similarity_threshold=get_env_var_float("HR_SIMILARITY_THRESHOLD", cls.hr_similarity_threshold),
            hr_borderline_threshold_offset=get_env_var_float("HR_BORDERLINE_THRESHOLD_OFFSET", cls.hr_borderline_threshold_offset),
            chunk_size=get_env_var_int("DOCUMENT_CHUNK_SIZE", cls.chunk_size),
            chunk_overlap=get_env_var_int("DOCUMENT_CHUNK_OVERLAP", cls.chunk_overlap),
            max_chunks_per_query=get_env_var_int("MAX_CHUNKS_PER_QUERY", cls.max_chunks_per_query),
            enable_table_extraction=get_env_var_bool("ENABLE_TABLE_EXTRACTION", cls.enable_table_extraction),
            enable_structure_preservation=get_env_var_bool("ENABLE_STRUCTURE_PRESERVATION", cls.enable_structure_preservation),
            ocr_fallback=get_env_var_bool("OCR_FALLBACK", cls.ocr_fallback),
        )

@dataclass(frozen=True)
class AppSettings:
    app_name: str = "HR Teams Bot"
    host: str = "0.0.0.0"
    port: int = 3978
    debug: bool = False  # Set to False for production
    cors_origins: List[str] = field(default_factory=lambda: ["*"])  # Secure this for production
    db: DatabaseSettings = field(default_factory=DatabaseSettings.from_environment)
    gemini: GeminiSettings = field(default_factory=GeminiSettings.from_environment)
    embeddings: EmbeddingSettings = field(default_factory=EmbeddingSettings.from_environment)
    teams: TeamsSettings = field(default_factory=TeamsSettings.from_environment)
    google_cloud: GoogleCloudSettings = field(default_factory=GoogleCloudSettings.from_environment)
    feedback: FeedbackSettings = field(default_factory=FeedbackSettings.from_environment)
    hr_support: HRSupportSettings = field(default_factory=HRSupportSettings.from_environment)
    aws: AWSSettings = field(default_factory=AWSSettings.from_environment)
    performance: PerformanceSettings = field(default_factory=PerformanceSettings.from_environment)
    session_idle_minutes: int = 30

    @classmethod
    def from_environment(cls) -> "AppSettings":
        # Default CORS origins if not specified in environment
        default_cors_origins = ["*"]
        logger.info("Environment variables loaded; building AppSettings")
        return cls(
            db=DatabaseSettings.from_environment(),
            gemini=GeminiSettings.from_environment(),
            aws=AWSSettings.from_environment(),
            app_name=get_env_var("APP_NAME", cls.app_name),
            host=get_env_var("HOST", cls.host),
            port=get_env_var_int("PORT", cls.port),
            debug=get_env_var_bool("DEBUG", cls.debug),
            cors_origins=get_env_var_list("CORS_ORIGINS", default_cors_origins),
            session_idle_minutes=get_env_var_int("SESSION_IDLE_MINUTES", cls.session_idle_minutes),
        )
        
try:
    settings = AppSettings.from_environment()
    logger.info(f"Config loaded for env='{settings.app_name}'")
    if settings.aws.use_secrets_manager:
        logger.info("AWS Secrets Manager integration enabled")
    if settings.gemini.use_aws_secrets:
        logger.info("Gemini credentials loaded from AWS Secrets Manager")
except Exception as exc: 
    logger.critical("‼️  Failed to load configuration – exiting", exc_info=exc)
    raise
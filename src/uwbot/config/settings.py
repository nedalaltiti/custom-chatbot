import logging
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from uwbot.config.environment import (
    get_env_var, get_env_var_bool, get_env_var_float, get_env_var_int, get_env_var_list
)
from uwbot.config.app_config import get_app_config
from uwbot.utils.result import Result
import httpx


logger = logging.getLogger("uwbot.config")

@dataclass(frozen=True)
class DatabaseSettings:
    name: str
    user: str
    password: str
    host: str
    port: int
    sslmode: str = "disable"
    pool_size: int = 5
    max_overflow: int = 10
    pool_timeout: int = 30
    pool_recycle: int = 1800
    
    @property
    def url(self) -> str:
        """
        Assemble a SQLAlchemy URL using asyncpg.  
        Example: postgresql+asyncpg://user:pass@host:5432/dbname?sslmode=disable
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
        import os
        
        # Check if database initialization should be skipped
        skip_db_init = os.environ.get("SKIP_DB_INIT", "").lower() in ("true", "1", "yes")
        
        # Prefer AWS Secrets Manager unless the caller explicitly disables it
        use_aws_secrets = get_env_var_bool("USE_AWS_SECRETS", True)
        
        # Enhanced debugging
        logger.info(f"=== DATABASE CONFIGURATION DEBUG ===")
        logger.info(f"SKIP_DB_INIT: {skip_db_init}")
        logger.info(f"USE_AWS_SECRETS: {use_aws_secrets}")
        logger.info(f"AWS_DB_SECRET_NAME: {os.environ.get('AWS_DB_SECRET_NAME', 'NOT_SET')}")
        
        if use_aws_secrets and not skip_db_init:
            try:
                from uwbot.utils.secret_manager import get_database_credentials, get_aws_region
                
                # Get AWS configuration
                region = get_aws_region()
                secret_name = get_env_var("AWS_DB_SECRET_NAME", "chatbot-clarity-db-dev-postgres")
                
                logger.info(f"Attempting to load database credentials from AWS Secrets Manager: {secret_name}")
                db_creds = get_database_credentials(secret_name, region)
                
                result = cls(
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
                
                logger.info(f"✅ AWS Database config: host={result.host}, port={result.port}, database={result.name}")
                logger.info(f"Database URL: {result.url}")
                return result
                
            except Exception as e:
                logger.error(f"❌ Failed to load database credentials from AWS Secrets Manager: {e}")
                
                # If USE_AWS_SECRETS=true but AWS fails, we don't want to fall back to local DB
                # Instead, provide a dummy configuration that will fail gracefully at runtime
                if use_aws_secrets:
                    logger.error("AWS Secrets Manager is enabled but failed. Application will not start.")
                    logger.error("Please check your AWS credentials and network connectivity.")
                    logger.error("To use local database instead, set USE_AWS_SECRETS=false")
                    
                    # Return dummy configuration that will cause a clear error at runtime
                    result = cls(
                        name="aws_rds_unavailable",
                        user="aws_rds_unavailable", 
                        password="aws_rds_unavailable",
                        host="aws_rds_unavailable",
                        port=5432,
                        sslmode="disable",
                        pool_size=get_env_var_int("DB_POOL_SIZE", 5),
                        max_overflow=get_env_var_int("DB_MAX_OVERFLOW", 10),
                        pool_timeout=get_env_var_int("DB_POOL_TIMEOUT", 30),
                        pool_recycle=get_env_var_int("DB_POOL_RECYCLE", 1800),
                    )
                    
                    logger.error(f"Using dummy config: {result.url}")
                    return result
                
                logger.info("Falling back to environment variables for database configuration")
                # Fall through to environment variable method only if USE_AWS_SECRETS=false
        
        # Get database settings from environment variables
        db_name = get_env_var("DB_NAME") 
        db_user = get_env_var("DB_USER")
        db_password = get_env_var("DB_PASSWORD")
        db_host = get_env_var("DB_HOST")
        
        # Enhanced environment variable debugging
        logger.info(f"=== ENVIRONMENT VARIABLE FALLBACK ===")
        logger.info(f"DB_NAME: {db_name or 'NOT_SET'}")
        logger.info(f"DB_USER: {db_user or 'NOT_SET'}")
        logger.info(f"DB_PASSWORD: {'SET' if db_password else 'NOT_SET'}")
        logger.info(f"DB_HOST: {db_host or 'NOT_SET'}")
        logger.info(f"DB_PORT: {os.environ.get('DB_PORT', 'NOT_SET')}")
        
        # Provide safe fallbacks when database initialization is skipped
        if skip_db_init:
            logger.info("SKIP_DB_INIT=true - using dummy database configuration")
            result = cls(
                name=db_name or "dummy",
                user=db_user or "dummy",
                password=db_password or "dummy",
                host=db_host or "localhost",  # Use localhost to avoid DNS issues
                port=get_env_var_int("DB_PORT", 5432),
                sslmode=get_env_var("DB_SSLMODE", "disable"),
                pool_size=get_env_var_int("DB_POOL_SIZE", 5),
                max_overflow=get_env_var_int("DB_MAX_OVERFLOW", 10),
                pool_timeout=get_env_var_int("DB_POOL_TIMEOUT", 30),
                pool_recycle=get_env_var_int("DB_POOL_RECYCLE", 1800),
            )
            logger.info(f"Skip DB config: {result.url}")
            return result
        
        # Default: Use environment variables with validation
        if not all([db_name, db_user, db_password, db_host]):
            missing = [name for name, val in [("DB_NAME", db_name), ("DB_USER", db_user), 
                                            ("DB_PASSWORD", db_password), ("DB_HOST", db_host)] if not val]
            
            # Only require local DB variables if USE_AWS_SECRETS=false
            if not use_aws_secrets:
                raise ValueError(f"Missing required database environment variables: {missing}")
            else:
                # If AWS is enabled but failed, and no local variables, return dummy config
                logger.warning("AWS Secrets Manager failed and no local DB variables provided")
                result = cls(
                    name="placeholder",
                    user="placeholder",
                    password="placeholder", 
                    host="placeholder",
                    port=5432,
                    sslmode="disable",
                    pool_size=get_env_var_int("DB_POOL_SIZE", 5),
                    max_overflow=get_env_var_int("DB_MAX_OVERFLOW", 10),
                    pool_timeout=get_env_var_int("DB_POOL_TIMEOUT", 30),
                    pool_recycle=get_env_var_int("DB_POOL_RECYCLE", 1800),
                )
                logger.warning(f"Placeholder config: {result.url}")
                return result
            
        result = cls(
            name=db_name,
            user=db_user,
            password=db_password,
            host=db_host,
            port=get_env_var_int("DB_PORT", 5432),
            sslmode=get_env_var("DB_SSLMODE", "disable"),
            pool_size=get_env_var_int("DB_POOL_SIZE", 5),
            max_overflow=get_env_var_int("DB_MAX_OVERFLOW", 10),
            pool_timeout=get_env_var_int("DB_POOL_TIMEOUT", 30),
            pool_recycle=get_env_var_int("DB_POOL_RECYCLE", 1800),
        )
        
        logger.info(f"✅ Environment variable config: host={result.host}, port={result.port}, database={result.name}")
        logger.info(f"Database URL: {result.url}")
        return result

    use_aws_secrets: bool = False


@dataclass(frozen=True)
class TeamsSettings:
    app_id: Optional[str] = None
    app_password: Optional[str] = None
    tenant_id: Optional[str] = None  # Shared Azure AD tenant ID for all app instances
    client_id: Optional[str] = None
    client_secret: Optional[str] = None

    @classmethod
    def from_environment(cls) -> "TeamsSettings":
        # With separate .env files, we now use generic environment variables
        # The appropriate .env.jo or .env.us file should be loaded based on the instance
        
        app_id = get_env_var("APP_ID") or get_env_var("MICROSOFT_APP_ID")
        app_password = get_env_var("APP_PASSWORD") or get_env_var("MICROSOFT_APP_PASSWORD")
        
        try:
            app_config = get_app_config()
            logger.info(f"Loading Teams settings for app instance: {app_config.name}")
        except Exception as e:
            logger.warning(f"Could not get app config context: {e}")
        
        if app_id:
            logger.info("Using APP_ID from environment")
        else:
            logger.warning("No APP_ID found in environment")
                
        return cls(
            app_id=app_id,
            app_password=app_password,
            tenant_id=get_env_var("TENANT_ID"),  # Same tenant for all app instances
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
            admin_token=get_env_var("ADMIN_TOKEN"),
            feedback_timeout_minutes=get_env_var_int("FEEDBACK_TIMEOUT_MINUTES", cls.feedback_timeout_minutes),
        )

@dataclass(frozen=True)
class AWSSettings:
    """AWS-specific configuration settings."""
    use_secrets_manager: bool = False
    region: str = "us-west-1"
    db_secret_name: str = "chatbot-clarity-db-dev-postgres"
    
    @classmethod
    def from_environment(cls) -> "AWSSettings":
        return cls(
            use_secrets_manager=get_env_var_bool("USE_AWS_SECRETS", cls.use_secrets_manager),
            region=get_env_var("AWS_REGION", get_env_var("AWS_DEFAULT_REGION", cls.region)),
            db_secret_name=get_env_var("AWS_DB_SECRET_NAME", cls.db_secret_name),
        )

@dataclass(frozen=True)
class PerformanceSettings:
    """Performance optimization settings for Microsoft Teams streaming"""
    use_intent_classification: bool = False  # Skip LLM-based intent classification (uwbot uses keywords)
    min_streaming_length: int = 200  # Lowered from 400 to enable streaming for more responses
    show_acknowledgment_threshold: int = 10  # Show "looking into it" for queries > 10 words
    enable_streaming: bool = True  # Enable/disable streaming responses
    streaming_delay: float = 0.8  # Reduced delay for faster streaming (Microsoft minimum)
    max_chunk_size: int = 120  # Reduced for faster perception
    
    @classmethod
    def from_environment(cls) -> "PerformanceSettings":
        return cls(
            use_intent_classification=get_env_var_bool("USE_INTENT_CLASSIFICATION", cls.use_intent_classification),
            min_streaming_length=get_env_var_int("MIN_STREAMING_LENGTH", cls.min_streaming_length),
            show_acknowledgment_threshold=get_env_var_int("SHOW_ACK_THRESHOLD", cls.show_acknowledgment_threshold),
            enable_streaming=get_env_var_bool("ENABLE_STREAMING", cls.enable_streaming),
            streaming_delay=get_env_var_float("STREAMING_DELAY", cls.streaming_delay),
            max_chunk_size=get_env_var_int("MAX_CHUNK_SIZE", cls.max_chunk_size),
        )

@dataclass(frozen=True)
class ExternalValidationSettings:
    """External validation API configuration settings."""
    api_base_url: str = "https://underwriting-validator-dev.usclaritytech.com"
    timeout: float = 30.0  # Request timeout in seconds
    
    @classmethod
    def from_environment(cls) -> "ExternalValidationSettings":
        return cls(
            api_base_url=get_env_var("EXTERNAL_VALIDATION_API_URL", cls.api_base_url),
            timeout=get_env_var_float("EXTERNAL_VALIDATION_TIMEOUT", cls.timeout),
        )

@dataclass(frozen=True)
class HardshipFields:
    """Hardship field configuration settings."""
    financial_hardship_id: str = "financial_hardship"
    hardship_description_id: str = "hardship_description"
    
    def validate(self) -> bool:
        """Validate hardship field configuration."""
        return bool(self.financial_hardship_id and self.hardship_description_id)
    
    @classmethod
    def from_environment(cls) -> "HardshipFields":
        return cls(
            financial_hardship_id=get_env_var("HARDSHIP_FINANCIAL_ID", cls.financial_hardship_id),
            hardship_description_id=get_env_var("HARDSHIP_DESCRIPTION_ID", cls.hardship_description_id),
        )

@dataclass(frozen=True)
class BudgetFields:
    """Budget field configuration settings."""
    acctid: str = "acctid"
    c_type: str = "c_type"
    iscoapp: str = "iscoapp"
    leadstatus: str = "leadstatus"
    
    def validate(self) -> bool:
        """Validate budget field configuration."""
        return bool(self.acctid and self.c_type and self.iscoapp and self.leadstatus)
    
    @classmethod
    def from_environment(cls) -> "BudgetFields":
        return cls(
            acctid=get_env_var("BUDGET_ACCTID", cls.acctid),
            c_type=get_env_var("BUDGET_C_TYPE", cls.c_type),
            iscoapp=get_env_var("BUDGET_ISCOAPP", cls.iscoapp),
            leadstatus=get_env_var("BUDGET_LEADSTATUS", cls.leadstatus),
        )

@dataclass(frozen=True)
class AppSettings:
    app_name: str = "UWBot Teams Bot"
    host: str = "0.0.0.0"
    port: int = 3979
    environment: str = "development" 
    debug: bool = False  # Set to False for production
    cors_origins: List[str] = field(default_factory=lambda: ["*"])  # Secure this for production
    db: DatabaseSettings = field(default_factory=DatabaseSettings.from_environment)
    teams: TeamsSettings = field(default_factory=TeamsSettings.from_environment)
    google_cloud: GoogleCloudSettings = field(default_factory=GoogleCloudSettings.from_environment)
    feedback: FeedbackSettings = field(default_factory=FeedbackSettings.from_environment)
    aws: AWSSettings = field(default_factory=AWSSettings.from_environment)
    performance: PerformanceSettings = field(default_factory=PerformanceSettings.from_environment)
    external_validation: ExternalValidationSettings = field(default_factory=ExternalValidationSettings.from_environment)
    hardship_fields: HardshipFields = field(default_factory=HardshipFields.from_environment)
    budget_fields: BudgetFields = field(default_factory=BudgetFields.from_environment)
    session_idle_minutes: int = 30

    @classmethod
    def from_environment(cls) -> "AppSettings":
        # Default CORS origins if not specified in environment
        default_cors_origins = ["*"]
        logger.info("Environment variables loaded; building AppSettings")
        
        return cls(
            db=DatabaseSettings.from_environment(),
            aws=AWSSettings.from_environment(),
            external_validation=ExternalValidationSettings.from_environment(),
            hardship_fields=HardshipFields.from_environment(),
            budget_fields=BudgetFields.from_environment(),
            app_name=get_env_var("APP_NAME", cls.app_name),
            host=get_env_var("HOST", cls.host),
            port=get_env_var_int("PORT", cls.port),
            environment=get_env_var("ENVIRONMENT", cls.environment),
            debug=get_env_var_bool("DEBUG", cls.debug),
            cors_origins=get_env_var_list("CORS_ORIGINS", default_cors_origins),
            session_idle_minutes=get_env_var_int("SESSION_IDLE_MINUTES", cls.session_idle_minutes),
        )
        
try:
    settings = AppSettings.from_environment()
    logger.info(f"Config loaded for env='{settings.app_name}'")
    if settings.aws.use_secrets_manager:
        logger.info("AWS Secrets Manager integration enabled")
except Exception as exc: 
    logger.critical("‼️  Failed to load configuration – exiting", exc_info=exc)
    raise
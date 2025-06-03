# src/customer_sentiment_hub/utils/secret_manager.py

import os
import json
import tempfile
import logging
from typing import Dict, Optional
import boto3
from botocore.exceptions import ClientError, NoCredentialsError

logger = logging.getLogger(__name__)

def get_aws_secret(secret_name: str, region_name: str = "us-west-1") -> Dict:
    """
    Retrieve a secret from AWS Secrets Manager.
    
    Args:
        secret_name: Name of the secret in AWS Secrets Manager
        region_name: AWS region where the secret is stored
        
    Returns:
        Dictionary containing the secret data
        
    Raises:
        ClientError: If AWS API call fails
        ValueError: If secret format is invalid
        NoCredentialsError: If AWS credentials are not configured
    """
    try:
        # Debug logging for credential availability
        aws_access_key_id = os.environ.get('AWS_ACCESS_KEY_ID')
        aws_secret_access_key = os.environ.get('AWS_SECRET_ACCESS_KEY')
        
        logger.debug(f"AWS credentials check: ACCESS_KEY_ID={'SET' if aws_access_key_id else 'NOT_SET'}, "
                    f"SECRET_ACCESS_KEY={'SET' if aws_secret_access_key else 'NOT_SET'}")
        
        if not aws_access_key_id or not aws_secret_access_key:
            logger.warning("AWS credentials not found in environment variables - this may cause authentication issues")
        
        # Use environment variables for AWS credentials (more robust than explicit passing)
        session = boto3.session.Session()
        client = session.client(
            service_name='secretsmanager',
            region_name=region_name
        )
        
        logger.info(f"Fetching secret: {secret_name} from region: {region_name}")
        
        response = client.get_secret_value(SecretId=secret_name)
        secret_string = response.get('SecretString')
        
        if not secret_string:
            raise ValueError(f"Secret {secret_name} did not contain a SecretString")
        
        secret_data = json.loads(secret_string)
        logger.info(f"Successfully retrieved secret: {secret_name}")
        
        return secret_data
        
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        logger.error(f"Failed to fetch secret {secret_name}: {error_code} - {str(e)}")
        raise
    except NoCredentialsError as e:
        logger.error(f"AWS credentials not configured: {str(e)}")
        raise
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON format in secret {secret_name}: {str(e)}")
        raise ValueError(f"Secret {secret_name} contains invalid JSON")


def get_database_credentials(
    secret_name: str = None,
    region_name: str = "us-west-1"
) -> Dict[str, str]:
    """
    Fetch database credentials from AWS Secrets Manager.
    
    Args:
        secret_name: Name of the database secret (defaults to env var)
        region_name: AWS region
        
    Returns:
        Dictionary with database connection parameters
    """
    # Get secret name from environment variable
    secret_name = secret_name or os.environ.get("AWS_DB_SECRET_NAME", "chatbot-clarity-db-dev-postgres")
    
    try:
        credentials = get_aws_secret(secret_name, region_name)
        
        # Normalize/strip whitespace to avoid connection issues (e.g. stray newlines)
        db_config = {
            "username": (credentials.get("USERNAME") or "").strip(),
            "password": (credentials.get("PASSWORD") or "").strip(), 
            "host": (credentials.get("HOST") or "").strip(),
            "port": str(credentials.get("PORT", "5432")).strip(),
            "database": (credentials.get("DATABASE_NAME") or "").strip(),
            "schema": (credentials.get("SCHEMA_NAME") or "").strip(),
            "sslmode": (credentials.get("SSLMODE") or "disable").strip().lower() or "disable"
        }
        
        # Validate required fields
        required_fields = ["username", "password", "host", "database"]
        missing_fields = [field for field in required_fields if not db_config.get(field)]
        
        if missing_fields:
            raise ValueError(f"Database secret missing required fields: {missing_fields}")
        
        logger.info("Database credentials successfully retrieved from AWS Secrets Manager")
        logger.info(f"Database host: {db_config['host']}, SSL mode: {db_config['sslmode']}")
        return db_config
        
    except Exception as e:
        logger.error(f"Failed to get database credentials: {str(e)}")
        raise


def load_gemini_credentials(
    secret_name: str = None,
    region_name: str = "us-west-1"
) -> str:
    """
    Fetch Gemini service account credentials from AWS Secrets Manager,
    write to temp file, and set environment variables.
    
    Args:
        secret_name: Name of the Gemini secret (defaults to env var)
        region_name: AWS region
        
    Returns:
        Path to the temporary credentials file
    """
    # Get secret name from environment variable
    secret_name = secret_name or os.environ.get("AWS_GEMINI_SECRET_NAME", "genai-gemini-vertex-prod-api")
    
    try:
        credentials = get_aws_secret(secret_name, region_name)
        
        # Fix private key formatting (AWS may escape newlines)
        if "private_key" in credentials and isinstance(credentials["private_key"], str):
            credentials["private_key"] = credentials["private_key"].replace("\\n", "\n")
        
        # Validate required fields for service account
        required_fields = ["type", "project_id", "private_key", "client_email"]
        missing_fields = [field for field in required_fields if not credentials.get(field)]
        
        if missing_fields:
            raise ValueError(f"Gemini secret missing required fields: {missing_fields}")
        
        # Write credentials to secure temporary file
        fd, temp_path = tempfile.mkstemp(
            prefix="gemini_creds_", 
            suffix=".json"
        )
        
        try:
            with os.fdopen(fd, 'w') as f:
                json.dump(credentials, f, indent=2)
            
            # Set environment variables for Google libraries
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = temp_path
            
            if credentials.get("project_id"):
                os.environ["GOOGLE_CLOUD_PROJECT"] = credentials["project_id"]
            
            # Set location from environment or use default
            location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
            os.environ["GOOGLE_CLOUD_LOCATION"] = location
            
            logger.info(f"Gemini credentials loaded from AWS Secrets Manager")
            logger.info(f"Project: {credentials.get('project_id')}, Location: {location}")
            
            return temp_path
            
        except Exception as e:
            # Clean up temp file if something goes wrong
            try:
                os.unlink(temp_path)
            except:
                pass
            raise
            
    except Exception as e:
        logger.error(f"Failed to load Gemini credentials: {str(e)}")
        raise


def cleanup_temp_credentials(temp_path: str) -> None:
    """
    Safely remove temporary credentials file.
    
    Args:
        temp_path: Path to the temporary credentials file
    """
    try:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)
            logger.debug(f"Cleaned up temporary credentials file: {temp_path}")
    except Exception as e:
        logger.warning(f"Failed to cleanup temp credentials file {temp_path}: {e}")


def is_aws_secrets_enabled() -> bool:
    """
    Check if AWS Secrets Manager integration is enabled.
    
    Returns:
        True if AWS secrets should be used, False otherwise
    """
    return os.environ.get("USE_AWS_SECRETS", "false").lower() in ("true", "1", "yes")


def get_aws_region() -> str:
    """
    Get AWS region from environment or use default.
    
    Returns:
        AWS region string
    """
    return os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-west-1"))
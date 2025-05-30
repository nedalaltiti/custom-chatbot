import os
from dotenv import load_dotenv
load_dotenv()

# Test AWS Secrets Manager
try:
    from hrbot.utils.secret_manager import get_database_credentials, get_aws_region
    region = get_aws_region()
    secret_name = os.getenv("AWS_DB_SECRET_NAME", "chatbot-clarity-db-dev-postgres")
    
    print(f"Loading secret: {secret_name} from region: {region}")
    db_creds = get_database_credentials(secret_name, region)
    
    print(f"Database Host: {db_creds['host']}")
    print(f"Database Port: {db_creds['port']}")
    print(f"Database Name: {db_creds['database']}")
    print(f"Database User: {db_creds['username']}")
    
    # Construct the URL like the app does
    from hrbot.config.settings import DatabaseSettings
    db_settings = DatabaseSettings(
        name=db_creds["database"],
        user=db_creds["username"],
        password=db_creds["password"],
        host=db_creds["host"],
        port=int(db_creds["port"]),
        sslmode=db_creds.get("sslmode", "disable")
    )
    print(f"Database URL: {db_settings.url}")
    
except Exception as e:
    print(f"Error: {e}")

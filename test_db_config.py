from dotenv import load_dotenv
load_dotenv()

from hrbot.config.settings import DatabaseSettings

db_settings = DatabaseSettings.from_environment()
print(f"Database URL: {db_settings.url}")
print(f"Host: {db_settings.host}")
print(f"Database: {db_settings.name}")
print(f"Use AWS Secrets: {load_dotenv() or __import__('os').getenv('USE_AWS_SECRETS')}")

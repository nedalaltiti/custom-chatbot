"""
Multi-App Configuration for HR Bot - CI/CD Friendly & Scalable.

This module manages configuration for multiple app registrations within the same Azure AD tenant.
New instances can be added simply by updating the configuration file - no code changes required.

Features:
- Configuration-driven instances (instances.yaml)
- Automatic directory provisioning
- Standardized hostname patterns
- CI/CD friendly deployment

App instance detection priority:
1. Hostname-based detection (from ingress URL patterns)
2. APP_INSTANCE environment variable
3. Default instance from config

To add a new region:
1. Add entry to instances.yaml
2. Create deployment manifest
3. Deploy - directories and configs are auto-created
"""

import os
import yaml
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, Optional, List, Any
import logging

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AppConfig:
    """Configuration for a specific app instance."""
    instance_id: str
    name: str
    knowledge_base_dir: Path
    embeddings_dir: Path
    prompt_dir: Path
    hr_support_url: str
    supports_noi: bool = False
    hostname_patterns: List[str] = None
    default_instance: bool = False


class AppInstanceManager:
    """Manages app instances from configuration file."""
    
    def __init__(self, config_path: str = "instances.yaml"):
        self.config_path = config_path
        self._instances: Dict[str, AppConfig] = {}
        self._hostname_patterns: Dict[str, str] = {}  # pattern -> instance_id
        self._default_instance: Optional[str] = None
        self._load_configuration()
    
    def _load_configuration(self):
        """Load instance configuration from YAML file."""
        config_file = Path(self.config_path)
        
        # Create default config if it doesn't exist
        if not config_file.exists():
            logger.info(f"Creating default configuration: {config_file}")
            self._create_default_config(config_file)
        
        try:
            with open(config_file, 'r') as f:
                config_data = yaml.safe_load(f)
            
            self._parse_configuration(config_data)
            logger.info(f"Loaded {len(self._instances)} instances from {config_file}")
            
        except Exception as e:
            logger.error(f"Failed to load configuration from {config_file}: {e}")
            # Fall back to hardcoded minimal config
            self._create_fallback_config()
    
    def _create_default_config(self, config_file: Path):
        """Create a default instances.yaml file."""
        default_config = {
            'instances': {
                'jo': {
                    'name': 'Jo HR Assistant',
                    'supports_noi': True,
                    'hr_support_url': 'https://hrsupport.usclarity.com/support/home',
                    'hostname_patterns': ['hr-chatbot-jo-*', '*-jo-*'],
                    'default': True
                },
                'us': {
                    'name': 'US HR Assistant', 
                    'supports_noi': False,
                    'hr_support_url': 'https://hrsupport.usclarity.com/support/home',
                    'hostname_patterns': ['hr-chatbot-us-*', '*-us-*'],
                    'default': False
                }
            },
            'global_settings': {
                'data_base_dir': 'data',
                'auto_create_directories': True
            }
        }
        
        with open(config_file, 'w') as f:
            yaml.dump(default_config, f, default_flow_style=False, indent=2)
        
        logger.info(f"Created default configuration: {config_file}")
    
    def _parse_configuration(self, config_data: Dict[str, Any]):
        """Parse configuration data and create AppConfig instances."""
        instances_config = config_data.get('instances', {})
        global_settings = config_data.get('global_settings', {})
        
        data_base_dir = Path(global_settings.get('data_base_dir', 'data'))
        auto_create = global_settings.get('auto_create_directories', True)
        
        for instance_id, instance_data in instances_config.items():
            # Build paths
            knowledge_dir = data_base_dir / 'knowledge' / instance_id
            embeddings_dir = data_base_dir / 'embeddings' / instance_id
            prompt_dir = data_base_dir / 'prompts' / instance_id
            
            # Auto-create directories if enabled
            if auto_create:
                for directory in [knowledge_dir, embeddings_dir, prompt_dir]:
                    directory.mkdir(parents=True, exist_ok=True)
                    logger.debug(f"Ensured directory exists: {directory}")
            
            # Create AppConfig
            app_config = AppConfig(
                instance_id=instance_id,
                name=instance_data.get('name', f'{instance_id.title()} HR Assistant'),
                knowledge_base_dir=knowledge_dir,
                embeddings_dir=embeddings_dir,
                prompt_dir=prompt_dir,
                hr_support_url=instance_data.get('hr_support_url', 'https://hrsupport.usclarity.com/support/home'),
                supports_noi=instance_data.get('supports_noi', False),
                hostname_patterns=instance_data.get('hostname_patterns', []),
                default_instance=instance_data.get('default', False)
            )
            
            self._instances[instance_id] = app_config
            
            # Register hostname patterns
            for pattern in app_config.hostname_patterns:
                self._hostname_patterns[pattern.lower()] = instance_id
            
            # Set default instance
            if app_config.default_instance:
                self._default_instance = instance_id
        
        # Ensure we have a default
        if not self._default_instance and self._instances:
            first_instance = next(iter(self._instances.keys()))
            self._default_instance = first_instance
            logger.info(f"No default instance specified, using: {first_instance}")
    
    def _create_fallback_config(self):
        """Create minimal fallback configuration when file loading fails."""
        logger.warning("Using fallback configuration")
        
        self._instances = {
            'jo': AppConfig(
                instance_id='jo',
                name='Jo HR Assistant',
                knowledge_base_dir=Path('data/knowledge/jo'),
                embeddings_dir=Path('data/embeddings/jo'),
                prompt_dir=Path('data/prompts/jo'),
                hr_support_url='https://hrsupport.usclarity.com/support/home',
                supports_noi=True,
                hostname_patterns=['hr-chatbot-jo-*', '*-jo-*'],
                default_instance=True
            ),
            'us': AppConfig(
                instance_id='us',
                name='US HR Assistant',
                knowledge_base_dir=Path('data/knowledge/us'),
                embeddings_dir=Path('data/embeddings/us'),
                prompt_dir=Path('data/prompts/us'),
                hr_support_url='https://hrsupport.usclarity.com/support/home',
                supports_noi=False,
                hostname_patterns=['hr-chatbot-us-*', '*-us-*'],
                default_instance=False
            )
        }
        
        self._hostname_patterns = {
            'hr-chatbot-jo-*': 'jo',
            '*-jo-*': 'jo',
            'hr-chatbot-us-*': 'us',
            '*-us-*': 'us'
        }
        
        self._default_instance = 'jo'
    
    def get_instance(self, instance_id: str) -> Optional[AppConfig]:
        """Get instance configuration by ID."""
        return self._instances.get(instance_id)
    
    def get_all_instances(self) -> Dict[str, AppConfig]:
        """Get all configured instances."""
        return self._instances.copy()
    
    def detect_instance_from_hostname(self, hostname: Optional[str] = None) -> Optional[str]:
        """Detect instance from hostname using configured patterns."""
        if not hostname:
            # Try to get hostname from environment
            hostname = (
                os.environ.get("HOSTNAME") or
                os.environ.get("HOST") or
                os.environ.get("SERVER_NAME") or
                os.environ.get("INGRESS_HOST")
            )
            
            if not hostname:
                try:
                    import socket
                    hostname = socket.gethostname()
                except:
                    pass
        
        if not hostname:
            logger.debug("No hostname available for instance detection")
            return None
        
        hostname = hostname.lower()
        logger.info(f"Detecting instance from hostname: {hostname}")
        
        # Check patterns
        for pattern, instance_id in self._hostname_patterns.items():
            # Convert glob pattern to simple check
            if pattern.startswith('*') and pattern.endswith('*'):
                # *-jo-* -> check if '-jo-' in hostname
                check = pattern[1:-1]
                if check in hostname:
                    logger.info(f"Matched pattern '{pattern}' -> instance '{instance_id}'")
                    return instance_id
            elif pattern.startswith('*'):
                # *-jo -> check if hostname ends with '-jo'
                check = pattern[1:]
                if hostname.endswith(check):
                    logger.info(f"Matched pattern '{pattern}' -> instance '{instance_id}'")
                    return instance_id
            elif pattern.endswith('*'):
                # hr-chatbot-jo-* -> check if hostname starts with 'hr-chatbot-jo-'
                check = pattern[:-1]
                if hostname.startswith(check):
                    logger.info(f"Matched pattern '{pattern}' -> instance '{instance_id}'")
                    return instance_id
            else:
                # Exact match
                if hostname == pattern:
                    logger.info(f"Matched pattern '{pattern}' -> instance '{instance_id}'")
                    return instance_id
        
        logger.debug(f"No pattern matched for hostname: {hostname}")
        return None
    
    def get_default_instance(self) -> str:
        """Get the default instance ID."""
        return self._default_instance or 'jo'


# Global instance manager
_instance_manager: Optional[AppInstanceManager] = None

def get_instance_manager() -> AppInstanceManager:
    """Get the global instance manager."""
    global _instance_manager
    if _instance_manager is None:
        _instance_manager = AppInstanceManager()
    return _instance_manager


def detect_app_instance_from_hostname() -> Optional[str]:
    """Detect app instance from hostname using configured patterns."""
    return get_instance_manager().detect_instance_from_hostname()


def detect_app_instance_from_env() -> Optional[str]:
    """Detect app instance from APP_INSTANCE environment variable."""
    instance_id = os.environ.get("APP_INSTANCE")
    if instance_id:
        manager = get_instance_manager()
        if manager.get_instance(instance_id):
            return instance_id
        else:
            logger.warning(f"Invalid APP_INSTANCE '{instance_id}' - not found in configuration")
    return None


def get_current_app_instance() -> str:
    """
    Get the current app instance using detection priority:
    1. Hostname-based detection (from configured patterns)
    2. APP_INSTANCE environment variable  
    3. Default instance from configuration
    
    Returns:
        Current app instance ID
    """
    manager = get_instance_manager()
    
    # Try hostname detection first (for deployment)
    instance_id = detect_app_instance_from_hostname()
    if instance_id:
        logger.info(f"App instance detected from hostname: {instance_id}")
        return instance_id
    
    # Fall back to environment variable (for local development)
    instance_id = detect_app_instance_from_env()
    if instance_id:
        logger.info(f"App instance detected from environment: {instance_id}")
        return instance_id
    
    # Default fallback
    default_instance = manager.get_default_instance()
    logger.info(f"No instance detected, using default: {default_instance}")
    return default_instance


def get_current_app_config() -> AppConfig:
    """
    Get the configuration for the current app instance.
    
    Returns:
        App configuration for current instance
    """
    instance_id = get_current_app_instance()
    manager = get_instance_manager()
    config = manager.get_instance(instance_id)
    
    if not config:
        raise RuntimeError(f"No configuration found for instance: {instance_id}")
    
    return config


def is_feature_enabled(feature_name: str) -> bool:
    """
    Check if a feature is enabled for the current app instance.
    
    Args:
        feature_name: Name of the feature to check
        
    Returns:
        True if feature is enabled, False otherwise
    """
    app_config = get_current_app_config()
    
    if feature_name.lower() == "noi":
        return app_config.supports_noi
    
    # Add other features here as needed
    logger.warning(f"Unknown feature: {feature_name}")
    return False


def set_hostname_for_testing(hostname: str) -> None:
    """Set hostname for testing purposes."""
    os.environ["HOSTNAME"] = hostname
    logger.info(f"Set hostname for testing: {hostname}")


def add_instance_to_config(instance_id: str, instance_config: Dict[str, Any], config_path: str = "instances.yaml") -> bool:
    """
    Add a new instance to the configuration file.
    
    Args:
        instance_id: Unique identifier for the instance
        instance_config: Instance configuration dictionary
        config_path: Path to the configuration file
        
    Returns:
        True if successful, False otherwise
    """
    try:
        config_file = Path(config_path)
        
        # Load existing config
        if config_file.exists():
            with open(config_file, 'r') as f:
                config_data = yaml.safe_load(f) or {}
        else:
            config_data = {'instances': {}, 'global_settings': {}}
        
        # Add new instance
        config_data['instances'][instance_id] = instance_config
        
        # Write back
        with open(config_file, 'w') as f:
            yaml.dump(config_data, f, default_flow_style=False, indent=2)
        
        logger.info(f"Added instance '{instance_id}' to configuration")
        
        # Reload the instance manager
        global _instance_manager
        _instance_manager = None  # Force reload
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to add instance to configuration: {e}")
        return False


def list_available_instances() -> List[str]:
    """List all available instance IDs."""
    return list(get_instance_manager().get_all_instances().keys())


# Cached instance for performance
_current_instance: Optional[str] = None

def get_cached_app_instance() -> str:
    """Get app instance with caching for better performance."""
    global _current_instance
    
    if _current_instance is None:
        _current_instance = get_current_app_instance()
        
    return _current_instance


def clear_instance_cache() -> None:
    """Clear the cached app instance (useful for testing)."""
    global _current_instance, _instance_manager
    _current_instance = None
    _instance_manager = None
    logger.debug("Cleared app instance cache")
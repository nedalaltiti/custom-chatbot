"""
Environment variable handling with validation and type conversion.

This module provides functions for retrieving environment variables with
proper typing, validation, and default values using a fail-safe approach.
"""

import os
import logging
from typing import Any, Callable, Dict, Generic, Optional, TypeVar, Union, cast


try:
    from dotenv import load_dotenv
    load_dotenv()
    DOTENV_LOADED = True
except ImportError:
    DOTENV_LOADED = False

# Configure logging
logger = logging.getLogger("hrbot.config")

# Type variable for generic type hints
T = TypeVar('T')
V = TypeVar('V')

# Type converter registry for environment variables
TYPE_CONVERTERS: Dict[type, Callable[[str], Any]] = {
    str: str,
    int: int,
    float: float,
    bool: lambda v: v.lower() in ('true', 'yes', 'y', '1', 'on'),
    list: lambda v: [item.strip() for item in v.split(',') if item.strip()],
}

def get_env_var(name: str, default: Optional[T] = None, var_type: Optional[type] = None) -> Any:
    """
    Get environment variable with validation and type conversion.
    
    Args:
        name: The name of the environment variable
        default: Default value if not set
        var_type: Type to convert the value to (inferred from default if not provided)
    
    Returns:
        The value of the environment variable converted to the appropriate type
    
    Examples:
        >>> get_env_var("PORT", 8000, int)  # Returns PORT as int with default 8000
        >>> get_env_var("DEBUG", False)     # Infers bool type from default value
    """
    # Get the raw value from environment
    value = os.environ.get(name)
    
    # If no value and no default, return None
    if value is None and default is None:
        return None
    
    # If we have a value, try to convert it
    if value is not None:
        # Determine the target type
        target_type = var_type or (type(default) if default is not None else str)
        
        # Get the appropriate converter
        converter = TYPE_CONVERTERS.get(target_type, str)
        
        try:
            return converter(value)
        except (ValueError, TypeError) as e:
            # Log the error and fall back to default
            logger.warning(
                f"Failed to convert environment variable '{name}' value '{value}' "
                f"to type {target_type.__name__}: {str(e)}. Using default value."
            )
    
    # If conversion failed or no value, return default
    return default

def get_env_var_bool(name: str, default: bool = False) -> bool:
    """
    Get boolean environment variable with validation.
    
    Specialized function for boolean values with clear semantics.
    
    Args:
        name: The name of the environment variable
        default: Default value if not set
    
    Returns:
        The boolean value of the environment variable
    
    Examples:
        >>> get_env_var_bool("DEBUG")           # Default: False
        >>> get_env_var_bool("FEATURE_FLAG", True)  # Default: True
    """
    return cast(bool, get_env_var(name, default, bool))

def get_env_var_list(name: str, default: Optional[list] = None) -> list:
    """
    Get a list from a comma-separated environment variable.
    
    Args:
        name: The name of the environment variable
        default: Default value if not set
    
    Returns:
        A list parsed from the comma-separated environment variable
    
    Examples:
        >>> get_env_var_list("ALLOWED_HOSTS")  # Returns ['localhost', '127.0.0.1'] 
                                              # for ALLOWED_HOSTS=localhost,127.0.0.1
    """
    return cast(list, get_env_var(name, default, list))

def get_env_var_int(name: str, default: int) -> int:
    """Get integer environment variable with validation."""
    return cast(int, get_env_var(name, default, int))

def get_env_var_float(name: str, default: float) -> float:
    """Get float environment variable with validation."""
    return cast(float, get_env_var(name, default, float))

# Status indication for modules that need to know if .env was loaded
def is_dotenv_loaded() -> bool:
    """Check if .env file was successfully loaded."""
    return DOTENV_LOADED
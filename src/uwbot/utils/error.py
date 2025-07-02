"""
Error handling module for the HR bot application.

This module provides a standardized approach to error handling across the application with:
1. A hierarchical error structure for different domains
2. Error codes and messages for consistent logging and reporting
3. User-friendly error messages for external communication
4. Support for localization and internationalization
"""

from enum import Enum
from typing import Dict, Any, Optional, List, Union


class ErrorSeverity(Enum):
    """Enum representing error severity levels."""
    
    INFO = "INFO"  # Informational, not critical
    WARNING = "WARNING"  # Warning, potentially problematic
    ERROR = "ERROR"  # Error, operation failed
    CRITICAL = "CRITICAL"  # Critical error, system integrity affected


class ErrorCode(Enum):
    """Enum of error codes by domain."""
    
    # General errors (1000-1999)
    UNKNOWN_ERROR = 1000
    CONFIGURATION_ERROR = 1001
    DEPENDENCY_ERROR = 1002
    INITIALIZATION_ERROR = 1003
    
    # Authentication/authorization errors (2000-2999)
    AUTH_FAILED = 2000
    UNAUTHORIZED = 2001
    TOKEN_EXPIRED = 2002
    INVALID_CREDENTIALS = 2003
    
    # Storage errors (3000-3999)
    STORAGE_UNAVAILABLE = 3000
    FILE_NOT_FOUND = 3001
    PERMISSION_DENIED = 3002
    STORAGE_FULL = 3003
    FILE_CORRUPTED = 3004
    
    # Vector store errors (4000-4999)
    EMBEDDING_FAILED = 4000
    SIMILARITY_SEARCH_FAILED = 4001
    INDEX_CORRUPTED = 4002
    VECTOR_STORE_UNAVAILABLE = 4003
    
    # LLM errors (5000-5999)
    LLM_UNAVAILABLE = 5000
    PROMPT_TOO_LONG = 5001
    RESPONSE_ERROR = 5002
    CONTENT_FILTERED = 5003
    TOKEN_LIMIT_EXCEEDED = 5004
    
    # Document processing errors (6000-6999)
    DOCUMENT_PARSE_ERROR = 6000
    UNSUPPORTED_FORMAT = 6001
    EXTRACTION_FAILED = 6002
    CHUNKING_ERROR = 6003
    
    # Teams API errors (7000-7999)
    TEAMS_API_UNAVAILABLE = 7000
    MESSAGE_DELIVERY_FAILED = 7001
    CARD_RENDERING_FAILED = 7002
    
    # RAG-specific errors (8000-8999)
    NO_RELEVANT_CONTENT = 8000
    CONTEXT_TOO_LARGE = 8001
    QUERY_PROCESSING_ERROR = 8002


class BaseError(Exception):
    """Base error class for all HR bot exceptions."""
    
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        user_message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        severity: ErrorSeverity = ErrorSeverity.ERROR,
        cause: Optional[Exception] = None,
    ):
        """
        Initialize the base error.
        
        Args:
            code: Error code enum value
            message: Technical error message
            user_message: Optional user-friendly message
            details: Optional error details dictionary
            severity: Error severity level
            cause: Optional exception that caused this error
        """
        self.code = code
        self.message = message
        self.user_message = user_message or "An unexpected error occurred."
        self.details = details or {}
        self.severity = severity
        self.cause = cause
        
        # Base exception init with technical message
        super().__init__(message)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert error to a dictionary for serialization."""
        result = {
            "code": self.code.value,
            "code_name": self.code.name,
            "message": self.message,
            "user_message": self.user_message,
            "severity": self.severity.value,
        }
        
        if self.details:
            result["details"] = self.details
            
        if self.cause:
            result["cause"] = str(self.cause)
            
        return result


# Domain-specific error classes

class ConfigError(BaseError):
    """Configuration related errors."""
    
    def __init__(
        self,
        message: str,
        user_message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        severity: ErrorSeverity = ErrorSeverity.ERROR,
        cause: Optional[Exception] = None,
    ):
        super().__init__(
            code=ErrorCode.CONFIGURATION_ERROR,
            message=message,
            user_message=user_message or "System configuration error.",
            details=details,
            severity=severity,
            cause=cause,
        )


class AuthError(BaseError):
    """Authentication and authorization errors."""
    
    def __init__(
        self,
        code: ErrorCode = ErrorCode.AUTH_FAILED,
        message: str = "Authentication failed",
        user_message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        severity: ErrorSeverity = ErrorSeverity.ERROR,
        cause: Optional[Exception] = None,
    ):
        super().__init__(
            code=code,
            message=message,
            user_message=user_message or "Authentication error.",
            details=details,
            severity=severity,
            cause=cause,
        )


class StorageError(BaseError):
    """Storage-related errors."""
    
    def __init__(
        self,
        code: ErrorCode = ErrorCode.STORAGE_UNAVAILABLE,
        message: str = "Storage operation failed",
        user_message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        severity: ErrorSeverity = ErrorSeverity.ERROR,
        cause: Optional[Exception] = None,
    ):
        super().__init__(
            code=code,
            message=message,
            user_message=user_message or "Storage system error.",
            details=details,
            severity=severity,
            cause=cause,
        )


class VectorStoreError(BaseError):
    """Vector store specific errors."""
    
    def __init__(
        self,
        code: ErrorCode = ErrorCode.VECTOR_STORE_UNAVAILABLE,
        message: str = "Vector store operation failed",
        user_message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        severity: ErrorSeverity = ErrorSeverity.ERROR,
        cause: Optional[Exception] = None,
    ):
        super().__init__(
            code=code,
            message=message,
            user_message=user_message or "Knowledge retrieval system error.",
            details=details,
            severity=severity,
            cause=cause,
        )


class LLMError(BaseError):
    """LLM-related errors."""
    
    def __init__(
        self,
        code: ErrorCode = ErrorCode.LLM_UNAVAILABLE,
        message: str = "LLM operation failed",
        user_message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        severity: ErrorSeverity = ErrorSeverity.ERROR,
        cause: Optional[Exception] = None,
    ):
        super().__init__(
            code=code,
            message=message,
            user_message=user_message or "AI processing system error.",
            details=details,
            severity=severity,
            cause=cause,
        )


class DocumentError(BaseError):
    """Document processing errors."""
    
    def __init__(
        self,
        code: ErrorCode = ErrorCode.DOCUMENT_PARSE_ERROR,
        message: str = "Document processing failed",
        user_message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        severity: ErrorSeverity = ErrorSeverity.ERROR,
        cause: Optional[Exception] = None,
    ):
        super().__init__(
            code=code,
            message=message,
            user_message=user_message or "Document processing error.",
            details=details,
            severity=severity,
            cause=cause,
        )


class TeamsError(BaseError):
    """Microsoft Teams API errors."""
    
    def __init__(
        self,
        code: ErrorCode = ErrorCode.TEAMS_API_UNAVAILABLE,
        message: str = "Teams API operation failed",
        user_message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        severity: ErrorSeverity = ErrorSeverity.ERROR,
        cause: Optional[Exception] = None,
    ):
        super().__init__(
            code=code,
            message=message,
            user_message=user_message or "Messaging system error.",
            details=details,
            severity=severity,
            cause=cause,
        )


class RAGError(BaseError):
    """RAG-specific errors."""
    
    def __init__(
        self,
        code: ErrorCode = ErrorCode.QUERY_PROCESSING_ERROR,
        message: str = "RAG operation failed",
        user_message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        severity: ErrorSeverity = ErrorSeverity.ERROR,
        cause: Optional[Exception] = None,
    ):
        super().__init__(
            code=code, 
            message=message,
            user_message=user_message or "Knowledge retrieval system error.",
            details=details,
            severity=severity,
            cause=cause,
        )


# Helper functions

def get_user_friendly_message(error: Union[BaseError, Exception]) -> str:
    """
    Get a user-friendly error message for any error.
    
    Args:
        error: Any exception
        
    Returns:
        User-friendly error message
    """
    if isinstance(error, BaseError):
        return error.user_message
    
    # Generic message for unknown errors
    return "An unexpected error occurred. Please try again later." 
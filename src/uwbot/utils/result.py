"""
Result type for error handling across the application.

This module provides a functional approach to error handling with:
1. A Result type that can contain either a success value or an error
2. Helper types for Success and Error cases
3. Utility methods for working with Results

This approach enables more predictable error handling and cleaner code.
"""

from typing import TypeVar, Generic, Any, Optional, Callable, Union, List


T = TypeVar('T')  # Success type
E = TypeVar('E')  # Error type


class Result(Generic[T]):
    """
    A Result type that can contain either a success value or an error.
    
    This enables a functional approach to error handling without exceptions.
    """
    
    def __init__(self, value: T = None, error: Any = None):
        """
        Initialize a Result.
        
        Args:
            value: The success value (if successful)
            error: The error value (if failed)
        """
        self._value = value
        self._error = error
        self._is_success = error is None
    
    @property
    def value(self) -> Optional[T]:
        """Get the success value (if any)."""
        return self._value if self._is_success else None
    
    @property
    def error(self) -> Any:
        """Get the error (if any)."""
        return self._error if not self._is_success else None
    
    def is_success(self) -> bool:
        """Check if this Result is a success."""
        return self._is_success
    
    def is_error(self) -> bool:
        """Check if this Result is an error."""
        return not self._is_success
    
    def unwrap(self) -> T:
        """
        Unwrap the success value.
        
        Raises:
            ValueError: If this Result is an error
        """
        if self._is_success:
            return self._value
        else:
            raise ValueError(f"Cannot unwrap error result: {self._error}")
    
    def unwrap_or(self, default: T) -> T:
        """
        Unwrap the success value or return a default.
        
        Args:
            default: Default value to return if this is an error
            
        Returns:
            The success value or the default
        """
        return self._value if self._is_success else default
    
    def map(self, fn: Callable[[T], E]) -> 'Result[E]':
        """
        Map a function over the success value.
        
        Args:
            fn: Function to apply to the success value
            
        Returns:
            A new Result with the mapped value or the original error
        """
        if self._is_success:
            return Result(value=fn(self._value))
        else:
            return Result(error=self._error)
    
    def flat_map(self, fn: Callable[[T], 'Result[E]']) -> 'Result[E]':
        """
        Apply a function that returns a Result to the success value.
        
        Args:
            fn: Function that returns a Result
            
        Returns:
            The Result returned by the function or the original error
        """
        if self._is_success:
            return fn(self._value)
        else:
            return Result(error=self._error)


def Success(value: T) -> Result[T]:
    """
    Create a successful Result.
    
    Args:
        value: The success value
        
    Returns:
        A successful Result
    """
    return Result(value=value)


def Error(error: Any) -> Result:
    """
    Create an error Result.
    
    Args:
        error: The error value
        
    Returns:
        An error Result
    """
    return Result(error=error)


def collect_results(results: List[Result[T]]) -> Result[List[T]]:
    """
    Collect a list of Results into a single Result containing a list of values.
    
    If any Result is an error, returns the first error encountered.
    
    Args:
        results: List of Results
        
    Returns:
        A Result containing a list of success values, or the first error
    """
    values = []
    for result in results:
        if result.is_error():
            return Error(result.error)
        values.append(result.unwrap())
    return Success(values) 
"""
Timing utilities for performance monitoring and response time tracking.

This module provides:
1. Context managers for timing operations
2. Decorators for timing functions
3. Performance tracking across different services
4. Detailed timing reports
"""

import time
import logging
import asyncio
from contextlib import asynccontextmanager, contextmanager
from functools import wraps
from typing import Dict, Any, Optional, Callable, Union
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import statistics

logger = logging.getLogger(__name__)


class TimingLevel(Enum):
    """Enum for timing detail levels."""
    BASIC = "basic"
    DETAILED = "detailed"
    VERBOSE = "verbose"


@dataclass
class TimingResult:
    """Result of a timing operation."""
    service_name: str
    operation_name: str
    duration_seconds: float
    start_time: datetime
    end_time: datetime
    success: bool = True
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def duration_ms(self) -> float:
        """Duration in milliseconds."""
        return self.duration_seconds * 1000
    
    @property
    def duration_formatted(self) -> str:
        """Human-readable duration."""
        if self.duration_seconds < 1:
            return f"{self.duration_ms:.1f}ms"
        elif self.duration_seconds < 60:
            return f"{self.duration_seconds:.2f}s"
        else:
            minutes = int(self.duration_seconds // 60)
            seconds = self.duration_seconds % 60
            return f"{minutes}m {seconds:.1f}s"


class PerformanceTracker:
    """Tracks performance metrics across different services and operations."""
    
    def __init__(self):
        self.timings: Dict[str, list[TimingResult]] = {}
        self.active_timings: Dict[str, TimingResult] = {}
        self.enabled = True
        self.log_level = TimingLevel.DETAILED
    
    def start_timing(self, service_name: str, operation_name: str, **metadata) -> str:
        """
        Start timing an operation.
        
        Args:
            service_name: Name of the service (e.g., 'database', 'llm', 'teams')
            operation_name: Name of the operation (e.g., 'query', 'generate', 'send_message')
            **metadata: Additional metadata to track
            
        Returns:
            Timing ID for tracking
        """
        if not self.enabled:
            return "disabled"
        
        timing_id = f"{service_name}_{operation_name}_{int(time.time() * 1000)}"
        
        timing = TimingResult(
            service_name=service_name,
            operation_name=operation_name,
            duration_seconds=0.0,
            start_time=datetime.utcnow(),
            end_time=datetime.utcnow(),
            metadata=metadata
        )
        
        self.active_timings[timing_id] = timing
        
        if self.log_level == TimingLevel.VERBOSE:
            logger.debug(f"Started timing: {service_name}.{operation_name} (ID: {timing_id})")
        
        return timing_id
    
    def end_timing(self, timing_id: str, success: bool = True, error: Optional[str] = None) -> Optional[TimingResult]:
        """
        End timing an operation.
        
        Args:
            timing_id: The timing ID returned from start_timing
            success: Whether the operation was successful
            error: Error message if operation failed
            
        Returns:
            TimingResult if successful, None if timing ID not found
        """
        if timing_id == "disabled" or not self.enabled:
            return None
        
        if timing_id not in self.active_timings:
            logger.warning(f"Timing ID not found: {timing_id}")
            return None
        
        timing = self.active_timings[timing_id]
        timing.end_time = datetime.utcnow()
        timing.duration_seconds = (timing.end_time - timing.start_time).total_seconds()
        timing.success = success
        timing.error = error
        
        # Store in service-specific list
        service_key = timing.service_name
        if service_key not in self.timings:
            self.timings[service_key] = []
        self.timings[service_key].append(timing)
        
        # Remove from active timings
        del self.active_timings[timing_id]
        
        # Log based on level
        if self.log_level == TimingLevel.VERBOSE:
            logger.debug(f"Completed timing: {timing.service_name}.{timing.operation_name} "
                        f"in {timing.duration_formatted} (success: {success})")
        elif self.log_level == TimingLevel.DETAILED and timing.duration_seconds > 1.0:
            logger.info(f"Slow operation: {timing.service_name}.{timing.operation_name} "
                       f"took {timing.duration_formatted}")
        
        return timing
    
    def get_service_stats(self, service_name: str) -> Dict[str, Any]:
        """
        Get performance statistics for a specific service.
        
        Args:
            service_name: Name of the service
            
        Returns:
            Dictionary with performance statistics
        """
        if service_name not in self.timings:
            return {
                "service": service_name,
                "total_operations": 0,
                "average_duration": 0.0,
                "min_duration": 0.0,
                "max_duration": 0.0,
                "success_rate": 0.0
            }
        
        timings = self.timings[service_name]
        if not timings:
            return {
                "service": service_name,
                "total_operations": 0,
                "average_duration": 0.0,
                "min_duration": 0.0,
                "max_duration": 0.0,
                "success_rate": 0.0
            }
        
        durations = [t.duration_seconds for t in timings]
        successful = [t for t in timings if t.success]
        
        return {
            "service": service_name,
            "total_operations": len(timings),
            "average_duration": statistics.mean(durations),
            "median_duration": statistics.median(durations),
            "min_duration": min(durations),
            "max_duration": max(durations),
            "success_rate": len(successful) / len(timings) * 100,
            "recent_operations": [
                {
                    "operation": t.operation_name,
                    "duration": t.duration_formatted,
                    "success": t.success,
                    "timestamp": t.start_time.isoformat()
                }
                for t in timings[-10:]  # Last 10 operations
            ]
        }
    
    def get_overall_stats(self) -> Dict[str, Any]:
        """
        Get overall performance statistics across all services.
        
        Returns:
            Dictionary with overall performance statistics
        """
        all_timings = []
        for service_timings in self.timings.values():
            all_timings.extend(service_timings)
        
        if not all_timings:
            return {
                "total_operations": 0,
                "average_duration": 0.0,
                "services": {}
            }
        
        durations = [t.duration_seconds for t in all_timings]
        successful = [t for t in all_timings if t.success]
        
        # Get stats per service
        service_stats = {}
        for service_name in self.timings.keys():
            service_stats[service_name] = self.get_service_stats(service_name)
        
        return {
            "total_operations": len(all_timings),
            "average_duration": statistics.mean(durations),
            "median_duration": statistics.median(durations),
            "min_duration": min(durations),
            "max_duration": max(durations),
            "success_rate": len(successful) / len(all_timings) * 100,
            "services": service_stats,
            "active_timings": len(self.active_timings)
        }
    
    def clear_stats(self, service_name: Optional[str] = None):
        """
        Clear timing statistics.
        
        Args:
            service_name: If provided, clear only this service's stats
        """
        if service_name:
            self.timings.pop(service_name, None)
        else:
            self.timings.clear()
            self.active_timings.clear()


# Global performance tracker instance
performance_tracker = PerformanceTracker()


@contextmanager
def time_operation(service_name: str, operation_name: str, **metadata):
    """
    Context manager for timing operations.
    
    Args:
        service_name: Name of the service
        operation_name: Name of the operation
        **metadata: Additional metadata to track
        
    Yields:
        Timing ID for manual control if needed
    """
    timing_id = performance_tracker.start_timing(service_name, operation_name, **metadata)
    try:
        yield timing_id
        performance_tracker.end_timing(timing_id, success=True)
    except Exception as e:
        performance_tracker.end_timing(timing_id, success=False, error=str(e))
        raise


@asynccontextmanager
async def time_async_operation(service_name: str, operation_name: str, **metadata):
    """
    Async context manager for timing async operations.
    
    Args:
        service_name: Name of the service
        operation_name: Name of the operation
        **metadata: Additional metadata to track
        
    Yields:
        Timing ID for manual control if needed
    """
    timing_id = performance_tracker.start_timing(service_name, operation_name, **metadata)
    try:
        yield timing_id
        performance_tracker.end_timing(timing_id, success=True)
    except Exception as e:
        performance_tracker.end_timing(timing_id, success=False, error=str(e))
        raise


def time_function(service_name: str, operation_name: Optional[str] = None):
    """
    Decorator for timing functions.
    
    Args:
        service_name: Name of the service
        operation_name: Name of the operation (defaults to function name)
        
    Returns:
        Decorated function
    """
    def decorator(func):
        op_name = operation_name or func.__name__
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            with time_operation(service_name, op_name):
                return func(*args, **kwargs)
        
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            async with time_async_operation(service_name, op_name):
                return await func(*args, **kwargs)
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


def get_performance_report(service_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Get a performance report.
    
    Args:
        service_name: If provided, get report for specific service only
        
    Returns:
        Performance report dictionary
    """
    if service_name:
        return performance_tracker.get_service_stats(service_name)
    else:
        return performance_tracker.get_overall_stats()


def enable_timing(enabled: bool = True):
    """Enable or disable timing globally."""
    performance_tracker.enabled = enabled


def set_timing_level(level: TimingLevel):
    """Set the timing detail level."""
    performance_tracker.log_level = level


# Convenience functions for common services
def time_database_operation(operation_name: str):
    """Decorator for timing database operations."""
    return time_function("database", operation_name)


def time_llm_operation(operation_name: str):
    """Decorator for timing LLM operations."""
    return time_function("llm", operation_name)


def time_teams_operation(operation_name: str):
    """Decorator for timing Teams API operations."""
    return time_function("teams", operation_name)


def time_validation_operation(operation_name: str):
    """Decorator for timing validation operations."""
    return time_function("validation", operation_name)


def time_feedback_operation(operation_name: str):
    """Decorator for timing feedback operations."""
    return time_function("feedback", operation_name) 
"""
utils.py — Production utilities for structured logging, retry logic, and security.

Features:
  - Structured JSON logging
  - Exponential backoff retry decorator
  - Request ID correlation
  - Sensitive data masking
"""

import asyncio
import functools
import json
import logging
import time
import uuid
from typing import Any, Callable, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class StructuredLogger:
    """
    Wrapper around Python logging that outputs structured JSON for production.
    
    Enables easier parsing, searching, and alerting in centralized logging systems
    (ELK, CloudWatch, Datadog, etc.).
    """

    def __init__(self, name: str):
        self.logger = logging.getLogger(name)

    def _mask_sensitive(self, data: dict[str, Any]) -> dict[str, Any]:
        """Mask API keys and sensitive data from logs."""
        masked = data.copy()
        sensitive_keys = ["api_key", "key", "secret", "token", "password"]
        
        for key in list(masked.keys()):
            if any(s in key.lower() for s in sensitive_keys):
                masked[key] = "***MASKED***"
        
        return masked

    def info(
        self,
        message: str,
        request_id: Optional[str] = None,
        **context: Any,
    ) -> None:
        """Log info with structured context."""
        log_entry = {
            "level": "INFO",
            "message": message,
            "request_id": request_id,
            "timestamp": time.time(),
            **self._mask_sensitive(context),
        }
        self.logger.info(json.dumps(log_entry))

    def warning(
        self,
        message: str,
        request_id: Optional[str] = None,
        **context: Any,
    ) -> None:
        """Log warning with structured context."""
        log_entry = {
            "level": "WARNING",
            "message": message,
            "request_id": request_id,
            "timestamp": time.time(),
            **self._mask_sensitive(context),
        }
        self.logger.warning(json.dumps(log_entry))

    def error(
        self,
        message: str,
        request_id: Optional[str] = None,
        **context: Any,
    ) -> None:
        """Log error with structured context."""
        log_entry = {
            "level": "ERROR",
            "message": message,
            "request_id": request_id,
            "timestamp": time.time(),
            **self._mask_sensitive(context),
        }
        self.logger.error(json.dumps(log_entry))


def retry_with_backoff(
    max_retries: int = 3,
    base_backoff_ms: int = 100,
    exponential_base: float = 2.0,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator: Retry a function with exponential backoff.
    
    Usage:
        @retry_with_backoff(max_retries=3, base_backoff_ms=100)
        def call_api():
            ...
    
    Args:
        max_retries: Number of retry attempts
        base_backoff_ms: Initial backoff in milliseconds
        exponential_base: Multiplier for each retry (e.g., 2.0 = exponential)
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> T:
                last_exception = None
                for attempt in range(max_retries):
                    try:
                        return await func(*args, **kwargs)
                    except Exception as exc:
                        last_exception = exc
                        if attempt < max_retries - 1:
                            backoff_ms = base_backoff_ms * (exponential_base ** attempt)
                            backoff_sec = backoff_ms / 1000.0
                            logger.warning(
                                "Retry attempt %d/%d after %.2fs (error: %s)",
                                attempt + 1,
                                max_retries,
                                backoff_sec,
                                str(exc),
                            )
                            await asyncio.sleep(backoff_sec)
                        else:
                            logger.error(
                                "All %d retry attempts exhausted for %s",
                                max_retries,
                                func.__name__,
                            )
                raise last_exception

            return async_wrapper

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception = None
            
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:
                    last_exception = exc
                    
                    if attempt < max_retries - 1:
                        backoff_ms = base_backoff_ms * (exponential_base ** attempt)
                        backoff_sec = backoff_ms / 1000.0
                        logger.warning(
                            "Retry attempt %d/%d after %.2fs (error: %s)",
                            attempt + 1,
                            max_retries,
                            backoff_sec,
                            str(exc),
                        )
                        time.sleep(backoff_sec)
                    else:
                        logger.error(
                            "All %d retry attempts exhausted for %s",
                            max_retries,
                            func.__name__,
                        )
            
            raise last_exception

        return wrapper

    return decorator


def generate_request_id() -> str:
    """Generate a short unique request ID for correlation."""
    return str(uuid.uuid4())[:8]


def sanitize_input(text: str, max_length: int = 4000) -> str:
    """
    Sanitize user input: strip whitespace, enforce length limits, check for injection.
    
    Args:
        text: User input to sanitize
        max_length: Maximum allowed length
    
    Returns:
        Cleaned text
    
    Raises:
        ValueError: If input is invalid
    """
    if not isinstance(text, str):
        raise ValueError("Input must be a string")
    
    text = text.strip()
    
    if not text:
        raise ValueError("Input cannot be empty")
    
    if len(text) > max_length:
        raise ValueError(f"Input exceeds maximum length of {max_length} characters")
    
    # Check for null bytes and other control characters
    if "\x00" in text or "\x1b" in text:
        raise ValueError("Input contains invalid control characters")
    
    return text


def format_api_error_response(
    code: str,
    message: str,
    request_id: Optional[str] = None,
) -> dict[str, Any]:
    """
    Format standard Stage 1.2 API error payload:
    {
        "error": {
            "code": code,
            "message": message,
            "request_id": request_id
        }
    }
    """
    return {
        "error": {
            "code": code,
            "message": message,
            "request_id": request_id or generate_request_id(),
        }
    }


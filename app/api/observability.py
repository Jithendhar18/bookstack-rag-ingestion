"""Observability and monitoring utilities."""

import asyncio
import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Any, Callable, Optional

from app.config.logging import get_logger

logger = get_logger(__name__)

_MAX_METRIC_NAMES = 500
_REQUEST_STALE_SECONDS = 300


class PerformanceMetrics:
    """Track performance metrics."""

    def __init__(self):
        """Initialize metrics tracker."""
        self.metrics: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def record(self, name: str, duration_ms: float, success: bool = True, **kwargs) -> None:
        """Record a metric.

        Args:
            name: Metric name
            duration_ms: Duration in milliseconds
            success: Whether the operation succeeded
            **kwargs: Additional metadata
        """
        with self._lock:
            if name not in self.metrics:
                if len(self.metrics) >= _MAX_METRIC_NAMES:
                    oldest = next(iter(self.metrics))
                    del self.metrics[oldest]
                self.metrics[name] = {
                    "count": 0,
                    "total_time": 0,
                    "min_time": float("inf"),
                    "max_time": 0,
                    "errors": 0,
                }

            self.metrics[name]["count"] += 1
            self.metrics[name]["total_time"] += duration_ms
            self.metrics[name]["min_time"] = min(self.metrics[name]["min_time"], duration_ms)
            self.metrics[name]["max_time"] = max(self.metrics[name]["max_time"], duration_ms)

            if not success:
                self.metrics[name]["errors"] += 1

        logger.info(
            "metric.recorded",
            metric_name=name,
            duration_ms=round(duration_ms, 2),
            success=success,
            **kwargs,
        )

    def get_stats(self, name: Optional[str] = None) -> dict[str, Any]:
        """Get metric statistics.

        Args:
            name: Optional metric name (None for all)

        Returns:
            Dictionary with statistics
        """
        with self._lock:
            if name:
                if name not in self.metrics:
                    return {}
                m = self.metrics[name]
                return {
                    "name": name,
                    "count": m["count"],
                    "avg_time": m["total_time"] / m["count"] if m["count"] > 0 else 0,
                    "min_time": m["min_time"],
                    "max_time": m["max_time"],
                    "total_time": m["total_time"],
                    "errors": m["errors"],
                    "error_rate": m["errors"] / m["count"] if m["count"] > 0 else 0,
                }

            return {
                name: {
                    "count": m["count"],
                    "avg_time": m["total_time"] / m["count"] if m["count"] > 0 else 0,
                    "min_time": m["min_time"],
                    "max_time": m["max_time"],
                    "total_time": m["total_time"],
                    "errors": m["errors"],
                }
                for name, m in self.metrics.items()
            }

    def reset(self) -> None:
        """Reset all metrics."""
        with self._lock:
            self.metrics.clear()


# Global metrics instance
_metrics = PerformanceMetrics()


def get_metrics() -> PerformanceMetrics:
    """Get global metrics instance."""
    return _metrics


def timed_operation(name: str, log_level: int = logging.INFO):
    """Decorator to time and log an operation.

    Args:
        name: Operation name
        log_level: Logging level

    Returns:
        Decorator function
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                duration_ms = (time.time() - start_time) * 1000
                _metrics.record(name, duration_ms, success=True)
                logger.log(
                    log_level,
                    "operation.completed",
                    operation=name,
                    duration_ms=round(duration_ms, 2),
                )
                return result
            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000
                _metrics.record(name, duration_ms, success=False)
                logger.error(
                    "operation.failed",
                    operation=name,
                    duration_ms=round(duration_ms, 2),
                    error=str(e),
                )
                raise

        @wraps(func)
        def sync_wrapper(*args, **kwargs) -> Any:
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                duration_ms = (time.time() - start_time) * 1000
                _metrics.record(name, duration_ms, success=True)
                logger.log(
                    log_level,
                    "operation.completed",
                    operation=name,
                    duration_ms=round(duration_ms, 2),
                )
                return result
            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000
                _metrics.record(name, duration_ms, success=False)
                logger.error(
                    "operation.failed",
                    operation=name,
                    duration_ms=round(duration_ms, 2),
                    error=str(e),
                )
                raise

        # Return async or sync wrapper based on whether func is async
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


class RequestLogger:
    """Log and track requests."""

    def __init__(self):
        """Initialize request logger."""
        self.requests: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def start_request(self, request_id: str, **metadata) -> None:
        """Log start of a request.

        Args:
            request_id: Request ID
            **metadata: Request metadata
        """
        now = datetime.now(timezone.utc)
        with self._lock:
            # Evict stale entries to prevent memory leaks from orphaned requests
            stale_cutoff = now - timedelta(seconds=_REQUEST_STALE_SECONDS)
            stale_keys = [k for k, v in self.requests.items() if v["start_time"] < stale_cutoff]
            for k in stale_keys:
                del self.requests[k]

            self.requests[request_id] = {
                "start_time": now,
                "metadata": metadata,
            }

    def end_request(self, request_id: str, status: str = "success", **metadata) -> dict[str, Any]:
        """Log end of a request.

        Args:
            request_id: Request ID
            status: Status (success, error, timeout, etc.)
            **metadata: Additional metadata

        Returns:
            Request log entry
        """
        if request_id not in self.requests:
            logger.warning("request.not_found", request_id=request_id)
            return {}

        with self._lock:
            req = self.requests.pop(request_id, None)
        if req is None:
            return {}
        duration = datetime.now(timezone.utc) - req["start_time"]
        duration_ms = duration.total_seconds() * 1000

        log_entry = {
            "request_id": request_id,
            "status": status,
            "duration_ms": duration_ms,
            "metadata": {**req["metadata"], **metadata},
        }

        logger.info(
            "request.completed",
            request_id=request_id,
            status=status,
            duration_ms=round(duration_ms, 2),
        )

        return log_entry


# Global request logger
_request_logger = RequestLogger()


def get_request_logger() -> RequestLogger:
    """Get global request logger."""
    return _request_logger

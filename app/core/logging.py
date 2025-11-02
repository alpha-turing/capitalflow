import structlog
import logging
import sys
from typing import Any, Dict
from datetime import datetime

from app.core.config import settings


class StructlogFormatter(logging.Formatter):
    """Custom formatter for structured logging"""
    
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # Add extra fields from the record
        for key, value in record.__dict__.items():
            if key not in ["name", "msg", "args", "levelname", "levelno", "pathname",
                          "filename", "module", "lineno", "funcName", "created",
                          "msecs", "relativeCreated", "thread", "threadName",
                          "processName", "process", "message"]:
                log_data[key] = value
        
        if settings.LOG_FORMAT == "json":
            import json
            return json.dumps(log_data)
        else:
            return f"{log_data['timestamp']} - {log_data['level']} - {log_data['message']}"


def setup_logging() -> None:
    """Setup structured logging configuration"""
    
    # Configure standard library logging
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL.upper()),
        format="%(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    
    # Configure structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.JSONRenderer() if settings.LOG_FORMAT == "json" 
            else structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.LOG_LEVEL.upper())
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    # Set up Sentry if configured
    if settings.SENTRY_DSN:
        import sentry_sdk
        from sentry_sdk.integrations.logging import LoggingIntegration
        
        sentry_logging = LoggingIntegration(
            level=logging.INFO,
            event_level=logging.ERROR
        )
        
        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            integrations=[sentry_logging],
            traces_sample_rate=0.1,
            environment=settings.ENVIRONMENT,
        )


def get_logger(name: str = None) -> Any:
    """Get a structured logger instance"""
    return structlog.get_logger(name)
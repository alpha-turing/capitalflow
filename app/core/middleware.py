from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Callable
import time
import structlog
import uuid

from app.core.config import settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses"""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        
        # Add security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        return response


class AuditLogMiddleware(BaseHTTPMiddleware):
    """Log all API requests for audit purposes"""
    
    def __init__(self, app):
        super().__init__(app)
        self.logger = structlog.get_logger("audit")
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Generate request ID
        request_id = str(uuid.uuid4())
        
        # Log request
        start_time = time.time()
        
        self.logger.info(
            "Request started",
            request_id=request_id,
            method=request.method,
            url=str(request.url),
            client_ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        
        try:
            response = await call_next(request)
            
            # Log response
            process_time = time.time() - start_time
            self.logger.info(
                "Request completed",
                request_id=request_id,
                status_code=response.status_code,
                process_time=round(process_time, 4),
            )
            
            response.headers["X-Request-ID"] = request_id
            return response
            
        except Exception as e:
            # Log error
            process_time = time.time() - start_time
            self.logger.error(
                "Request failed",
                request_id=request_id,
                error=str(e),
                process_time=round(process_time, 4),
                exc_info=True,
            )
            raise
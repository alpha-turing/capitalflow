from typing import List, Optional, Dict, Any, Generic, TypeVar
from pydantic import BaseModel, Field
from datetime import datetime

T = TypeVar('T')

class BaseResponse(BaseModel):
    """Base response model"""
    success: bool = True
    message: Optional[str] = None


class ErrorResponse(BaseModel):
    """Error response model"""
    success: bool = False
    error: str
    detail: Optional[str] = None


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated response model"""
    items: List[T]
    total: int
    page: int = 1
    per_page: int = 50
    pages: int = 1
    
    class Config:
        arbitrary_types_allowed = True


class HealthCheckResponse(BaseModel):
    """Health check response"""
    status: str
    version: str
    timestamp: datetime = Field(default_factory=datetime.now)
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from jose import JWTError, jwt
import structlog

from app.core.config import settings
from app.core.database import get_db
from app.db.models import User


security = HTTPBearer()
logger = structlog.get_logger("dependencies")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> User:
    """Get current authenticated user from JWT token"""
    
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        logger.info(f"Attempting to decode JWT token: {credentials.credentials[:50]}...")
        payload = jwt.decode(credentials.credentials, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        email: Optional[str] = payload.get("sub")
        logger.info(f"JWT payload decoded successfully, email: {email}")
        if email is None:
            logger.error("No email found in JWT payload")
            raise credentials_exception
    except JWTError as e:
        logger.error(f"JWT decoding failed: {str(e)}")
        raise credentials_exception
    
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    
    if user is None:
        raise credentials_exception
    
    return user
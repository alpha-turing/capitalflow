from fastapi import APIRouter, HTTPException, status
import structlog


router = APIRouter()
logger = structlog.get_logger("transactions_api")


@router.get("/")
async def get_transactions():
    """Get transactions endpoint - placeholder"""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Transactions API not implemented in MVP"
    )
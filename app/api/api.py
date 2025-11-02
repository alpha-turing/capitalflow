from fastapi import APIRouter
from app.api.v1.endpoints import (
    portfolios, 
    auth, 
    uploads, 
    transactions,
    dashboard,
    reports,
    corporate_actions
)

# Create API v1 router
api_router = APIRouter()

# Include all endpoint routers
api_router.include_router(auth.router, prefix="/auth", tags=["authentication"])
api_router.include_router(portfolios.router, prefix="/portfolios", tags=["portfolios"])
api_router.include_router(uploads.router, prefix="/uploads", tags=["uploads"])
api_router.include_router(transactions.router, prefix="/transactions", tags=["transactions"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(reports.router, prefix="/reports", tags=["reports"])
api_router.include_router(corporate_actions.router, prefix="/corporate-actions", tags=["corporate-actions"])
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import structlog

from app.core.database import get_db
from app.api.dependencies import get_current_user
from app.portfolio.service import portfolio_service
from app.db.models import User, Portfolio


router = APIRouter()
logger = structlog.get_logger("dashboard_api")


@router.get("/")
async def get_dashboard_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get user dashboard summary"""
    
    try:
        # Get all user portfolios using SQLAlchemy ORM
        from sqlalchemy.orm import selectinload
        from sqlalchemy import select
        
        portfolios_stmt = select(Portfolio).where(Portfolio.user_id == current_user.id)
        portfolios_result = await db.execute(portfolios_stmt)
        portfolios = portfolios_result.scalars().all()
        
        dashboard_data = {
            "user_id": current_user.id,
            "total_portfolios": 0,
            "total_net_worth": 0.0,
            "total_invested": 0.0,
            "total_unrealized_pnl": 0.0,
            "portfolios": []
        }
        
        total_net_worth = 0.0
        total_invested = 0.0
        total_unrealized_pnl = 0.0
        
        for portfolio in portfolios:
            try:
                summary = await portfolio_service.get_portfolio_summary(
                    db, portfolio.id
                )
                
                portfolio_data = {
                    "id": portfolio.id,
                    "name": portfolio.name,
                    "current_value": summary.get('current_value', 0.0),
                    "total_invested": summary.get('total_invested', 0.0),
                    "unrealized_pnl": summary.get('unrealized_pnl', 0.0),
                    "unrealized_pnl_percentage": summary.get('unrealized_pnl_percentage', 0.0),
                    "position_count": summary.get('total_positions', 0)
                }
                
                dashboard_data["portfolios"].append(portfolio_data)
                
                total_net_worth += portfolio_data["current_value"]
                total_invested += portfolio_data["total_invested"]
                total_unrealized_pnl += portfolio_data["unrealized_pnl"]
                
            except Exception as e:
                logger.error("Error getting portfolio summary", portfolio_id=portfolio.id, error=str(e))
                continue
        
        dashboard_data.update({
            "total_portfolios": len(dashboard_data["portfolios"]),
            "total_net_worth": total_net_worth,
            "total_invested": total_invested,
            "total_unrealized_pnl": total_unrealized_pnl,
            "total_unrealized_pnl_percentage": (total_unrealized_pnl / total_invested * 100) if total_invested > 0 else 0.0
        })
        
        logger.info("Retrieved dashboard summary", user_id=current_user.id)
        return dashboard_data
        
    except Exception as e:
        logger.error("Error retrieving dashboard", user_id=current_user.id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving dashboard data"
        )
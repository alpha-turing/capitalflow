from typing import List, Optional, Dict, Any
from datetime import datetime
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import structlog

from app.core.database import get_db
from app.portfolio.service import portfolio_service
from app.api.v1.schemas.portfolio import (
    PortfolioResponse,
    PortfolioSummaryResponse,
    PositionResponse,
    PerformanceResponse
)
from app.api.v1.schemas.common import PaginatedResponse
from app.api.dependencies import get_current_user
from app.db.models import User, Portfolio


router = APIRouter()
logger = structlog.get_logger("portfolio_api")


@router.get("/", response_model=List[PortfolioResponse])
async def get_user_portfolios(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> List[PortfolioResponse]:
    """Get all portfolios for the current user"""
    
    try:
        portfolios = await db.execute(
            text("SELECT * FROM portfolios WHERE user_id = :user_id ORDER BY created_at"),
            {"user_id": current_user.id}
        )
        
        portfolio_list = []
        for portfolio in portfolios.fetchall():
            # Get basic summary for each portfolio
            summary = await portfolio_service.get_portfolio_summary(
                db, portfolio.id
            )
            
            portfolio_response = PortfolioResponse(
                id=portfolio.id,
                name=portfolio.name,
                description=portfolio.description,
                base_currency=portfolio.base_currency,
                is_default=portfolio.is_default,
                total_value=summary.get('current_value', 0.0),
                unrealized_pnl=summary.get('unrealized_pnl', 0.0),
                position_count=summary.get('total_positions', 0),
                last_updated=summary.get('valuation_date')
            )
            
            portfolio_list.append(portfolio_response)
        
        logger.info("Retrieved user portfolios", user_id=current_user.id, count=len(portfolio_list))
        return portfolio_list
        
    except Exception as e:
        logger.error("Error retrieving portfolios", user_id=current_user.id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving portfolios"
        )


@router.get("/{portfolio_id}", response_model=PortfolioSummaryResponse)
async def get_portfolio_summary(
    portfolio_id: str,
    valuation_date: Optional[datetime] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> PortfolioSummaryResponse:
    """Get detailed portfolio summary"""
    
    try:
        # Verify portfolio ownership
        portfolio = await db.get(Portfolio, portfolio_id)
        if not portfolio or portfolio.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Portfolio not found"
            )
        
        # Get comprehensive summary
        summary = await portfolio_service.get_portfolio_summary(
            db, portfolio_id, valuation_date
        )
        
        response = PortfolioSummaryResponse(
            id=portfolio_id,
            name=summary['portfolio_name'],
            description=portfolio.description,
            base_currency=summary['base_currency'],
            valuation_date=summary['valuation_date'],
            
            # Financial metrics
            total_invested=summary['total_invested'],
            current_value=summary['current_value'],
            unrealized_pnl=summary['unrealized_pnl'],
            unrealized_pnl_percentage=summary['unrealized_pnl_percentage'],
            
            # Performance metrics
            xirr_annualized=summary.get('xirr_annualized'),
            total_return_percentage=summary['total_return_percentage'],
            days_invested=summary['days_invested'],
            
            # Holdings
            position_count=summary['total_positions'],
            positions=[
                PositionResponse(**position) 
                for position in summary['positions']
            ],
            
            # Allocations
            asset_allocation=summary['asset_allocation'],
            currency_allocation=summary['currency_allocation']
        )
        
        logger.info("Retrieved portfolio summary", portfolio_id=portfolio_id)
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error retrieving portfolio summary", portfolio_id=portfolio_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving portfolio summary"
        )


@router.get("/{portfolio_id}/positions", response_model=List[PositionResponse])
async def get_portfolio_positions(
    portfolio_id: str,
    valuation_date: Optional[datetime] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> List[PositionResponse]:
    """Get all positions for a portfolio"""
    
    try:
        # Verify portfolio ownership
        portfolio = await db.get(Portfolio, portfolio_id)
        if not portfolio or portfolio.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Portfolio not found"
            )
        
        # Calculate positions
        positions = await portfolio_service.calculate_portfolio_positions(
            db, portfolio_id, valuation_date
        )
        
        position_responses = []
        for position in positions:
            response = PositionResponse(
                instrument_id=position.instrument_id,
                instrument_name=position.instrument_name,
                quantity=float(position.quantity),
                average_cost=float(position.average_cost),
                total_cost=float(position.total_cost),
                current_price=float(position.current_price) if position.current_price else None,
                market_value=float(position.market_value) if position.market_value else None,
                unrealized_pnl=float(position.unrealized_pnl) if position.unrealized_pnl else None,
                unrealized_pnl_percentage=float(position.unrealized_pnl / position.total_cost * 100) if position.unrealized_pnl and position.total_cost > 0 else 0.0,
                currency=position.currency.value,
                tax_lots_count=len(position.tax_lots) if position.tax_lots else 0
            )
            position_responses.append(response)
        
        logger.info("Retrieved portfolio positions", portfolio_id=portfolio_id, count=len(position_responses))
        return position_responses
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error retrieving positions", portfolio_id=portfolio_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving positions"
        )


@router.get("/{portfolio_id}/performance", response_model=PerformanceResponse)
async def get_portfolio_performance(
    portfolio_id: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> PerformanceResponse:
    """Get portfolio performance metrics"""
    
    try:
        # Verify portfolio ownership
        portfolio = await db.get(Portfolio, portfolio_id)
        if not portfolio or portfolio.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Portfolio not found"
            )
        
        # Calculate performance metrics
        performance = await portfolio_service.calculate_portfolio_performance(
            db, portfolio_id, start_date, end_date
        )
        
        response = PerformanceResponse(
            portfolio_id=portfolio_id,
            
            # Time-weighted return
            twr_annualized=float(performance.twr_annualized) if performance.twr_annualized else None,
            twr_total=float(performance.twr_total) if performance.twr_total else None,
            
            # Money-weighted return
            xirr_annualized=float(performance.xirr_annualized) if performance.xirr_annualized else None,
            
            # Simple metrics
            total_invested=float(performance.total_invested),
            current_value=float(performance.current_value),
            total_return=float(performance.total_return),
            total_return_percentage=float(performance.total_return_percentage),
            
            # Time period
            start_date=performance.start_date.isoformat() if performance.start_date else None,
            end_date=performance.end_date.isoformat() if performance.end_date else None,
            days_invested=performance.days_invested,
            
            # Risk metrics
            volatility=float(performance.volatility) if performance.volatility else None,
            sharpe_ratio=float(performance.sharpe_ratio) if performance.sharpe_ratio else None,
            max_drawdown=float(performance.max_drawdown) if performance.max_drawdown else None
        )
        
        logger.info("Retrieved portfolio performance", portfolio_id=portfolio_id)
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error retrieving performance", portfolio_id=portfolio_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving performance metrics"
        )


@router.post("/{portfolio_id}/refresh")
async def refresh_portfolio_positions(
    portfolio_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """Refresh portfolio position calculations"""
    
    try:
        # Verify portfolio ownership
        portfolio = await db.get(Portfolio, portfolio_id)
        if not portfolio or portfolio.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Portfolio not found"
            )
        
        # Refresh positions
        updated_count = await portfolio_service.update_portfolio_positions(
            db, portfolio_id, force_refresh=True
        )
        
        logger.info("Refreshed portfolio positions", portfolio_id=portfolio_id, updated_count=updated_count)
        
        return {
            "success": True,
            "message": f"Refreshed {updated_count} positions",
            "updated_count": updated_count
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error refreshing positions", portfolio_id=portfolio_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error refreshing portfolio positions"
        )
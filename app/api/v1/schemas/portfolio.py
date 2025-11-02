from typing import List, Optional, Dict
from pydantic import BaseModel, Field
from datetime import datetime


class PositionResponse(BaseModel):
    """Position response model"""
    instrument_id: str
    instrument_name: str
    quantity: float
    average_cost: float
    total_cost: float
    current_price: Optional[float] = None
    market_value: Optional[float] = None
    unrealized_pnl: Optional[float] = None
    unrealized_pnl_percentage: float = 0.0
    currency: str
    tax_lots_count: int = 0


class PortfolioResponse(BaseModel):
    """Basic portfolio response model"""
    id: str
    name: str
    description: Optional[str] = None
    base_currency: str = "INR"
    is_default: bool = False
    total_value: float = 0.0
    unrealized_pnl: float = 0.0
    position_count: int = 0
    last_updated: Optional[str] = None


class PortfolioSummaryResponse(BaseModel):
    """Detailed portfolio summary response"""
    id: str
    name: str
    description: Optional[str] = None
    base_currency: str = "INR"
    valuation_date: str
    
    # Financial metrics
    total_invested: float
    current_value: float
    unrealized_pnl: float
    unrealized_pnl_percentage: float
    
    # Performance metrics
    xirr_annualized: Optional[float] = None
    total_return_percentage: float
    days_invested: int
    
    # Holdings
    position_count: int
    positions: List[PositionResponse] = []
    
    # Allocations
    asset_allocation: Dict[str, float] = {}
    currency_allocation: Dict[str, float] = {}


class PerformanceResponse(BaseModel):
    """Portfolio performance response"""
    portfolio_id: str
    
    # Time-weighted return
    twr_annualized: Optional[float] = None
    twr_total: Optional[float] = None
    
    # Money-weighted return
    xirr_annualized: Optional[float] = None
    
    # Simple metrics
    total_invested: float
    current_value: float
    total_return: float
    total_return_percentage: float
    
    # Time period
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    days_invested: int
    
    # Risk metrics
    volatility: Optional[float] = None
    sharpe_ratio: Optional[float] = None
    max_drawdown: Optional[float] = None


class PortfolioCreateRequest(BaseModel):
    """Portfolio creation request"""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    base_currency: str = Field("INR", pattern="^[A-Z]{3}$")
    is_default: bool = False


class PortfolioUpdateRequest(BaseModel):
    """Portfolio update request"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    base_currency: Optional[str] = Field(None, pattern="^[A-Z]{3}$")
    is_default: Optional[bool] = None
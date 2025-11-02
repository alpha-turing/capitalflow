from typing import List, Dict, Optional, Tuple
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
import structlog

from app.portfolio.positions import PositionCalculator, PositionSnapshot, TaxLotManager
from app.portfolio.returns import ReturnsCalculator, PerformanceMetrics
from app.db.models import (
    Portfolio, Transaction, Position, TaxLot, Instrument, Price,
    TransactionType, Currency
)


class PortfolioService:
    """Service for portfolio calculations and management"""
    
    def __init__(self):
        self.logger = structlog.get_logger("PortfolioService")
        self.position_calculator = PositionCalculator()
        self.returns_calculator = ReturnsCalculator()
        self.tax_lot_manager = TaxLotManager()
    
    async def calculate_portfolio_positions(
        self,
        db: AsyncSession,
        portfolio_id: str,
        valuation_date: Optional[datetime] = None
    ) -> List[PositionSnapshot]:
        """Calculate all positions for a portfolio"""
        
        valuation_date = valuation_date or datetime.now(timezone.utc)
        
        # Get all transactions for the portfolio with instrument eagerly loaded
        from sqlalchemy.orm import selectinload
        stmt = select(Transaction).where(
            Transaction.portfolio_id == portfolio_id
        ).options(selectinload(Transaction.instrument)).order_by(Transaction.transaction_date)
        
        result = await db.execute(stmt)
        transactions = result.scalars().all()
        
        if not transactions:
            return []
        
        # Group transactions by instrument
        transactions_by_instrument = {}
        for txn in transactions:
            if txn.instrument_id not in transactions_by_instrument:
                transactions_by_instrument[txn.instrument_id] = []
            transactions_by_instrument[txn.instrument_id].append(txn)
        
        positions = []
        
        for instrument_id, instrument_transactions in transactions_by_instrument.items():
            try:
                # Get current price
                current_price = await self._get_current_price(db, instrument_id, valuation_date)
                
                # Calculate position
                position = self.position_calculator.calculate_position(
                    transactions=instrument_transactions,
                    current_price=current_price,
                    valuation_date=valuation_date
                )
                
                # Only include positions with quantity > 0
                if position.quantity > 0:
                    positions.append(position)
                    
            except Exception as e:
                self.logger.error(
                    "Error calculating position", 
                    instrument_id=instrument_id, 
                    error=str(e)
                )
                continue
        
        self.logger.info(
            "Calculated portfolio positions",
            portfolio_id=portfolio_id,
            position_count=len(positions),
            valuation_date=valuation_date.isoformat()
        )
        
        return positions
    
    async def update_portfolio_positions(
        self,
        db: AsyncSession,
        portfolio_id: str,
        force_refresh: bool = False
    ) -> int:
        """Update position records in database"""
        
        positions = await self.calculate_portfolio_positions(db, portfolio_id)
        updated_count = 0
        
        for position_snapshot in positions:
            try:
                # Find existing position record
                stmt = select(Position).where(
                    and_(
                        Position.portfolio_id == portfolio_id,
                        Position.instrument_id == position_snapshot.instrument_id
                    )
                )
                
                result = await db.execute(stmt)
                existing_position = result.scalar_one_or_none()
                
                if existing_position:
                    # Update existing position
                    existing_position.quantity = position_snapshot.quantity
                    existing_position.average_cost = position_snapshot.average_cost
                    existing_position.total_cost = position_snapshot.total_cost
                    existing_position.current_price = position_snapshot.current_price
                    existing_position.market_value = position_snapshot.market_value
                    existing_position.unrealized_pnl = position_snapshot.unrealized_pnl
                    existing_position.last_updated = datetime.now(timezone.utc)
                    
                else:
                    # Create new position
                    new_position = Position(
                        portfolio_id=portfolio_id,
                        instrument_id=position_snapshot.instrument_id,
                        quantity=position_snapshot.quantity,
                        average_cost=position_snapshot.average_cost,
                        total_cost=position_snapshot.total_cost,
                        current_price=position_snapshot.current_price,
                        market_value=position_snapshot.market_value,
                        unrealized_pnl=position_snapshot.unrealized_pnl,
                        currency=position_snapshot.currency,
                        last_updated=datetime.now(timezone.utc)
                    )
                    
                    db.add(new_position)
                
                updated_count += 1
                
            except Exception as e:
                self.logger.error(
                    "Error updating position record",
                    instrument_id=position_snapshot.instrument_id,
                    error=str(e)
                )
                continue
        
        await db.commit()
        
        self.logger.info(
            "Updated portfolio positions",
            portfolio_id=portfolio_id,
            updated_count=updated_count
        )
        
        return updated_count
    
    async def calculate_portfolio_performance(
        self,
        db: AsyncSession,
        portfolio_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> PerformanceMetrics:
        """Calculate portfolio performance metrics"""
        
        end_date = end_date or datetime.now(timezone.utc)
        
        # Get all transactions for the portfolio
        query = select(Transaction).where(Transaction.portfolio_id == portfolio_id)
        
        if start_date:
            query = query.where(Transaction.transaction_date >= start_date)
        if end_date:
            query = query.where(Transaction.transaction_date <= end_date)
        
        query = query.order_by(Transaction.transaction_date)
        
        result = await db.execute(query)
        transactions = result.scalars().all()
        
        if not transactions:
            return PerformanceMetrics()
        
        # Calculate current portfolio value
        positions = await self.calculate_portfolio_positions(db, portfolio_id, end_date)
        current_value = sum(
            position.market_value or Decimal('0') 
            for position in positions
        )
        
        # Get historical portfolio values for TWR calculation
        # For MVP, we'll skip this and focus on XIRR
        portfolio_values = None
        
        # Calculate performance metrics
        metrics = self.returns_calculator.calculate_performance_metrics(
            transactions=transactions,
            current_value=current_value,
            valuation_date=end_date,
            portfolio_values=portfolio_values
        )
        
        self.logger.info(
            "Calculated portfolio performance",
            portfolio_id=portfolio_id,
            xirr=f"{float(metrics.xirr_annualized) * 100:.2f}%" if metrics.xirr_annualized else None,
            total_return=f"{float(metrics.total_return_percentage):.2f}%"
        )
        
        return metrics
    
    async def get_portfolio_summary(
        self,
        db: AsyncSession,
        portfolio_id: str,
        valuation_date: Optional[datetime] = None
    ) -> Dict[str, any]:
        """Get comprehensive portfolio summary"""
        
        valuation_date = valuation_date or datetime.now(timezone.utc)
        
        # Get portfolio info
        portfolio = await db.get(Portfolio, portfolio_id)
        if not portfolio:
            raise ValueError(f"Portfolio {portfolio_id} not found")
        
        # Calculate positions
        positions = await self.calculate_portfolio_positions(db, portfolio_id, valuation_date)
        
        # Calculate performance
        performance = await self.calculate_portfolio_performance(db, portfolio_id)
        
        # Calculate summary metrics
        total_investments = sum(pos.total_cost for pos in positions)
        total_market_value = sum(pos.market_value or Decimal('0') for pos in positions)
        total_unrealized_pnl = sum(pos.unrealized_pnl or Decimal('0') for pos in positions)
        
        # Asset allocation
        asset_allocation = await self._calculate_asset_allocation(db, positions)
        
        # Currency allocation 
        currency_allocation = self._calculate_currency_allocation(positions)
        
        summary = {
            'portfolio_id': portfolio_id,
            'portfolio_name': portfolio.name,
            'base_currency': portfolio.base_currency,
            'valuation_date': valuation_date.isoformat(),
            
            # Values
            'total_invested': float(total_investments),
            'current_value': float(total_market_value),
            'unrealized_pnl': float(total_unrealized_pnl),
            'unrealized_pnl_percentage': float(total_unrealized_pnl / total_investments * 100) if total_investments > 0 else 0.0,
            
            # Performance
            'xirr_annualized': float(performance.xirr_annualized) if performance.xirr_annualized else None,
            'total_return_percentage': float(performance.total_return_percentage),
            'days_invested': performance.days_invested,
            
            # Holdings
            'total_positions': len(positions),
            'positions': [self._position_to_dict(pos) for pos in positions],
            
            # Allocations
            'asset_allocation': asset_allocation,
            'currency_allocation': currency_allocation,
        }
        
        return summary
    
    async def get_realized_gains(
        self,
        db: AsyncSession,
        portfolio_id: str,
        financial_year: Optional[str] = None
    ) -> List[Dict]:
        """Get realized gains for tax reporting"""
        
        # For MVP, we'll implement a simplified version
        # This would need to be enhanced with proper tax lot tracking
        
        query = select(Transaction).where(
            and_(
                Transaction.portfolio_id == portfolio_id,
                Transaction.transaction_type == TransactionType.SELL
            )
        ).order_by(Transaction.transaction_date)
        
        result = await db.execute(query)
        sale_transactions = result.scalars().all()
        
        gains = []
        
        for sale_txn in sale_transactions:
            # Simplified gain calculation
            # In production, this should use proper FIFO tax lot matching
            
            gain_data = {
                'transaction_id': sale_txn.id,
                'instrument_name': sale_txn.instrument.name if sale_txn.instrument else "Unknown",
                'sale_date': sale_txn.transaction_date.isoformat(),
                'sale_quantity': float(sale_txn.quantity),
                'sale_price': float(sale_txn.price),
                'sale_proceeds': float(sale_txn.net_amount or sale_txn.gross_amount),
                # These would be calculated from tax lots in production
                'cost_basis': 0.0,
                'realized_gain': 0.0,
                'is_long_term': False,
                'holding_period_days': 0
            }
            
            gains.append(gain_data)
        
        return gains
    
    async def _get_current_price(
        self,
        db: AsyncSession,
        instrument_id: str,
        valuation_date: datetime
    ) -> Optional[Decimal]:
        """Get current price for an instrument"""
        
        # Find the most recent price on or before valuation date
        stmt = select(Price).where(
            and_(
                Price.instrument_id == instrument_id,
                Price.price_date <= valuation_date
            )
        ).order_by(Price.price_date.desc()).limit(1)
        
        result = await db.execute(stmt)
        price_record = result.scalar_one_or_none()
        
        if price_record:
            return price_record.close_price
        
        return None
    
    async def _calculate_asset_allocation(
        self,
        db: AsyncSession,
        positions: List[PositionSnapshot]
    ) -> Dict[str, float]:
        """Calculate asset class allocation"""
        
        total_value = sum(pos.market_value or Decimal('0') for pos in positions)
        
        if total_value == 0:
            return {}
        
        # Get instrument details for asset classification
        allocation = {}
        
        for position in positions:
            # Get instrument details
            instrument = await db.get(Instrument, position.instrument_id)
            
            if instrument and position.market_value:
                asset_class = instrument.asset_class.value
                allocation_pct = float(position.market_value / total_value * 100)
                
                if asset_class in allocation:
                    allocation[asset_class] += allocation_pct
                else:
                    allocation[asset_class] = allocation_pct
        
        return allocation
    
    def _calculate_currency_allocation(
        self, 
        positions: List[PositionSnapshot]
    ) -> Dict[str, float]:
        """Calculate currency allocation"""
        
        total_value = sum(pos.market_value or Decimal('0') for pos in positions)
        
        if total_value == 0:
            return {}
        
        allocation = {}
        
        for position in positions:
            if position.market_value:
                currency = position.currency.value
                allocation_pct = float(position.market_value / total_value * 100)
                
                if currency in allocation:
                    allocation[currency] += allocation_pct
                else:
                    allocation[currency] = allocation_pct
        
        return allocation
    
    def _position_to_dict(self, position: PositionSnapshot) -> Dict:
        """Convert position snapshot to dictionary"""
        
        return {
            'instrument_id': position.instrument_id,
            'instrument_name': position.instrument_name,
            'quantity': float(position.quantity),
            'average_cost': float(position.average_cost),
            'total_cost': float(position.total_cost),
            'current_price': float(position.current_price) if position.current_price else None,
            'market_value': float(position.market_value) if position.market_value else None,
            'unrealized_pnl': float(position.unrealized_pnl) if position.unrealized_pnl else None,
            'unrealized_pnl_percentage': float(position.unrealized_pnl / position.total_cost * 100) if position.unrealized_pnl and position.total_cost > 0 else 0.0,
            'currency': position.currency.value,
            'tax_lots_count': len(position.tax_lots) if position.tax_lots else 0
        }


# Create global service instance
portfolio_service = PortfolioService()
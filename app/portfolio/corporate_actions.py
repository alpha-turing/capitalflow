from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload
import structlog
from decimal import Decimal
from typing import Dict, Any

from app.db.models import (
    CorporateAction, 
    Position, 
    TaxLot, 
    Transaction,
    CorporateActionStatus,
    CorporateActionType
)


logger = structlog.get_logger("corporate_actions")


class CorporateActionProcessor:
    """Processes corporate actions and adjusts positions"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def process_action(self, action_id: str) -> bool:
        """Process a corporate action"""
        
        try:
            # Get corporate action with instrument
            result = await self.db.execute(
                select(CorporateAction)
                .options(selectinload(CorporateAction.instrument))
                .where(CorporateAction.id == action_id)
            )
            action = result.scalar_one_or_none()
            
            if not action:
                raise ValueError(f"Corporate action {action_id} not found")
            
            if action.status != CorporateActionStatus.PENDING:
                raise ValueError(f"Corporate action {action_id} is not in pending status")
            
            # Update status to processing
            action.status = CorporateActionStatus.PROCESSING
            await self.db.commit()
            
            # Process based on action type
            if action.action_type == CorporateActionType.STOCK_SPLIT:
                await self._process_stock_split(action)
            elif action.action_type == CorporateActionType.BONUS:
                await self._process_bonus_issue(action)
            elif action.action_type == CorporateActionType.DIVIDEND:
                await self._process_dividend(action)
            else:
                raise ValueError(f"Unsupported corporate action type: {action.action_type}")
            
            # Update status to completed
            action.status = CorporateActionStatus.COMPLETED
            await self.db.commit()
            
            logger.info("Corporate action processed successfully", action_id=action_id)
            return True
            
        except Exception as e:
            logger.error("Error processing corporate action", action_id=action_id, error=str(e))
            
            # Update status to failed
            if action:
                action.status = CorporateActionStatus.FAILED
                await self.db.commit()
            
            raise e
    
    async def _process_stock_split(self, action: CorporateAction):
        """Process stock split - adjust quantities and prices"""
        
        if not action.ratio_old or not action.ratio_new:
            raise ValueError("Stock split requires ratio_old and ratio_new")
        
        split_ratio = action.ratio_new / action.ratio_old
        
        # Get all positions for this instrument
        result = await self.db.execute(
            select(Position)
            .where(Position.instrument_id == action.instrument_id)
            .where(Position.quantity > 0)
        )
        positions = result.scalars().all()
        
        # Update positions
        for position in positions:
            new_quantity = position.quantity * split_ratio
            new_avg_price = position.average_price / split_ratio
            
            position.quantity = new_quantity
            position.average_price = new_avg_price
            
            logger.info(
                "Updated position for stock split",
                position_id=position.id,
                old_qty=float(position.quantity / split_ratio),
                new_qty=float(new_quantity)
            )
        
        # Update tax lots
        result = await self.db.execute(
            select(TaxLot)
            .join(Transaction)
            .where(Transaction.instrument_id == action.instrument_id)
            .where(TaxLot.status == "open")
        )
        tax_lots = result.scalars().all()
        
        for tax_lot in tax_lots:
            tax_lot.quantity = tax_lot.quantity * split_ratio
            tax_lot.buy_price = tax_lot.buy_price / split_ratio
            
        await self.db.commit()
    
    async def _process_bonus_issue(self, action: CorporateAction):
        """Process bonus issue - add free shares"""
        
        if not action.ratio_old or not action.ratio_new:
            raise ValueError("Bonus issue requires ratio_old and ratio_new")
        
        bonus_ratio = action.ratio_new / action.ratio_old
        
        # Get all positions for this instrument on record date
        result = await self.db.execute(
            select(Position)
            .where(Position.instrument_id == action.instrument_id)
            .where(Position.quantity > 0)
        )
        positions = result.scalars().all()
        
        # Update positions with bonus shares
        for position in positions:
            bonus_shares = position.quantity * bonus_ratio
            new_total_quantity = position.quantity + bonus_shares
            
            # Adjust average price (cost remains same, quantity increases)
            new_avg_price = (position.average_price * position.quantity) / new_total_quantity
            
            position.quantity = new_total_quantity
            position.average_price = new_avg_price
            
            logger.info(
                "Added bonus shares",
                position_id=position.id,
                original_qty=float(position.quantity - bonus_shares),
                bonus_qty=float(bonus_shares),
                new_total=float(new_total_quantity)
            )
        
        await self.db.commit()
    
    async def _process_dividend(self, action: CorporateAction):
        """Process dividend - create cash transactions"""
        
        if not action.cash_amount:
            raise ValueError("Dividend requires cash_amount")
        
        # Get all positions for this instrument on record date
        result = await self.db.execute(
            select(Position)
            .options(selectinload(Position.portfolio))
            .where(Position.instrument_id == action.instrument_id)
            .where(Position.quantity > 0)
        )
        positions = result.scalars().all()
        
        # Create dividend transactions
        for position in positions:
            dividend_amount = position.quantity * action.cash_amount
            
            # Create dividend transaction
            dividend_txn = Transaction(
                portfolio_id=position.portfolio_id,
                instrument_id=action.instrument_id,
                transaction_type="dividend",
                transaction_date=action.payment_date or action.ex_date,
                quantity=Decimal('0'),  # No quantity change for dividend
                price=action.cash_amount,
                amount=dividend_amount,
                currency="INR",  # Default currency
                notes=f"Dividend from corporate action {action.id}"
            )
            
            self.db.add(dividend_txn)
            
            logger.info(
                "Created dividend transaction",
                position_id=position.id,
                dividend_per_share=float(action.cash_amount),
                total_dividend=float(dividend_amount)
            )
        
        await self.db.commit()
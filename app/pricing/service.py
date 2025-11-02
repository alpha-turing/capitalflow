from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
from datetime import date, datetime, timedelta
from typing import List, Optional
import structlog
from decimal import Decimal

from app.db.models import Instrument, Price
from app.pricing.providers import (
    NSEPriceProvider,
    AMFIPriceProvider, 
    FXRateProvider,
    USEquityPriceProvider
)


logger = structlog.get_logger("pricing_service")


class PricingService:
    """Service to fetch and store instrument prices"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.providers = [
            NSEPriceProvider(),
            AMFIPriceProvider(),
            FXRateProvider(),
            USEquityPriceProvider()
        ]
    
    async def update_eod_prices(self, price_date: Optional[date] = None) -> int:
        """Update end-of-day prices for all active instruments"""
        
        if price_date is None:
            price_date = date.today()
        
        # Skip weekends for now (can be enhanced with market calendars)
        if price_date.weekday() >= 5:  # Saturday = 5, Sunday = 6
            logger.info("Skipping weekend date", price_date=price_date)
            return 0
        
        # Get all active instruments that need pricing
        result = await self.db.execute(
            select(Instrument)
            .where(Instrument.is_active == True)
        )
        instruments = result.scalars().all()
        
        total_updated = 0
        
        # Group instruments by provider
        for provider in self.providers:
            provider_instruments = [
                inst for inst in instruments 
                if provider.supports_instrument(inst)
            ]
            
            if not provider_instruments:
                continue
            
            try:
                # Get prices from provider
                prices = await provider.get_prices(provider_instruments, price_date)
                
                # Store prices in database
                updated_count = await self._store_prices(prices, price_date)
                total_updated += updated_count
                
                logger.info(
                    "Updated prices from provider",
                    provider=provider.__class__.__name__,
                    instruments_count=len(provider_instruments),
                    prices_updated=updated_count,
                    price_date=price_date
                )
                
            except Exception as e:
                logger.error(
                    "Error updating prices from provider",
                    provider=provider.__class__.__name__,
                    error=str(e)
                )
        
        return total_updated
    
    async def get_latest_price(self, instrument_id: str) -> Optional[Price]:
        """Get latest available price for an instrument"""
        
        result = await self.db.execute(
            select(Price)
            .where(Price.instrument_id == instrument_id)
            .order_by(Price.price_date.desc())
            .limit(1)
        )
        
        return result.scalar_one_or_none()
    
    async def get_price_on_date(self, instrument_id: str, price_date: date) -> Optional[Price]:
        """Get price for an instrument on a specific date"""
        
        result = await self.db.execute(
            select(Price)
            .where(
                and_(
                    Price.instrument_id == instrument_id,
                    Price.price_date == price_date
                )
            )
        )
        
        return result.scalar_one_or_none()
    
    async def get_historical_prices(
        self, 
        instrument_id: str, 
        start_date: date, 
        end_date: date
    ) -> List[Price]:
        """Get historical prices for an instrument in date range"""
        
        result = await self.db.execute(
            select(Price)
            .where(
                and_(
                    Price.instrument_id == instrument_id,
                    Price.price_date >= start_date,
                    Price.price_date <= end_date
                )
            )
            .order_by(Price.price_date.asc())
        )
        
        return result.scalars().all()
    
    async def _store_prices(self, prices: dict, price_date: date) -> int:
        """Store prices in database"""
        
        updated_count = 0
        
        for instrument_id, price_value in prices.items():
            try:
                # Check if price already exists for this date
                existing_price = await self.get_price_on_date(instrument_id, price_date)
                
                if existing_price:
                    # Update existing price
                    existing_price.close_price = price_value
                    existing_price.updated_at = datetime.now()
                else:
                    # Create new price record
                    new_price = Price(
                        instrument_id=instrument_id,
                        price_date=price_date,
                        close_price=price_value,
                        currency="INR"  # Default currency, should be instrument-specific
                    )
                    self.db.add(new_price)
                
                updated_count += 1
                
            except Exception as e:
                logger.error(
                    "Error storing price",
                    instrument_id=instrument_id,
                    price=price_value,
                    error=str(e)
                )
        
        await self.db.commit()
        return updated_count
    
    async def backfill_missing_prices(self, days: int = 30) -> int:
        """Backfill missing prices for the last N days"""
        
        end_date = date.today()
        start_date = end_date - timedelta(days=days)
        
        total_updated = 0
        current_date = start_date
        
        while current_date <= end_date:
            # Skip weekends
            if current_date.weekday() < 5:
                daily_updated = await self.update_eod_prices(current_date)
                total_updated += daily_updated
                
                logger.info(
                    "Backfilled prices for date",
                    price_date=current_date,
                    updated_count=daily_updated
                )
            
            current_date += timedelta(days=1)
        
        return total_updated
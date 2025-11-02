from celery import Celery
from datetime import date, datetime, timedelta
import structlog

from app.core.config import settings
from app.core.database import async_session
from app.pricing.service import PricingService


# Create Celery app
celery_app = Celery(
    "reaum_worker",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.pricing.tasks"]
)

# Configure Celery
celery_app.conf.update(
    timezone="Asia/Kolkata",
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_track_started=True,
    task_send_sent_event=True,
    worker_send_task_events=True,
    result_expires=3600,
)

logger = structlog.get_logger("pricing_tasks")


@celery_app.task(bind=True)
def update_eod_prices_task(self, price_date_str: str = None):
    """Celery task to update end-of-day prices"""
    
    import asyncio
    
    async def _update_prices():
        try:
            price_date = date.fromisoformat(price_date_str) if price_date_str else date.today()
            
            async with async_session() as db:
                pricing_service = PricingService(db)
                updated_count = await pricing_service.update_eod_prices(price_date)
                
                logger.info(
                    "EOD prices update completed",
                    task_id=self.request.id,
                    price_date=price_date,
                    updated_count=updated_count
                )
                
                return {
                    "status": "completed",
                    "price_date": price_date.isoformat(),
                    "updated_count": updated_count
                }
                
        except Exception as e:
            logger.error(
                "EOD prices update failed",
                task_id=self.request.id,
                error=str(e)
            )
            raise e
    
    # Run async function in event loop
    return asyncio.run(_update_prices())


@celery_app.task(bind=True)
def backfill_prices_task(self, days: int = 30):
    """Celery task to backfill missing historical prices"""
    
    import asyncio
    
    async def _backfill_prices():
        try:
            async with async_session() as db:
                pricing_service = PricingService(db)
                updated_count = await pricing_service.backfill_missing_prices(days)
                
                logger.info(
                    "Price backfill completed",
                    task_id=self.request.id,
                    days=days,
                    updated_count=updated_count
                )
                
                return {
                    "status": "completed",
                    "days": days,
                    "updated_count": updated_count
                }
                
        except Exception as e:
            logger.error(
                "Price backfill failed",
                task_id=self.request.id,
                error=str(e)
            )
            raise e
    
    return asyncio.run(_backfill_prices())


# Schedule daily EOD price updates (runs at 6 PM IST after market close)
celery_app.conf.beat_schedule = {
    "update-eod-prices": {
        "task": "app.pricing.tasks.update_eod_prices_task",
        "schedule": {
            "hour": 18,
            "minute": 0
        },
    },
    # Weekly backfill on Sundays
    "weekly-price-backfill": {
        "task": "app.pricing.tasks.backfill_prices_task", 
        "schedule": {
            "hour": 2,
            "minute": 0,
            "day_of_week": 0  # Sunday
        },
        "kwargs": {"days": 7}
    }
}
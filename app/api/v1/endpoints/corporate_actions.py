from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from sqlalchemy.orm import selectinload
from typing import List
import structlog
from datetime import datetime, timedelta

from app.core.database import get_db
from app.api.dependencies import get_current_user
from app.db.models import User, CorporateAction, Position, TaxLot, Transaction, Instrument
from app.api.v1.schemas.corporate_actions import (
    CorporateActionCreate,
    CorporateActionResponse,
    CorporateActionType,
    CorporateActionStatus
)
from app.portfolio.corporate_actions import CorporateActionProcessor


router = APIRouter()
logger = structlog.get_logger("corporate_actions_api")


@router.get("/", response_model=List[CorporateActionResponse])
async def list_corporate_actions(
    instrument_id: str = None,
    action_type: CorporateActionType = None,
    status: CorporateActionStatus = None,
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List corporate actions"""
    
    try:
        query = (
            select(CorporateAction)
            .options(selectinload(CorporateAction.instrument))
            .join(Instrument)
            .where(
                or_(
                    CorporateAction.created_by == current_user.id,
                    CorporateAction.status == CorporateActionStatus.APPROVED
                )
            )
        )
        
        if instrument_id:
            query = query.where(CorporateAction.instrument_id == instrument_id)
        
        if action_type:
            query = query.where(CorporateAction.action_type == action_type)
        
        if status:
            query = query.where(CorporateAction.status == status)
        
        query = query.order_by(CorporateAction.ex_date.desc()).offset(skip).limit(limit)
        
        result = await db.execute(query)
        actions = result.scalars().all()
        
        return [
            CorporateActionResponse(
                id=action.id,
                instrument_id=action.instrument_id,
                instrument_name=action.instrument.name,
                action_type=action.action_type,
                status=action.status,
                ex_date=action.ex_date,
                record_date=action.record_date,
                payment_date=action.payment_date,
                ratio_old=action.ratio_old,
                ratio_new=action.ratio_new,
                cash_amount=action.cash_amount,
                description=action.description,
                created_at=action.created_at,
                updated_at=action.updated_at
            )
            for action in actions
        ]
        
    except Exception as e:
        logger.error("Error listing corporate actions", user_id=current_user.id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving corporate actions"
        )


@router.post("/", response_model=CorporateActionResponse)
async def create_corporate_action(
    action_data: CorporateActionCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create new corporate action"""
    
    try:
        # Verify instrument exists
        instrument = await db.get(Instrument, action_data.instrument_id)
        if not instrument:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Instrument not found"
            )
        
        # Create corporate action
        corporate_action = CorporateAction(
            instrument_id=action_data.instrument_id,
            action_type=action_data.action_type,
            status=CorporateActionStatus.PENDING,
            ex_date=action_data.ex_date,
            record_date=action_data.record_date,
            payment_date=action_data.payment_date,
            ratio_old=action_data.ratio_old,
            ratio_new=action_data.ratio_new,
            cash_amount=action_data.cash_amount,
            description=action_data.description,
            created_by=current_user.id
        )
        
        db.add(corporate_action)
        await db.commit()
        await db.refresh(corporate_action)
        
        # Process corporate action in background if auto-approved
        if corporate_action.status == CorporateActionStatus.APPROVED:
            background_tasks.add_task(
                process_corporate_action_async,
                str(corporate_action.id),
                current_user.id
            )
        
        logger.info(
            "Created corporate action",
            user_id=current_user.id,
            action_id=corporate_action.id,
            action_type=action_data.action_type
        )
        
        return CorporateActionResponse(
            id=corporate_action.id,
            instrument_id=corporate_action.instrument_id,
            instrument_name=instrument.name,
            action_type=corporate_action.action_type,
            status=corporate_action.status,
            ex_date=corporate_action.ex_date,
            record_date=corporate_action.record_date,
            payment_date=corporate_action.payment_date,
            ratio_old=corporate_action.ratio_old,
            ratio_new=corporate_action.ratio_new,
            cash_amount=corporate_action.cash_amount,
            description=corporate_action.description,
            created_at=corporate_action.created_at,
            updated_at=corporate_action.updated_at
        )
        
    except Exception as e:
        await db.rollback()
        logger.error("Error creating corporate action", user_id=current_user.id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating corporate action"
        )


@router.post("/{action_id}/process")
async def process_corporate_action(
    action_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Process/apply corporate action to positions"""
    
    try:
        # Get corporate action
        corporate_action = await db.get(CorporateAction, action_id)
        if not corporate_action:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Corporate action not found"
            )
        
        if corporate_action.status != CorporateActionStatus.PENDING:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Corporate action is not in pending status"
            )
        
        # Update status to processing
        corporate_action.status = CorporateActionStatus.PROCESSING
        await db.commit()
        
        # Process in background
        background_tasks.add_task(
            process_corporate_action_async,
            action_id,
            current_user.id
        )
        
        logger.info("Started processing corporate action", action_id=action_id, user_id=current_user.id)
        
        return {"message": "Corporate action processing started", "action_id": action_id}
        
    except Exception as e:
        logger.error("Error processing corporate action", action_id=action_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error processing corporate action"
        )


async def process_corporate_action_async(action_id: str, user_id: str):
    """Background task to process corporate action"""
    
    from app.core.database import async_session
    
    async with async_session() as db:
        try:
            processor = CorporateActionProcessor(db)
            await processor.process_action(action_id)
            
            logger.info("Completed corporate action processing", action_id=action_id, user_id=user_id)
            
        except Exception as e:
            logger.error("Error in corporate action processing", action_id=action_id, error=str(e))
            
            # Update status to failed
            corporate_action = await db.get(CorporateAction, action_id)
            if corporate_action:
                corporate_action.status = CorporateActionStatus.FAILED
                await db.commit()
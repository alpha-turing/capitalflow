from typing import Optional
from datetime import date
from decimal import Decimal
from pydantic import BaseModel
from enum import Enum


class CorporateActionType(str, Enum):
    """Types of corporate actions"""
    DIVIDEND = "dividend"
    STOCK_SPLIT = "stock_split"
    BONUS = "bonus"
    RIGHTS = "rights"
    SPIN_OFF = "spin_off"
    MERGER = "merger"


class CorporateActionStatus(str, Enum):
    """Status of corporate action"""
    PENDING = "pending"
    APPROVED = "approved"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class CorporateActionCreate(BaseModel):
    """Schema for creating corporate action"""
    instrument_id: str
    action_type: CorporateActionType
    ex_date: date
    record_date: Optional[date] = None
    payment_date: Optional[date] = None
    ratio_old: Optional[Decimal] = None
    ratio_new: Optional[Decimal] = None
    cash_amount: Optional[Decimal] = None
    description: Optional[str] = None


class CorporateActionResponse(BaseModel):
    """Schema for corporate action response"""
    id: str
    instrument_id: str
    instrument_name: str
    action_type: CorporateActionType
    status: CorporateActionStatus
    ex_date: date
    record_date: Optional[date] = None
    payment_date: Optional[date] = None
    ratio_old: Optional[Decimal] = None
    ratio_new: Optional[Decimal] = None
    cash_amount: Optional[Decimal] = None
    description: Optional[str] = None
    created_at: date
    updated_at: date
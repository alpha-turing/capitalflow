from typing import List, Optional
from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel


class TaxLotDetails(BaseModel):
    """Tax lot reference details"""
    tax_lot_id: str
    buy_transaction_id: str
    sell_transaction_id: str


class CapitalGainsReportItem(BaseModel):
    """Individual capital gains transaction item"""
    instrument_name: str
    isin: Optional[str] = None
    quantity: Decimal
    buy_date: date
    sell_date: date
    buy_price: Decimal
    sell_price: Decimal
    buy_value: Decimal
    sell_value: Decimal
    capital_gain: Decimal
    holding_period_days: int
    is_long_term: bool
    tax_lot_details: TaxLotDetails


class CapitalGainsResponse(BaseModel):
    """Capital gains report response"""
    financial_year: str
    report_date: date
    total_transactions: int
    total_short_term_gains: Decimal
    total_long_term_gains: Decimal
    net_capital_gains: Decimal
    gains_items: List[CapitalGainsReportItem]
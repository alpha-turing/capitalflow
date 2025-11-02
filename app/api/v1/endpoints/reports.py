from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, extract
from sqlalchemy.orm import selectinload
from typing import List, Optional
import structlog
from datetime import datetime, date
import csv
import io
from decimal import Decimal

from app.core.database import get_db
from app.api.dependencies import get_current_user
from app.db.models import User, Transaction, Portfolio, TaxLot
from app.api.v1.schemas.reports import (
    CapitalGainsReportItem,
    CapitalGainsResponse,
    TaxLotDetails
)
from fastapi.responses import StreamingResponse


router = APIRouter()
logger = structlog.get_logger("reports_api")


@router.get("/capital-gains", response_model=CapitalGainsResponse)
async def get_capital_gains_report(
    financial_year: str = Query(..., description="Format: FY2025-26"),
    portfolio_id: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get capital gains report for specified financial year"""
    
    try:
        # Parse financial year
        fy_parts = financial_year.replace("FY", "").split("-")
        start_year = int(fy_parts[0])
        end_year = int(fy_parts[1]) + 2000 if int(fy_parts[1]) < 100 else int(fy_parts[1])
        
        # Indian FY: April 1 to March 31
        fy_start = date(start_year, 4, 1)
        fy_end = date(end_year, 3, 31)
        
        # Build query for realized tax lots (sells) in the FY
        query = (
            select(TaxLot)
            .options(
                selectinload(TaxLot.transaction).selectinload(Transaction.instrument),
                selectinload(TaxLot.buy_transaction).selectinload(Transaction.instrument)
            )
            .join(Transaction, TaxLot.transaction_id == Transaction.id)
            .join(Portfolio, Transaction.portfolio_id == Portfolio.id)
            .where(
                and_(
                    Portfolio.user_id == current_user.id,
                    TaxLot.status == "realized",
                    Transaction.transaction_date >= fy_start,
                    Transaction.transaction_date <= fy_end,
                    Transaction.transaction_type == "sell"
                )
            )
        )
        
        if portfolio_id:
            query = query.where(Portfolio.id == portfolio_id)
        
        result = await db.execute(query)
        tax_lots = result.scalars().all()
        
        gains_items = []
        total_short_term_gains = Decimal('0')
        total_long_term_gains = Decimal('0')
        
        for tax_lot in tax_lots:
            sell_txn = tax_lot.transaction
            buy_txn = tax_lot.buy_transaction
            
            # Calculate holding period
            holding_days = (sell_txn.transaction_date - buy_txn.transaction_date).days
            is_long_term = holding_days > 365  # 1 year for equity, can be refined by asset class
            
            # Calculate gains
            buy_value = tax_lot.quantity * tax_lot.buy_price
            sell_value = tax_lot.quantity * tax_lot.sell_price
            capital_gain = sell_value - buy_value
            
            if is_long_term:
                total_long_term_gains += capital_gain
            else:
                total_short_term_gains += capital_gain
            
            gains_item = CapitalGainsReportItem(
                instrument_name=sell_txn.instrument.name,
                isin=sell_txn.instrument.isin,
                quantity=tax_lot.quantity,
                buy_date=buy_txn.transaction_date,
                sell_date=sell_txn.transaction_date,
                buy_price=tax_lot.buy_price,
                sell_price=tax_lot.sell_price,
                buy_value=buy_value,
                sell_value=sell_value,
                capital_gain=capital_gain,
                holding_period_days=holding_days,
                is_long_term=is_long_term,
                tax_lot_details=TaxLotDetails(
                    tax_lot_id=tax_lot.id,
                    buy_transaction_id=buy_txn.id,
                    sell_transaction_id=sell_txn.id
                )
            )
            gains_items.append(gains_item)
        
        response = CapitalGainsResponse(
            financial_year=financial_year,
            report_date=datetime.now().date(),
            total_transactions=len(gains_items),
            total_short_term_gains=total_short_term_gains,
            total_long_term_gains=total_long_term_gains,
            net_capital_gains=total_short_term_gains + total_long_term_gains,
            gains_items=gains_items
        )
        
        logger.info(
            "Generated capital gains report",
            user_id=current_user.id,
            financial_year=financial_year,
            total_transactions=len(gains_items)
        )
        
        return response
        
    except Exception as e:
        logger.error("Error generating capital gains report", user_id=current_user.id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error generating capital gains report"
        )


@router.get("/capital-gains/export")
async def export_capital_gains_csv(
    financial_year: str = Query(..., description="Format: FY2025-26"),
    portfolio_id: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Export capital gains report as CSV"""
    
    try:
        # Get the capital gains data
        report_data = await get_capital_gains_report(
            financial_year=financial_year,
            portfolio_id=portfolio_id,
            current_user=current_user,
            db=db
        )
        
        # Create CSV content
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write headers
        writer.writerow([
            "Instrument Name",
            "ISIN",
            "Quantity",
            "Buy Date",
            "Sell Date",
            "Buy Price",
            "Sell Price",
            "Buy Value",
            "Sell Value",
            "Capital Gain/Loss",
            "Holding Period (Days)",
            "Gain Type"
        ])
        
        # Write data rows
        for item in report_data.gains_items:
            writer.writerow([
                item.instrument_name,
                item.isin or "",
                float(item.quantity),
                item.buy_date.strftime("%Y-%m-%d"),
                item.sell_date.strftime("%Y-%m-%d"),
                float(item.buy_price),
                float(item.sell_price),
                float(item.buy_value),
                float(item.sell_value),
                float(item.capital_gain),
                item.holding_period_days,
                "Long Term" if item.is_long_term else "Short Term"
            ])
        
        # Add summary rows
        writer.writerow([])
        writer.writerow(["SUMMARY"])
        writer.writerow(["Total Short Term Gains", "", "", "", "", "", "", "", "", float(report_data.total_short_term_gains)])
        writer.writerow(["Total Long Term Gains", "", "", "", "", "", "", "", "", float(report_data.total_long_term_gains)])
        writer.writerow(["Net Capital Gains", "", "", "", "", "", "", "", "", float(report_data.net_capital_gains)])
        
        # Prepare file for download
        output.seek(0)
        filename = f"capital_gains_{financial_year}_{datetime.now().strftime('%Y%m%d')}.csv"
        
        logger.info(
            "Exported capital gains CSV",
            user_id=current_user.id,
            financial_year=financial_year,
            filename=filename
        )
        
        return StreamingResponse(
            io.BytesIO(output.getvalue().encode()),
            media_type="application/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
        
    except Exception as e:
        logger.error("Error exporting capital gains CSV", user_id=current_user.id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error exporting capital gains report"
        )
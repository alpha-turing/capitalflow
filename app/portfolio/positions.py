from typing import List, Dict, Tuple, Optional
from datetime import datetime, date, timezone
from decimal import Decimal
from dataclasses import dataclass
import structlog
from enum import Enum

from app.db.models import Transaction, Position, TaxLot, TransactionType, Currency


def _normalize_datetime(dt: datetime) -> datetime:
    """Ensure datetime is timezone-aware by adding UTC if naive"""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class TaxLotMethod(str, Enum):
    """Tax lot selection methods"""
    FIFO = "fifo"  # First In, First Out
    LIFO = "lifo"  # Last In, First Out
    SPEC_ID = "spec_id"  # Specific Identification


@dataclass
class PositionSnapshot:
    """Snapshot of a position at a point in time"""
    instrument_id: str
    instrument_name: str
    quantity: Decimal
    average_cost: Decimal
    total_cost: Decimal
    current_price: Optional[Decimal] = None
    market_value: Optional[Decimal] = None
    unrealized_pnl: Optional[Decimal] = None
    currency: Currency = Currency.INR
    
    # Tax lot details
    tax_lots: List['TaxLotSnapshot'] = None
    
    def __post_init__(self):
        if self.tax_lots is None:
            self.tax_lots = []


@dataclass
class TaxLotSnapshot:
    """Snapshot of a tax lot"""
    acquisition_date: datetime
    quantity: Decimal
    remaining_quantity: Decimal
    cost_per_share: Decimal
    total_cost: Decimal
    is_long_term: bool
    days_held: int


@dataclass
class RealizedGain:
    """Realized gain/loss from a sale"""
    instrument_id: str
    instrument_name: str
    sale_date: datetime
    sale_quantity: Decimal
    sale_price: Decimal
    sale_proceeds: Decimal
    
    # Cost basis details
    cost_basis: Decimal
    cost_per_share: Decimal
    
    # Gain/loss
    realized_gain: Decimal
    gain_percentage: Decimal
    
    # Tax classification
    is_long_term: bool
    holding_period_days: int
    
    # Source transactions
    sale_transaction_id: str
    acquisition_lots: List[Tuple[str, Decimal, Decimal]]  # (transaction_id, quantity, cost)


class TaxLotManager:
    """Manages tax lots using FIFO methodology"""
    
    def __init__(self, method: TaxLotMethod = TaxLotMethod.FIFO):
        self.method = method
        self.logger = structlog.get_logger("TaxLotManager")
    
    def process_transaction(
        self,
        transaction: Transaction,
        existing_lots: List[TaxLot]
    ) -> Tuple[List[TaxLot], List[RealizedGain]]:
        """Process a transaction and update tax lots"""
        
        if transaction.transaction_type == TransactionType.BUY:
            return self._process_purchase(transaction, existing_lots)
        elif transaction.transaction_type == TransactionType.SELL:
            return self._process_sale(transaction, existing_lots)
        elif transaction.transaction_type == TransactionType.DIVIDEND:
            # Dividends don't affect tax lots
            return existing_lots, []
        else:
            # Other transaction types (splits, bonuses) handled separately
            return existing_lots, []
    
    def _process_purchase(
        self,
        transaction: Transaction,
        existing_lots: List[TaxLot]
    ) -> Tuple[List[TaxLot], List[RealizedGain]]:
        """Process a purchase transaction"""
        
        # Create new tax lot
        new_lot = TaxLot(
            position_id="",  # Will be set by caller
            transaction_id=transaction.id,
            quantity=transaction.quantity,
            remaining_quantity=transaction.quantity,
            cost_per_share=transaction.price,
            acquisition_date=transaction.transaction_date,
            is_closed=False
        )
        
        # Add to existing lots
        updated_lots = existing_lots + [new_lot]
        
        self.logger.info(
            "Created new tax lot",
            transaction_id=transaction.id,
            quantity=str(transaction.quantity),
            cost_per_share=str(transaction.price)
        )
        
        return updated_lots, []
    
    def _process_sale(
        self,
        transaction: Transaction,
        existing_lots: List[TaxLot]
    ) -> Tuple[List[TaxLot], List[RealizedGain]]:
        """Process a sale transaction using FIFO method"""
        
        sale_quantity = transaction.quantity
        sale_price = transaction.price
        sale_date = transaction.transaction_date
        
        # Sort lots by acquisition date (FIFO)
        if self.method == TaxLotMethod.FIFO:
            sorted_lots = sorted(existing_lots, key=lambda lot: lot.acquisition_date)
        elif self.method == TaxLotMethod.LIFO:
            sorted_lots = sorted(existing_lots, key=lambda lot: lot.acquisition_date, reverse=True)
        else:
            sorted_lots = existing_lots  # Specific ID would need additional logic
        
        remaining_to_sell = sale_quantity
        updated_lots = []
        acquisition_lots = []
        total_cost_basis = Decimal('0')
        
        for lot in sorted_lots:
            if remaining_to_sell <= 0:
                # No more to sell, keep lot as-is
                updated_lots.append(lot)
                continue
            
            if lot.remaining_quantity <= 0:
                # Lot already closed
                updated_lots.append(lot)
                continue
            
            # Determine how much to sell from this lot
            quantity_from_lot = min(remaining_to_sell, lot.remaining_quantity)
            cost_from_lot = quantity_from_lot * lot.cost_per_share
            
            # Update lot
            lot.remaining_quantity -= quantity_from_lot
            if lot.remaining_quantity <= 0:
                lot.is_closed = True
            
            # Track for realized gain calculation
            acquisition_lots.append((lot.transaction_id, quantity_from_lot, cost_from_lot))
            total_cost_basis += cost_from_lot
            remaining_to_sell -= quantity_from_lot
            
            updated_lots.append(lot)
        
        # Calculate realized gain
        sale_proceeds = sale_quantity * sale_price
        realized_gain_amount = sale_proceeds - total_cost_basis
        gain_percentage = (realized_gain_amount / total_cost_basis * 100) if total_cost_basis > 0 else Decimal('0')
        
        # Determine holding period (use first lot for simplicity)
        first_acquisition_date = min(
            existing_lots, key=lambda lot: lot.acquisition_date
        ).acquisition_date if existing_lots else sale_date
        
        # Normalize datetimes to prevent timezone issues
        normalized_sale_date = _normalize_datetime(sale_date)
        normalized_acquisition_date = _normalize_datetime(first_acquisition_date)
        holding_days = (normalized_sale_date - normalized_acquisition_date).days
        is_long_term = holding_days >= 365  # 1 year for long-term capital gains
        
        realized_gain = RealizedGain(
            instrument_id=transaction.instrument_id,
            instrument_name="",  # Will be filled by caller
            sale_date=sale_date,
            sale_quantity=sale_quantity,
            sale_price=sale_price,
            sale_proceeds=sale_proceeds,
            cost_basis=total_cost_basis,
            cost_per_share=total_cost_basis / sale_quantity,
            realized_gain=realized_gain_amount,
            gain_percentage=gain_percentage,
            is_long_term=is_long_term,
            holding_period_days=holding_days,
            sale_transaction_id=transaction.id,
            acquisition_lots=acquisition_lots
        )
        
        self.logger.info(
            "Processed sale transaction",
            transaction_id=transaction.id,
            sale_quantity=str(sale_quantity),
            realized_gain=str(realized_gain_amount),
            is_long_term=is_long_term
        )
        
        return updated_lots, [realized_gain]
    
    def calculate_unrealized_gains(
        self,
        tax_lots: List[TaxLot],
        current_price: Decimal,
        valuation_date: datetime
    ) -> Dict[str, Decimal]:
        """Calculate unrealized gains for current holdings"""
        
        total_unrealized = Decimal('0')
        short_term_unrealized = Decimal('0')
        long_term_unrealized = Decimal('0')
        
        for lot in tax_lots:
            if lot.remaining_quantity <= 0:
                continue
            
            # Calculate unrealized gain for this lot
            current_value = lot.remaining_quantity * current_price
            cost_basis = lot.remaining_quantity * lot.cost_per_share
            unrealized_gain = current_value - cost_basis
            
            total_unrealized += unrealized_gain
            
            # Classify as short/long term
            # Normalize datetimes to prevent timezone issues
            normalized_valuation_date = _normalize_datetime(valuation_date)
            normalized_acquisition_date = _normalize_datetime(lot.acquisition_date)
            holding_days = (normalized_valuation_date - normalized_acquisition_date).days
            if holding_days >= 365:
                long_term_unrealized += unrealized_gain
            else:
                short_term_unrealized += unrealized_gain
        
        return {
            'total_unrealized': total_unrealized,
            'short_term_unrealized': short_term_unrealized,
            'long_term_unrealized': long_term_unrealized
        }


class PositionCalculator:
    """Calculates position metrics"""
    
    def __init__(self):
        self.logger = structlog.get_logger("PositionCalculator")
        self.tax_lot_manager = TaxLotManager()
    
    def calculate_position(
        self,
        transactions: List[Transaction],
        current_price: Optional[Decimal] = None,
        valuation_date: Optional[datetime] = None
    ) -> PositionSnapshot:
        """Calculate current position from transactions"""
        
        if not transactions:
            raise ValueError("No transactions provided")
        
        # Sort transactions by date
        sorted_transactions = sorted(transactions, key=lambda t: t.transaction_date)
        
        # Get instrument info from first transaction
        first_txn = sorted_transactions[0]
        instrument_id = first_txn.instrument_id
        
        # Process transactions to build position
        total_quantity = Decimal('0')
        total_cost = Decimal('0')
        tax_lots = []
        realized_gains = []
        
        for transaction in sorted_transactions:
            if transaction.transaction_type == TransactionType.BUY:
                total_quantity += transaction.quantity
                total_cost += transaction.net_amount or transaction.gross_amount
                
                # Update tax lots
                tax_lots, new_gains = self.tax_lot_manager.process_transaction(transaction, tax_lots)
                realized_gains.extend(new_gains)
                
            elif transaction.transaction_type == TransactionType.SELL:
                total_quantity -= transaction.quantity
                # Cost reduction handled in tax lot processing
                
                # Update tax lots
                tax_lots, new_gains = self.tax_lot_manager.process_transaction(transaction, tax_lots)
                realized_gains.extend(new_gains)
                
            elif transaction.transaction_type == TransactionType.DIVIDEND:
                # Dividends don't affect position quantity
                pass
        
        # Calculate average cost
        remaining_cost = sum(
            lot.remaining_quantity * lot.cost_per_share 
            for lot in tax_lots if lot.remaining_quantity > 0
        )
        
        average_cost = (remaining_cost / total_quantity) if total_quantity > 0 else Decimal('0')
        
        # Calculate current market value and P&L
        market_value = None
        unrealized_pnl = None
        
        if current_price and total_quantity > 0:
            market_value = total_quantity * current_price
            unrealized_pnl = market_value - remaining_cost
        
        # Convert tax lots to snapshots
        valuation_date = valuation_date or datetime.now()
        tax_lot_snapshots = []
        
        for lot in tax_lots:
            if lot.remaining_quantity > 0:
                holding_days = (valuation_date - lot.acquisition_date).days
                snapshot = TaxLotSnapshot(
                    acquisition_date=lot.acquisition_date,
                    quantity=lot.quantity,
                    remaining_quantity=lot.remaining_quantity,
                    cost_per_share=lot.cost_per_share,
                    total_cost=lot.remaining_quantity * lot.cost_per_share,
                    is_long_term=holding_days >= 365,
                    days_held=holding_days
                )
                tax_lot_snapshots.append(snapshot)
        
        position = PositionSnapshot(
            instrument_id=instrument_id,
            instrument_name=first_txn.instrument.name if first_txn.instrument else "",
            quantity=total_quantity,
            average_cost=average_cost,
            total_cost=remaining_cost,
            current_price=current_price,
            market_value=market_value,
            unrealized_pnl=unrealized_pnl,
            currency=first_txn.currency,
            tax_lots=tax_lot_snapshots
        )
        
        self.logger.info(
            "Calculated position",
            instrument_id=instrument_id,
            quantity=str(total_quantity),
            average_cost=str(average_cost),
            unrealized_pnl=str(unrealized_pnl) if unrealized_pnl else None
        )
        
        return position
    
    def calculate_portfolio_summary(
        self,
        positions: List[PositionSnapshot],
        base_currency: Currency = Currency.INR
    ) -> Dict[str, Decimal]:
        """Calculate portfolio-level summary metrics"""
        
        total_cost = Decimal('0')
        total_market_value = Decimal('0')
        total_unrealized_pnl = Decimal('0')
        
        asset_class_allocation = {}
        
        for position in positions:
            if position.quantity > 0:
                total_cost += position.total_cost
                
                if position.market_value:
                    total_market_value += position.market_value
                
                if position.unrealized_pnl:
                    total_unrealized_pnl += position.unrealized_pnl
        
        # Calculate overall return
        total_return_pct = Decimal('0')
        if total_cost > 0:
            total_return_pct = (total_unrealized_pnl / total_cost) * 100
        
        return {
            'total_positions': len(positions),
            'total_invested': total_cost,
            'current_value': total_market_value,
            'total_unrealized_pnl': total_unrealized_pnl,
            'total_return_percentage': total_return_pct,
            'base_currency': base_currency.value
        }
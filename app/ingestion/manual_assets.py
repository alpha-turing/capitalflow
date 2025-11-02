from typing import Dict, Any, Optional
from datetime import datetime
from decimal import Decimal
from dataclasses import dataclass
import structlog

from app.ingestion.base import ParsedTransaction
from app.db.models import TransactionType, Currency, AssetClass


@dataclass
class ManualAssetEntry:
    """Manual asset entry for gold and real estate"""
    
    # Asset details
    asset_name: str
    asset_class: AssetClass
    asset_type: str  # "physical_gold", "gold_etf", "residential", "commercial", etc.
    
    # Transaction details
    transaction_type: TransactionType
    transaction_date: datetime
    
    # Quantity and valuation
    quantity: Decimal  # grams for gold, sq_ft for real estate, etc.
    unit: str  # "grams", "sq_ft", "acres", etc.
    purchase_price_per_unit: Decimal
    total_purchase_price: Decimal
    
    # Current valuation (optional)
    current_price_per_unit: Optional[Decimal] = None
    current_market_value: Optional[Decimal] = None
    valuation_date: Optional[datetime] = None
    
    # Location/storage details
    location: Optional[str] = None
    storage_details: Optional[str] = None
    
    # Documentation
    purchase_document: Optional[str] = None
    certificate_number: Optional[str] = None
    
    # Additional costs
    registration_fees: Decimal = Decimal('0')
    stamp_duty: Decimal = Decimal('0')
    other_charges: Decimal = Decimal('0')
    
    # Currency
    currency: Currency = Currency.INR
    
    # Additional metadata
    notes: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class ManualAssetProcessor:
    """Processor for manual asset entries"""
    
    def __init__(self):
        self.logger = structlog.get_logger("ManualAssetProcessor")
        
        # Predefined valuation rules
        self.valuation_rules = {
            'physical_gold': {
                'valuation_source': 'market_rate',
                'benchmark': '24k_gold_rate',
                'adjustment_factor': 0.95,  # Purity adjustment
                'description': '24K gold rate with 5% purity discount'
            },
            'gold_etf': {
                'valuation_source': 'nav',
                'benchmark': 'gold_etf_nav',
                'adjustment_factor': 1.0,
                'description': 'ETF NAV based valuation'
            },
            'residential_property': {
                'valuation_source': 'guideline_value',
                'benchmark': 'govt_guideline_rate',
                'adjustment_factor': 1.1,  # Market premium
                'description': 'Government guideline value with 10% market premium'
            },
            'commercial_property': {
                'valuation_source': 'market_rate',
                'benchmark': 'commercial_property_rate',
                'adjustment_factor': 1.0,
                'description': 'Current market rate for commercial properties'
            }
        }
    
    def create_asset_transaction(self, asset_entry: ManualAssetEntry) -> ParsedTransaction:
        """Convert manual asset entry to standardized transaction"""
        
        # Calculate net amount including all charges
        net_amount = (
            asset_entry.total_purchase_price + 
            asset_entry.registration_fees + 
            asset_entry.stamp_duty + 
            asset_entry.other_charges
        )
        
        # Create instrument name
        instrument_name = self._create_instrument_name(asset_entry)
        
        # Create transaction
        transaction = ParsedTransaction(
            transaction_type=asset_entry.transaction_type,
            transaction_date=asset_entry.transaction_date,
            quantity=asset_entry.quantity,
            price=asset_entry.purchase_price_per_unit,
            gross_amount=asset_entry.total_purchase_price,
            instrument_name=instrument_name,
            brokerage=Decimal('0'),  # No brokerage for manual assets
            taxes=asset_entry.stamp_duty,  # Stamp duty as tax component
            other_charges=asset_entry.registration_fees + asset_entry.other_charges,
            net_amount=net_amount,
            currency=asset_entry.currency,
            exchange="MANUAL",
            source_reference=f"MANUAL-{asset_entry.asset_class.value}-{asset_entry.transaction_date.strftime('%Y%m%d')}",
            raw_data={
                'asset_class': asset_entry.asset_class.value,
                'asset_type': asset_entry.asset_type,
                'unit': asset_entry.unit,
                'location': asset_entry.location,
                'storage_details': asset_entry.storage_details,
                'purchase_document': asset_entry.purchase_document,
                'certificate_number': asset_entry.certificate_number,
                'notes': asset_entry.notes,
                'metadata': asset_entry.metadata,
                'current_valuation': {
                    'current_price_per_unit': str(asset_entry.current_price_per_unit) if asset_entry.current_price_per_unit else None,
                    'current_market_value': str(asset_entry.current_market_value) if asset_entry.current_market_value else None,
                    'valuation_date': asset_entry.valuation_date.isoformat() if asset_entry.valuation_date else None,
                }
            }
        )
        
        self.logger.info(
            "Created asset transaction",
            asset_name=asset_entry.asset_name,
            asset_class=asset_entry.asset_class.value,
            transaction_type=asset_entry.transaction_type.value,
            quantity=str(asset_entry.quantity),
            unit=asset_entry.unit
        )
        
        return transaction
    
    def _create_instrument_name(self, asset_entry: ManualAssetEntry) -> str:
        """Create a standardized instrument name for manual assets"""
        
        if asset_entry.asset_class == AssetClass.COMMODITY:
            if 'gold' in asset_entry.asset_type.lower():
                return f"Gold ({asset_entry.asset_type}) - {asset_entry.location or 'Physical'}"
            else:
                return f"{asset_entry.asset_name} ({asset_entry.asset_type})"
        
        elif asset_entry.asset_class == AssetClass.REAL_ESTATE:
            location_part = f" - {asset_entry.location}" if asset_entry.location else ""
            return f"{asset_entry.asset_name} ({asset_entry.asset_type}){location_part}"
        
        else:
            return f"{asset_entry.asset_name} ({asset_entry.asset_type})"
    
    def get_valuation_rule(self, asset_type: str) -> Optional[Dict[str, Any]]:
        """Get valuation rule for asset type"""
        return self.valuation_rules.get(asset_type)
    
    def calculate_current_value(
        self, 
        asset_entry: ManualAssetEntry, 
        current_rate_per_unit: Decimal
    ) -> Dict[str, Any]:
        """Calculate current market value based on valuation rules"""
        
        valuation_rule = self.get_valuation_rule(asset_entry.asset_type)
        
        if not valuation_rule:
            # No specific rule, use direct calculation
            current_value = asset_entry.quantity * current_rate_per_unit
        else:
            # Apply adjustment factor from valuation rule
            adjusted_rate = current_rate_per_unit * Decimal(str(valuation_rule['adjustment_factor']))
            current_value = asset_entry.quantity * adjusted_rate
        
        # Calculate gain/loss
        total_cost = (
            asset_entry.total_purchase_price + 
            asset_entry.registration_fees + 
            asset_entry.stamp_duty + 
            asset_entry.other_charges
        )
        
        unrealized_gain = current_value - total_cost
        gain_percentage = (unrealized_gain / total_cost * 100) if total_cost > 0 else Decimal('0')
        
        result = {
            'current_rate_per_unit': current_rate_per_unit,
            'adjusted_rate_per_unit': adjusted_rate if valuation_rule else current_rate_per_unit,
            'current_market_value': current_value,
            'total_cost': total_cost,
            'unrealized_gain': unrealized_gain,
            'gain_percentage': gain_percentage,
            'valuation_method': valuation_rule['description'] if valuation_rule else 'Direct market rate',
            'valuation_date': datetime.now()
        }
        
        self.logger.info(
            "Calculated asset valuation",
            asset_name=asset_entry.asset_name,
            current_value=str(current_value),
            unrealized_gain=str(unrealized_gain),
            gain_percentage=str(gain_percentage)
        )
        
        return result
    
    def validate_asset_entry(self, asset_entry: ManualAssetEntry) -> bool:
        """Validate manual asset entry"""
        
        if not asset_entry.asset_name or not asset_entry.asset_name.strip():
            self.logger.warning("Asset name is required")
            return False
        
        if asset_entry.quantity <= 0:
            self.logger.warning("Quantity must be positive", quantity=str(asset_entry.quantity))
            return False
        
        if asset_entry.purchase_price_per_unit <= 0:
            self.logger.warning("Purchase price per unit must be positive", price=str(asset_entry.purchase_price_per_unit))
            return False
        
        if asset_entry.total_purchase_price <= 0:
            self.logger.warning("Total purchase price must be positive", total=str(asset_entry.total_purchase_price))
            return False
        
        # Validate that total price matches quantity * unit price (with some tolerance)
        expected_total = asset_entry.quantity * asset_entry.purchase_price_per_unit
        tolerance = abs(expected_total * Decimal('0.01'))  # 1% tolerance
        
        if abs(asset_entry.total_purchase_price - expected_total) > tolerance:
            self.logger.warning(
                "Total purchase price doesn't match quantity * unit price",
                expected=str(expected_total),
                actual=str(asset_entry.total_purchase_price),
                tolerance=str(tolerance)
            )
            return False
        
        return True


# Create global processor instance
manual_asset_processor = ManualAssetProcessor()
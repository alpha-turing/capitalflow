from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from datetime import datetime
from decimal import Decimal
import structlog
from dataclasses import dataclass

from app.db.models import TransactionType, Currency


@dataclass
class ParsedTransaction:
    """Standardized transaction data from parsers"""
    
    # Required fields first
    transaction_type: TransactionType
    transaction_date: datetime
    quantity: Decimal
    price: Decimal
    gross_amount: Decimal
    instrument_name: str
    
    # Optional fields with defaults
    symbol: Optional[str] = None
    isin: Optional[str] = None
    amfi_code: Optional[str] = None
    cusip: Optional[str] = None
    settlement_date: Optional[datetime] = None
    brokerage: Decimal = Decimal('0')
    taxes: Decimal = Decimal('0')
    other_charges: Decimal = Decimal('0')
    net_amount: Optional[Decimal] = None
    currency: Currency = Currency.INR
    exchange: Optional[str] = None
    source_reference: Optional[str] = None
    raw_data: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        """Calculate net amount if not provided"""
        if self.net_amount is None:
            if self.transaction_type == TransactionType.BUY:
                self.net_amount = self.gross_amount + self.brokerage + self.taxes + self.other_charges
            else:  # SELL or others
                self.net_amount = self.gross_amount - self.brokerage - self.taxes - self.other_charges


@dataclass 
class ParsedHolding:
    """Standardized holding data from CAS statements"""
    
    # Required fields first
    folio_number: str
    scheme_name: str
    units: Decimal
    nav: Decimal
    market_value: Decimal
    valuation_date: datetime
    
    # Optional fields with defaults
    amfi_code: Optional[str] = None
    isin: Optional[str] = None
    nominee: Optional[str] = None
    pan: Optional[str] = None
    raw_data: Optional[Dict[str, Any]] = None


class BaseParser(ABC):
    """Base class for all file parsers"""
    
    def __init__(self):
        self.logger = structlog.get_logger(self.__class__.__name__)
    
    @abstractmethod
    def can_parse(self, file_content: bytes, filename: str) -> bool:
        """Check if this parser can handle the given file"""
        pass
    
    @abstractmethod
    def parse_transactions(self, file_content: bytes, filename: str) -> List[ParsedTransaction]:
        """Parse transactions from file content"""
        pass
    
    def parse_holdings(self, file_content: bytes, filename: str) -> List[ParsedHolding]:
        """Parse holdings from file content (optional)"""
        return []
    
    def validate_transaction(self, transaction: ParsedTransaction) -> bool:
        """Validate a parsed transaction"""
        if not transaction.instrument_name:
            self.logger.warning("Transaction missing instrument name", transaction=transaction)
            return False
        
        if transaction.quantity <= 0:
            self.logger.warning("Invalid quantity", quantity=transaction.quantity)
            return False
        
        if transaction.price <= 0:
            self.logger.warning("Invalid price", price=transaction.price)
            return False
        
        return True


class ParserFactory:
    """Factory for creating appropriate parsers"""
    
    def __init__(self):
        self._parsers = []
        self.logger = structlog.get_logger("ParserFactory")
    
    def register_parser(self, parser: BaseParser):
        """Register a new parser"""
        self._parsers.append(parser)
        self.logger.info("Registered parser", parser_class=parser.__class__.__name__)
    
    def get_parser(self, file_content: bytes, filename: str) -> Optional[BaseParser]:
        """Get appropriate parser for file"""
        for parser in self._parsers:
            if parser.can_parse(file_content, filename):
                self.logger.info("Found parser", parser_class=parser.__class__.__name__, filename=filename)
                return parser
        
        self.logger.warning("No parser found for file", filename=filename)
        return None


# Global parser factory instance
parser_factory = ParserFactory()
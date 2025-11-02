from sqlalchemy import String, Numeric, DateTime, Date, Boolean, Text, Enum, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB
from decimal import Decimal
from datetime import datetime, date
from typing import Optional, List
import enum

from app.core.database import Base


class AssetClass(str, enum.Enum):
    """Asset class enumeration"""
    EQUITY = "equity"
    MUTUAL_FUND = "mutual_fund"
    BOND = "bond"
    COMMODITY = "commodity"
    REAL_ESTATE = "real_estate"
    CASH = "cash"
    CRYPTOCURRENCY = "cryptocurrency"


class Currency(str, enum.Enum):
    """Currency enumeration"""
    INR = "INR"
    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"


class Exchange(str, enum.Enum):
    """Exchange enumeration"""
    NSE = "NSE"
    BSE = "BSE"
    NASDAQ = "NASDAQ"
    NYSE = "NYSE"
    MANUAL = "MANUAL"


class TransactionType(str, enum.Enum):
    """Transaction type enumeration"""
    BUY = "buy"
    SELL = "sell"
    DIVIDEND = "dividend"
    INTEREST = "interest"
    BONUS = "bonus"
    SPLIT = "split"
    SPIN_OFF = "spin_off"


class CorporateActionType(str, enum.Enum):
    """Corporate action type enumeration"""
    DIVIDEND = "dividend"
    STOCK_SPLIT = "stock_split"
    BONUS = "bonus"
    RIGHTS = "rights"
    SPIN_OFF = "spin_off"
    MERGER = "merger"


class CorporateActionStatus(str, enum.Enum):
    """Corporate action status enumeration"""
    PENDING = "pending"
    APPROVED = "approved"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    MERGER = "merger"
    RIGHTS = "rights"


class User(Base):
    """User model"""
    __tablename__ = "users"
    
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Relationships
    portfolios: Mapped[List["Portfolio"]] = relationship("Portfolio", back_populates="user")
    uploads: Mapped[List["FileUpload"]] = relationship("FileUpload", back_populates="user")


class Portfolio(Base):
    """Portfolio model"""
    __tablename__ = "portfolios"
    
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text)
    base_currency: Mapped[str] = mapped_column(String(3), default="INR")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="portfolios")
    positions: Mapped[List["Position"]] = relationship("Position", back_populates="portfolio")
    transactions: Mapped[List["Transaction"]] = relationship("Transaction", back_populates="portfolio")


class Instrument(Base):
    """Instrument model for canonical instrument mapping"""
    __tablename__ = "instruments"
    
    # Canonical identifier
    canonical_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    
    # Basic info
    name: Mapped[str] = mapped_column(String(255))
    asset_class: Mapped[AssetClass] = mapped_column(Enum(AssetClass))
    currency: Mapped[Currency] = mapped_column(Enum(Currency))
    
    # Identifiers
    isin: Mapped[Optional[str]] = mapped_column(String(20), index=True)
    amfi_code: Mapped[Optional[str]] = mapped_column(String(20), index=True)
    cusip: Mapped[Optional[str]] = mapped_column(String(20), index=True)
    
    # Exchange info
    primary_exchange: Mapped[Optional[Exchange]] = mapped_column(Enum(Exchange))
    symbol: Mapped[Optional[str]] = mapped_column(String(50))
    
    # Additional metadata
    sector: Mapped[Optional[str]] = mapped_column(String(100))
    industry: Mapped[Optional[str]] = mapped_column(String(100))
    country: Mapped[str] = mapped_column(String(3), default="IN")
    
    # Pricing info
    face_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 4))
    lot_size: Mapped[int] = mapped_column(default=1)
    
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Relationships
    prices: Mapped[List["Price"]] = relationship("Price", back_populates="instrument")
    positions: Mapped[List["Position"]] = relationship("Position", back_populates="instrument")
    transactions: Mapped[List["Transaction"]] = relationship("Transaction", back_populates="instrument")
    corporate_actions: Mapped[List["CorporateAction"]] = relationship("CorporateAction", back_populates="instrument")
    
    __table_args__ = (
        Index("idx_instrument_isin", "isin"),
        Index("idx_instrument_amfi", "amfi_code"),
        Index("idx_instrument_cusip", "cusip"),
        Index("idx_instrument_symbol_exchange", "symbol", "primary_exchange"),
    )


class Price(Base):
    """Price model for storing historical prices"""
    __tablename__ = "prices"
    
    instrument_id: Mapped[str] = mapped_column(String(36), ForeignKey("instruments.id"))
    price_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    
    # Price data
    open_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 4))
    high_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 4))
    low_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 4))
    close_price: Mapped[Decimal] = mapped_column(Numeric(15, 4))
    volume: Mapped[Optional[int]] = mapped_column()
    
    # Adjusted prices (for corporate actions)
    adj_close_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 4))
    
    # Data source
    source: Mapped[str] = mapped_column(String(50))
    
    # Relationships
    instrument: Mapped["Instrument"] = relationship("Instrument", back_populates="prices")
    
    __table_args__ = (
        Index("idx_price_instrument_date", "instrument_id", "price_date"),
    )


class Transaction(Base):
    """Transaction model for all financial transactions"""
    __tablename__ = "transactions"
    
    portfolio_id: Mapped[str] = mapped_column(String(36), ForeignKey("portfolios.id"))
    instrument_id: Mapped[str] = mapped_column(String(36), ForeignKey("instruments.id"))
    
    # Transaction details
    transaction_type: Mapped[TransactionType] = mapped_column(Enum(TransactionType))
    transaction_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    settlement_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Quantities and prices
    quantity: Mapped[Decimal] = mapped_column(Numeric(15, 4))
    price: Mapped[Decimal] = mapped_column(Numeric(15, 4))
    gross_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2))
    
    # Costs and fees
    brokerage: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0)
    taxes: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0)
    other_charges: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0)
    net_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2))
    
    # Currency and FX
    currency: Mapped[Currency] = mapped_column(Enum(Currency))
    fx_rate: Mapped[Decimal] = mapped_column(Numeric(15, 6), default=1.0)  # To base currency
    
    # Source information
    source_file_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("file_uploads.id"))
    source_reference: Mapped[Optional[str]] = mapped_column(String(100))  # Reference from source file
    
    # Additional metadata
    notes: Mapped[Optional[str]] = mapped_column(Text)
    extra_data: Mapped[Optional[dict]] = mapped_column(JSONB)
    
    # Relationships
    portfolio: Mapped["Portfolio"] = relationship("Portfolio", back_populates="transactions")
    instrument: Mapped["Instrument"] = relationship("Instrument", back_populates="transactions")
    source_file: Mapped[Optional["FileUpload"]] = relationship("FileUpload", back_populates="transactions")
    tax_lots: Mapped[List["TaxLot"]] = relationship("TaxLot", back_populates="transaction")
    
    __table_args__ = (
        Index("idx_transaction_portfolio_date", "portfolio_id", "transaction_date"),
        Index("idx_transaction_instrument", "instrument_id"),
    )


class Position(Base):
    """Position model for current holdings"""
    __tablename__ = "positions"
    
    portfolio_id: Mapped[str] = mapped_column(String(36), ForeignKey("portfolios.id"))
    instrument_id: Mapped[str] = mapped_column(String(36), ForeignKey("instruments.id"))
    
    # Position data
    quantity: Mapped[Decimal] = mapped_column(Numeric(15, 4))
    average_cost: Mapped[Decimal] = mapped_column(Numeric(15, 4))
    total_cost: Mapped[Decimal] = mapped_column(Numeric(15, 2))
    
    # Current valuation
    current_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 4))
    market_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2))
    unrealized_pnl: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2))
    
    # Currency
    currency: Mapped[Currency] = mapped_column(Enum(Currency))
    
    # Last update
    last_updated: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    
    # Relationships
    portfolio: Mapped["Portfolio"] = relationship("Portfolio", back_populates="positions")
    instrument: Mapped["Instrument"] = relationship("Instrument", back_populates="positions")
    tax_lots: Mapped[List["TaxLot"]] = relationship("TaxLot", back_populates="position")
    
    __table_args__ = (
        Index("idx_position_portfolio", "portfolio_id"),
        Index("idx_position_unique", "portfolio_id", "instrument_id", unique=True),
    )


class TaxLot(Base):
    """Tax lot model for FIFO tracking"""
    __tablename__ = "tax_lots"
    
    position_id: Mapped[str] = mapped_column(String(36), ForeignKey("positions.id"))
    transaction_id: Mapped[str] = mapped_column(String(36), ForeignKey("transactions.id"))
    
    # Lot details
    quantity: Mapped[Decimal] = mapped_column(Numeric(15, 4))
    remaining_quantity: Mapped[Decimal] = mapped_column(Numeric(15, 4))
    cost_per_share: Mapped[Decimal] = mapped_column(Numeric(15, 4))
    acquisition_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    
    # Status
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Relationships
    position: Mapped["Position"] = relationship("Position", back_populates="tax_lots")
    transaction: Mapped["Transaction"] = relationship("Transaction", back_populates="tax_lots")
    
    __table_args__ = (
        Index("idx_tax_lot_position", "position_id"),
    )


class CorporateAction(Base):
    """Corporate action model"""
    __tablename__ = "corporate_actions"
    
    instrument_id: Mapped[str] = mapped_column(String(36), ForeignKey("instruments.id"))
    
    # Action details
    action_type: Mapped[CorporateActionType] = mapped_column(Enum(CorporateActionType))
    status: Mapped[CorporateActionStatus] = mapped_column(Enum(CorporateActionStatus), default=CorporateActionStatus.PENDING)
    ex_date: Mapped[date] = mapped_column(Date)
    record_date: Mapped[Optional[date]] = mapped_column(Date)
    payment_date: Mapped[Optional[date]] = mapped_column(Date)
    
    # Action parameters (for splits and bonus issues)
    ratio_old: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 4))  # Old ratio (e.g., 1 for 1:2 split)
    ratio_new: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 4))  # New ratio (e.g., 2 for 1:2 split)
    
    # Cash amount (for dividends)
    cash_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 4))
    
    # Description and metadata
    description: Mapped[Optional[str]] = mapped_column(Text)
    created_by: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id"))
    
    # Relationships
    instrument: Mapped["Instrument"] = relationship("Instrument", back_populates="corporate_actions")
    
    __table_args__ = (
        Index("idx_corporate_action_instrument", "instrument_id"),
        Index("idx_corporate_action_ex_date", "ex_date"),
    )


class FileUpload(Base):
    """File upload model for tracking processed files"""
    __tablename__ = "file_uploads"
    
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    
    # File details
    filename: Mapped[str] = mapped_column(String(255))
    original_filename: Mapped[str] = mapped_column(String(255))
    file_type: Mapped[str] = mapped_column(String(50))  # pdf, csv, excel
    file_size: Mapped[int] = mapped_column()
    
    # Processing status
    status: Mapped[str] = mapped_column(String(50), default="uploaded")  # uploaded, processing, completed, failed
    processed_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Results
    transactions_imported: Mapped[int] = mapped_column(default=0)
    errors: Mapped[Optional[List[str]]] = mapped_column(JSONB)
    
    # Source classification
    source_type: Mapped[str] = mapped_column(String(50))  # icici_direct, cams, kfin, vested, manual
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="uploads")
    transactions: Mapped[List["Transaction"]] = relationship("Transaction", back_populates="source_file")
    
    __table_args__ = (
        Index("idx_file_upload_user", "user_id"),
        Index("idx_file_upload_status", "status"),
    )


class ExchangeRate(Base):
    """Exchange rate model for currency conversions"""
    __tablename__ = "exchange_rates"
    
    # Currency pair
    from_currency: Mapped[Currency] = mapped_column(Enum(Currency))
    to_currency: Mapped[Currency] = mapped_column(Enum(Currency))
    
    # Rate data
    rate_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    rate: Mapped[Decimal] = mapped_column(Numeric(15, 6))
    
    # Source
    source: Mapped[str] = mapped_column(String(50))
    
    __table_args__ = (
        Index("idx_exchange_rate_pair_date", "from_currency", "to_currency", "rate_date"),
    )


class AuditLog(Base):
    """Audit log model for tracking all system activities"""
    __tablename__ = "audit_logs"
    
    # User context
    user_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id"))
    session_id: Mapped[Optional[str]] = mapped_column(String(255))
    
    # Action details
    action: Mapped[str] = mapped_column(String(100))
    entity_type: Mapped[Optional[str]] = mapped_column(String(50))
    entity_id: Mapped[Optional[str]] = mapped_column(String(36))
    
    # Request context
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))
    user_agent: Mapped[Optional[str]] = mapped_column(Text)
    
    # Changes (for data modifications)
    old_values: Mapped[Optional[dict]] = mapped_column(JSONB)
    new_values: Mapped[Optional[dict]] = mapped_column(JSONB)
    
    # Additional context
    extra_metadata: Mapped[Optional[dict]] = mapped_column(JSONB)
    
    __table_args__ = (
        Index("idx_audit_log_user", "user_id"),
        Index("idx_audit_log_action", "action"),
        Index("idx_audit_log_date", "created_at"),
    )


class ConsentLog(Base):
    """Consent log model for tracking user consents"""
    __tablename__ = "consent_logs"
    
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    
    # Consent details
    consent_type: Mapped[str] = mapped_column(String(100))
    consent_text: Mapped[str] = mapped_column(Text)
    version: Mapped[str] = mapped_column(String(20))
    
    # User action
    consented: Mapped[bool] = mapped_column(Boolean)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))
    
    __table_args__ = (
        Index("idx_consent_log_user", "user_id"),
        Index("idx_consent_log_type", "consent_type"),
    )
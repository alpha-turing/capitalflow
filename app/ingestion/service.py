from typing import List, Optional, Dict, Any
from datetime import datetime
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.ingestion.base import ParsedTransaction, ParsedHolding, parser_factory
from app.ingestion.manual_assets import ManualAssetEntry, manual_asset_processor
from app.db.models import FileUpload, Transaction, User, Portfolio, Instrument
from app.core.database import get_db


class IngestionService:
    """Service for processing file uploads and manual entries"""
    
    def __init__(self):
        self.logger = structlog.get_logger("IngestionService")
    
    async def process_file_upload(
        self,
        db: AsyncSession,
        user_id: str,
        portfolio_id: str,
        file_content: bytes,
        filename: str,
        file_type: str
    ) -> Dict[str, Any]:
        """Process uploaded file and extract transactions"""
        
        # Create file upload record
        file_upload = FileUpload(
            user_id=user_id,
            filename=f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{filename}",
            original_filename=filename,
            file_type=file_type,
            file_size=len(file_content),
            status="processing",
            source_type="unknown"  # Will be updated when parser is determined
        )
        
        db.add(file_upload)
        await db.flush()
        
        try:
            # Find appropriate parser
            parser = parser_factory.get_parser(file_content, filename)
            
            if not parser:
                file_upload.status = "failed"
                file_upload.errors = ["No suitable parser found for this file type"]
                await db.commit()
                
                return {
                    "success": False,
                    "error": "Unsupported file format",
                    "file_upload_id": file_upload.id
                }
            
            # Determine source type based on parser
            source_type = self._get_source_type(parser)
            file_upload.source_type = source_type
            
            # Parse transactions
            parsed_transactions = parser.parse_transactions(file_content, filename)
            
            # Parse holdings if supported
            parsed_holdings = []
            if hasattr(parser, 'parse_holdings'):
                parsed_holdings = parser.parse_holdings(file_content, filename)
            
            # Convert and save transactions
            saved_transactions = []
            errors = []
            
            for parsed_txn in parsed_transactions:
                try:
                    # Find or create instrument
                    instrument = await self._find_or_create_instrument(db, parsed_txn)
                    
                    # Create transaction record
                    transaction = await self._create_transaction_record(
                        db, parsed_txn, portfolio_id, instrument.id, file_upload.id
                    )
                    
                    saved_transactions.append(transaction)
                    
                except Exception as e:
                    error_msg = f"Failed to process transaction: {str(e)}"
                    errors.append(error_msg)
                    self.logger.error("Transaction processing error", error=error_msg, transaction=parsed_txn)
            
            # Update file upload status
            file_upload.status = "completed" if not errors else "partial"
            file_upload.transactions_imported = len(saved_transactions)
            file_upload.errors = errors if errors else None
            file_upload.processed_date = datetime.now()
            
            await db.commit()
            
            self.logger.info(
                "File processing completed",
                file_id=file_upload.id,
                filename=filename,
                transactions_imported=len(saved_transactions),
                errors_count=len(errors),
                holdings_parsed=len(parsed_holdings)
            )
            
            return {
                "success": True,
                "file_upload_id": file_upload.id,
                "transactions_imported": len(saved_transactions),
                "holdings_parsed": len(parsed_holdings),
                "errors": errors,
                "source_type": source_type
            }
            
        except Exception as e:
            # Update file upload with error
            file_upload.status = "failed"
            file_upload.errors = [str(e)]
            await db.commit()
            
            self.logger.error("File processing failed", filename=filename, error=str(e))
            
            return {
                "success": False,
                "error": str(e),
                "file_upload_id": file_upload.id
            }
    
    async def process_manual_asset(
        self,
        db: AsyncSession,
        user_id: str,
        portfolio_id: str,
        asset_entry: ManualAssetEntry
    ) -> Dict[str, Any]:
        """Process manual asset entry"""
        
        try:
            # Validate asset entry
            if not manual_asset_processor.validate_asset_entry(asset_entry):
                return {
                    "success": False,
                    "error": "Invalid asset entry data"
                }
            
            # Convert to parsed transaction
            parsed_transaction = manual_asset_processor.create_asset_transaction(asset_entry)
            
            # Find or create instrument
            instrument = await self._find_or_create_instrument(db, parsed_transaction)
            
            # Create transaction record
            transaction = await self._create_transaction_record(
                db, parsed_transaction, portfolio_id, instrument.id, None
            )
            
            await db.commit()
            
            self.logger.info(
                "Manual asset processed",
                asset_name=asset_entry.asset_name,
                asset_class=asset_entry.asset_class.value,
                transaction_id=transaction.id
            )
            
            return {
                "success": True,
                "transaction_id": transaction.id,
                "instrument_id": instrument.id
            }
            
        except Exception as e:
            await db.rollback()
            self.logger.error("Manual asset processing failed", error=str(e))
            
            return {
                "success": False,
                "error": str(e)
            }
    
    def _get_source_type(self, parser) -> str:
        """Get source type based on parser class"""
        parser_class_name = parser.__class__.__name__
        
        mapping = {
            'ICICIDirectParser': 'icici_direct',
            'CASParser': 'cas',
            'VestedCSVParser': 'vested',
        }
        
        return mapping.get(parser_class_name, 'unknown')
    
    async def _find_or_create_instrument(
        self, 
        db: AsyncSession, 
        parsed_txn: ParsedTransaction
    ) -> Instrument:
        """Find existing instrument or create new one"""
        
        # Try to find by identifiers (ISIN, AMFI code, CUSIP)
        instrument = None
        
        if parsed_txn.isin:
            result = await db.execute(
                text("SELECT * FROM instruments WHERE isin = :isin"),
                {"isin": parsed_txn.isin}
            )
            instrument = result.fetchone()
        
        if not instrument and parsed_txn.amfi_code:
            result = await db.execute(
                text("SELECT * FROM instruments WHERE amfi_code = :amfi_code"),
                {"amfi_code": parsed_txn.amfi_code}
            )
            instrument = result.fetchone()
        
        if not instrument and parsed_txn.cusip:
            result = await db.execute(
                text("SELECT * FROM instruments WHERE cusip = :cusip"),
                {"cusip": parsed_txn.cusip}
            )
            instrument = result.fetchone()
        
        # If not found, try by symbol and exchange
        if not instrument and parsed_txn.symbol and parsed_txn.exchange:
            result = await db.execute(
                text("SELECT * FROM instruments WHERE symbol = :symbol AND primary_exchange = :exchange"),
                {"symbol": parsed_txn.symbol, "exchange": parsed_txn.exchange}
            )
            instrument = result.fetchone()
        
        # If still not found, create new instrument
        if not instrument:
            instrument = await self._create_instrument_record(db, parsed_txn)
        
        return instrument
    
    async def _create_instrument_record(
        self, 
        db: AsyncSession, 
        parsed_txn: ParsedTransaction
    ) -> Instrument:
        """Create new instrument record"""
        
        # Generate canonical ID
        canonical_id = self._generate_canonical_id(parsed_txn)
        
        # Determine asset class
        asset_class = self._determine_asset_class(parsed_txn)
        
        instrument = Instrument(
            canonical_id=canonical_id,
            name=parsed_txn.instrument_name,
            asset_class=asset_class,
            currency=parsed_txn.currency,
            isin=parsed_txn.isin,
            amfi_code=parsed_txn.amfi_code,
            cusip=parsed_txn.cusip,
            symbol=parsed_txn.symbol,
            primary_exchange=parsed_txn.exchange,
            lot_size=1  # Default lot size
        )
        
        db.add(instrument)
        await db.flush()
        
        return instrument
    
    def _generate_canonical_id(self, parsed_txn: ParsedTransaction) -> str:
        """Generate canonical ID for instrument"""
        if parsed_txn.isin:
            return f"ISIN:{parsed_txn.isin}"
        elif parsed_txn.amfi_code:
            return f"AMFI:{parsed_txn.amfi_code}"
        elif parsed_txn.cusip:
            return f"CUSIP:{parsed_txn.cusip}"
        elif parsed_txn.symbol and parsed_txn.exchange:
            return f"{parsed_txn.exchange}:{parsed_txn.symbol}"
        else:
            # Generate hash-based ID for manual assets
            import hashlib
            name_hash = hashlib.md5(parsed_txn.instrument_name.encode()).hexdigest()[:8]
            return f"MANUAL:{name_hash}"
    
    def _determine_asset_class(self, parsed_txn: ParsedTransaction) -> str:
        """Determine asset class from parsed transaction"""
        
        # Check raw data for asset class
        if parsed_txn.raw_data and 'asset_class' in parsed_txn.raw_data:
            return parsed_txn.raw_data['asset_class']
        
        # Determine from identifiers and context
        if parsed_txn.amfi_code or 'fund' in parsed_txn.instrument_name.lower():
            return 'mutual_fund'
        elif parsed_txn.cusip or parsed_txn.exchange in ['NASDAQ', 'NYSE']:
            return 'equity'
        elif parsed_txn.exchange == 'MANUAL':
            if 'gold' in parsed_txn.instrument_name.lower():
                return 'commodity'
            elif any(word in parsed_txn.instrument_name.lower() for word in ['property', 'real estate', 'land']):
                return 'real_estate'
            else:
                return 'other'
        else:
            return 'equity'  # Default
    
    async def _create_transaction_record(
        self,
        db: AsyncSession,
        parsed_txn: ParsedTransaction,
        portfolio_id: str,
        instrument_id: str,
        file_upload_id: Optional[str]
    ) -> Transaction:
        """Create transaction database record"""
        
        transaction = Transaction(
            portfolio_id=portfolio_id,
            instrument_id=instrument_id,
            transaction_type=parsed_txn.transaction_type,
            transaction_date=parsed_txn.transaction_date,
            settlement_date=parsed_txn.settlement_date,
            quantity=parsed_txn.quantity,
            price=parsed_txn.price,
            gross_amount=parsed_txn.gross_amount,
            brokerage=parsed_txn.brokerage,
            taxes=parsed_txn.taxes,
            other_charges=parsed_txn.other_charges,
            net_amount=parsed_txn.net_amount,
            currency=parsed_txn.currency,
            fx_rate=1.0,  # Will be updated by FX service
            source_file_id=file_upload_id,
            source_reference=parsed_txn.source_reference,
            notes=parsed_txn.raw_data.get('notes') if parsed_txn.raw_data else None,
            metadata=parsed_txn.raw_data
        )
        
        db.add(transaction)
        await db.flush()
        
        return transaction


# Create global service instance
ingestion_service = IngestionService()
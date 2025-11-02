from typing import List, Dict, Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import structlog

from app.canonicalization.canonicalizer import (
    InstrumentCanonicalizer, 
    InstrumentIdentifier, 
    IdentifierType,
    CanonicalInstrument
)
from app.db.models import Instrument, AssetClass, Currency, Exchange


class InstrumentMappingService:
    """Service for managing instrument mappings and canonicalization"""
    
    def __init__(self):
        self.logger = structlog.get_logger("InstrumentMappingService")
        self.canonicalizer = InstrumentCanonicalizer()
    
    async def find_or_create_instrument(
        self,
        db: AsyncSession,
        name: str,
        identifiers: Dict[str, Optional[str]],  # {isin: "...", symbol: "...", etc}
        asset_class: AssetClass,
        currency: Currency,
        exchange: Optional[str] = None
    ) -> Instrument:
        """Find existing instrument or create new canonical one"""
        
        # Convert identifiers to structured format
        structured_identifiers = self._parse_identifiers(identifiers, exchange)
        
        # Load existing instruments for matching
        existing_canonical = await self._load_existing_instruments(db, structured_identifiers)
        
        # Canonicalize
        exchange_enum = self._parse_exchange(exchange) if exchange else None
        canonical_instrument = self.canonicalizer.canonicalize(
            name=name,
            identifiers=structured_identifiers,
            asset_class=asset_class,
            currency=currency,
            existing_instruments=existing_canonical,
            exchange=exchange_enum
        )
        
        # Check if instrument already exists in database
        existing_instrument = await self._find_existing_db_instrument(db, canonical_instrument)
        
        if existing_instrument:
            # Update existing instrument with new identifiers if needed
            await self._update_instrument_identifiers(db, existing_instrument, structured_identifiers)
            return existing_instrument
        
        # Create new instrument in database
        new_instrument = await self._create_db_instrument(db, canonical_instrument)
        
        self.logger.info(
            "Created new instrument",
            canonical_id=canonical_instrument.canonical_id,
            name=name,
            asset_class=asset_class.value
        )
        
        return new_instrument
    
    async def resolve_instrument_conflicts(
        self,
        db: AsyncSession,
        conflicting_instruments: List[Instrument]
    ) -> Instrument:
        """Resolve conflicts between multiple instruments that should be the same"""
        
        if len(conflicting_instruments) <= 1:
            return conflicting_instruments[0] if conflicting_instruments else None
        
        # Choose the best instrument (e.g., most identifiers, oldest, etc.)
        primary_instrument = self._choose_primary_instrument(conflicting_instruments)
        
        # Merge identifiers from other instruments
        for instrument in conflicting_instruments:
            if instrument.id != primary_instrument.id:
                await self._merge_instrument_identifiers(db, primary_instrument, instrument)
        
        self.logger.info(
            "Resolved instrument conflicts",
            primary_id=primary_instrument.id,
            merged_count=len(conflicting_instruments) - 1
        )
        
        return primary_instrument
    
    async def update_instrument_mapping(
        self,
        db: AsyncSession,
        instrument_id: str,
        new_identifiers: Dict[str, str]
    ) -> bool:
        """Update instrument with new identifier mappings"""
        
        instrument = await db.get(Instrument, instrument_id)
        if not instrument:
            return False
        
        # Add new identifiers
        for identifier_type, value in new_identifiers.items():
            if identifier_type == "isin" and value and not instrument.isin:
                instrument.isin = value
            elif identifier_type == "amfi_code" and value and not instrument.amfi_code:
                instrument.amfi_code = value
            elif identifier_type == "cusip" and value and not instrument.cusip:
                instrument.cusip = value
            elif identifier_type == "symbol" and value and not instrument.symbol:
                instrument.symbol = value
        
        await db.commit()
        
        self.logger.info(
            "Updated instrument mappings",
            instrument_id=instrument_id,
            new_identifiers=new_identifiers
        )
        
        return True
    
    def _parse_identifiers(
        self, 
        identifiers: Dict[str, Optional[str]], 
        exchange: Optional[str]
    ) -> List[InstrumentIdentifier]:
        """Parse identifier dictionary into structured format"""
        
        structured = []
        
        if identifiers.get("isin"):
            structured.append(InstrumentIdentifier(
                identifier_type=IdentifierType.ISIN,
                value=identifiers["isin"],
                country="IN" if identifiers["isin"].startswith("IN") else None
            ))
        
        if identifiers.get("amfi_code"):
            structured.append(InstrumentIdentifier(
                identifier_type=IdentifierType.AMFI_CODE,
                value=identifiers["amfi_code"]
            ))
        
        if identifiers.get("cusip"):
            structured.append(InstrumentIdentifier(
                identifier_type=IdentifierType.CUSIP,
                value=identifiers["cusip"],
                country="US"
            ))
        
        if identifiers.get("symbol"):
            structured.append(InstrumentIdentifier(
                identifier_type=IdentifierType.SYMBOL,
                value=identifiers["symbol"],
                exchange=exchange
            ))
        
        return structured
    
    def _parse_exchange(self, exchange_str: str) -> Optional[Exchange]:
        """Parse exchange string to enum"""
        exchange_mapping = {
            "NSE": Exchange.NSE,
            "BSE": Exchange.BSE,
            "NASDAQ": Exchange.NASDAQ,
            "NYSE": Exchange.NYSE,
            "MANUAL": Exchange.MANUAL,
        }
        
        return exchange_mapping.get(exchange_str.upper()) if exchange_str else None
    
    async def _load_existing_instruments(
        self, 
        db: AsyncSession, 
        identifiers: List[InstrumentIdentifier]
    ) -> List[CanonicalInstrument]:
        """Load existing instruments that might match"""
        
        # Build query conditions for potential matches
        conditions = []
        
        for identifier in identifiers:
            if identifier.identifier_type == IdentifierType.ISIN:
                conditions.append(Instrument.isin == identifier.value)
            elif identifier.identifier_type == IdentifierType.AMFI_CODE:
                conditions.append(Instrument.amfi_code == identifier.value)
            elif identifier.identifier_type == IdentifierType.CUSIP:
                conditions.append(Instrument.cusip == identifier.value)
            elif identifier.identifier_type == IdentifierType.SYMBOL:
                if identifier.exchange:
                    conditions.append(
                        (Instrument.symbol == identifier.value) & 
                        (Instrument.primary_exchange == identifier.exchange)
                    )
                else:
                    conditions.append(Instrument.symbol == identifier.value)
        
        if not conditions:
            return []
        
        # Execute query with OR conditions
        stmt = select(Instrument).where(
            conditions[0] if len(conditions) == 1 else 
            conditions[0] | conditions[1] if len(conditions) == 2 else
            conditions[0] | conditions[1] | conditions[2] if len(conditions) == 3 else
            conditions[0] | conditions[1] | conditions[2] | conditions[3]
        )
        
        result = await db.execute(stmt)
        db_instruments = result.scalars().all()
        
        # Convert to canonical format
        canonical_instruments = []
        for db_instrument in db_instruments:
            canonical = self._db_to_canonical(db_instrument)
            canonical_instruments.append(canonical)
        
        return canonical_instruments
    
    def _db_to_canonical(self, db_instrument: Instrument) -> CanonicalInstrument:
        """Convert database instrument to canonical format"""
        
        # Collect all identifiers
        identifiers = []
        
        if db_instrument.isin:
            identifiers.append(InstrumentIdentifier(
                identifier_type=IdentifierType.ISIN,
                value=db_instrument.isin
            ))
        
        if db_instrument.amfi_code:
            identifiers.append(InstrumentIdentifier(
                identifier_type=IdentifierType.AMFI_CODE,
                value=db_instrument.amfi_code
            ))
        
        if db_instrument.cusip:
            identifiers.append(InstrumentIdentifier(
                identifier_type=IdentifierType.CUSIP,
                value=db_instrument.cusip
            ))
        
        if db_instrument.symbol:
            identifiers.append(InstrumentIdentifier(
                identifier_type=IdentifierType.SYMBOL,
                value=db_instrument.symbol,
                exchange=db_instrument.primary_exchange.value if db_instrument.primary_exchange else None
            ))
        
        return CanonicalInstrument(
            canonical_id=db_instrument.canonical_id,
            name=db_instrument.name,
            asset_class=db_instrument.asset_class,
            currency=db_instrument.currency,
            primary_exchange=db_instrument.primary_exchange,
            identifiers=identifiers,
            sector=db_instrument.sector,
            industry=db_instrument.industry,
            country=db_instrument.country,
            face_value=float(db_instrument.face_value) if db_instrument.face_value else None,
            lot_size=db_instrument.lot_size,
            is_active=db_instrument.is_active
        )
    
    async def _find_existing_db_instrument(
        self, 
        db: AsyncSession, 
        canonical: CanonicalInstrument
    ) -> Optional[Instrument]:
        """Find existing instrument in database by canonical ID"""
        
        stmt = select(Instrument).where(Instrument.canonical_id == canonical.canonical_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def _create_db_instrument(
        self, 
        db: AsyncSession, 
        canonical: CanonicalInstrument
    ) -> Instrument:
        """Create new instrument in database"""
        
        # Extract individual identifiers
        isin = next((id.value for id in canonical.identifiers if id.identifier_type == IdentifierType.ISIN), None)
        amfi_code = next((id.value for id in canonical.identifiers if id.identifier_type == IdentifierType.AMFI_CODE), None)
        cusip = next((id.value for id in canonical.identifiers if id.identifier_type == IdentifierType.CUSIP), None)
        symbol = next((id.value for id in canonical.identifiers if id.identifier_type == IdentifierType.SYMBOL), None)
        
        instrument = Instrument(
            canonical_id=canonical.canonical_id,
            name=canonical.name,
            asset_class=canonical.asset_class,
            currency=canonical.currency,
            isin=isin,
            amfi_code=amfi_code,
            cusip=cusip,
            primary_exchange=canonical.primary_exchange,
            symbol=symbol,
            sector=canonical.sector,
            industry=canonical.industry,
            country=canonical.country,
            face_value=canonical.face_value,
            lot_size=canonical.lot_size,
            is_active=canonical.is_active
        )
        
        db.add(instrument)
        await db.flush()
        
        return instrument
    
    async def _update_instrument_identifiers(
        self,
        db: AsyncSession,
        instrument: Instrument,
        new_identifiers: List[InstrumentIdentifier]
    ) -> bool:
        """Update existing instrument with new identifiers"""
        
        updated = False
        
        for identifier in new_identifiers:
            if identifier.identifier_type == IdentifierType.ISIN and not instrument.isin:
                instrument.isin = identifier.value
                updated = True
            elif identifier.identifier_type == IdentifierType.AMFI_CODE and not instrument.amfi_code:
                instrument.amfi_code = identifier.value
                updated = True
            elif identifier.identifier_type == IdentifierType.CUSIP and not instrument.cusip:
                instrument.cusip = identifier.value
                updated = True
            elif identifier.identifier_type == IdentifierType.SYMBOL and not instrument.symbol:
                instrument.symbol = identifier.value
                updated = True
        
        if updated:
            await db.commit()
        
        return updated
    
    def _choose_primary_instrument(self, instruments: List[Instrument]) -> Instrument:
        """Choose the best instrument from conflicts"""
        
        # Score instruments based on completeness
        def score_instrument(instrument: Instrument) -> int:
            score = 0
            if instrument.isin: score += 4
            if instrument.amfi_code: score += 3
            if instrument.cusip: score += 3
            if instrument.symbol: score += 2
            if instrument.sector: score += 1
            return score
        
        # Return instrument with highest score
        return max(instruments, key=score_instrument)
    
    async def _merge_instrument_identifiers(
        self,
        db: AsyncSession,
        primary: Instrument,
        secondary: Instrument
    ) -> None:
        """Merge identifiers from secondary instrument to primary"""
        
        # Copy missing identifiers
        if secondary.isin and not primary.isin:
            primary.isin = secondary.isin
        if secondary.amfi_code and not primary.amfi_code:
            primary.amfi_code = secondary.amfi_code
        if secondary.cusip and not primary.cusip:
            primary.cusip = secondary.cusip
        if secondary.symbol and not primary.symbol:
            primary.symbol = secondary.symbol
            primary.primary_exchange = secondary.primary_exchange
        
        # Copy other useful fields
        if secondary.sector and not primary.sector:
            primary.sector = secondary.sector
        if secondary.industry and not primary.industry:
            primary.industry = secondary.industry
        
        # Mark secondary as inactive (don't delete to preserve audit trail)
        secondary.is_active = False
        
        await db.commit()


# Create global service instance
instrument_mapping_service = InstrumentMappingService()
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
import structlog
import re
import hashlib
from enum import Enum

from app.db.models import AssetClass, Currency, Exchange


class IdentifierType(str, Enum):
    """Types of instrument identifiers"""
    ISIN = "isin"
    AMFI_CODE = "amfi_code"
    CUSIP = "cusip"
    SYMBOL = "symbol"
    MANUAL = "manual"


@dataclass
class InstrumentIdentifier:
    """Standardized instrument identifier"""
    identifier_type: IdentifierType
    value: str
    exchange: Optional[str] = None
    country: Optional[str] = None
    
    def __post_init__(self):
        """Normalize identifier value"""
        self.value = self.value.strip().upper()
        if self.exchange:
            self.exchange = self.exchange.strip().upper()
        if self.country:
            self.country = self.country.strip().upper()


@dataclass
class CanonicalInstrument:
    """Canonical representation of an instrument"""
    canonical_id: str
    name: str
    asset_class: AssetClass
    currency: Currency
    primary_exchange: Optional[Exchange]
    
    # All known identifiers
    identifiers: List[InstrumentIdentifier]
    
    # Additional metadata
    sector: Optional[str] = None
    industry: Optional[str] = None
    country: str = "IN"
    face_value: Optional[float] = None
    lot_size: int = 1
    
    # Validation
    is_active: bool = True
    confidence_score: float = 1.0  # 0-1 confidence in canonicalization


class InstrumentMatcher(ABC):
    """Base class for instrument matching strategies"""
    
    @abstractmethod
    def match(
        self, 
        query_identifiers: List[InstrumentIdentifier],
        existing_instruments: List[CanonicalInstrument]
    ) -> List[Tuple[CanonicalInstrument, float]]:
        """Return list of (instrument, confidence_score) matches"""
        pass


class ExactMatcher(InstrumentMatcher):
    """Exact identifier matching"""
    
    def match(
        self, 
        query_identifiers: List[InstrumentIdentifier],
        existing_instruments: List[CanonicalInstrument]
    ) -> List[Tuple[CanonicalInstrument, float]]:
        """Find exact matches"""
        matches = []
        
        for query_id in query_identifiers:
            for instrument in existing_instruments:
                for existing_id in instrument.identifiers:
                    if (query_id.identifier_type == existing_id.identifier_type and
                        query_id.value == existing_id.value):
                        
                        # Check exchange match if both specified
                        if (query_id.exchange and existing_id.exchange and 
                            query_id.exchange != existing_id.exchange):
                            continue
                        
                        matches.append((instrument, 1.0))
                        break
        
        return matches


class FuzzyNameMatcher(InstrumentMatcher):
    """Fuzzy name-based matching"""
    
    def __init__(self):
        self.name_normalizer = NameNormalizer()
    
    def match(
        self, 
        query_identifiers: List[InstrumentIdentifier],
        existing_instruments: List[CanonicalInstrument]
    ) -> List[Tuple[CanonicalInstrument, float]]:
        """Find fuzzy name matches"""
        matches = []
        
        # For now, we'll skip fuzzy matching in MVP
        # This can be enhanced with libraries like fuzzywuzzy
        return matches


class NameNormalizer:
    """Utility for normalizing instrument names"""
    
    def __init__(self):
        # Common abbreviations and their expansions
        self.abbreviations = {
            'LTD': 'LIMITED',
            'PVT': 'PRIVATE',
            'CORP': 'CORPORATION',
            'INC': 'INCORPORATED',
            'CO': 'COMPANY',
            'TECH': 'TECHNOLOGY',
            'PHARM': 'PHARMACEUTICALS',
            'INFRA': 'INFRASTRUCTURE',
            'FIN': 'FINANCIAL',
            'SVC': 'SERVICES',
            'MFG': 'MANUFACTURING',
        }
        
        # Words to remove
        self.stop_words = {'THE', 'OF', 'AND', 'OR', 'FOR', 'WITH', 'BY'}
        
        # Common company suffixes
        self.company_suffixes = {
            'LIMITED', 'LTD', 'PRIVATE', 'PVT', 'CORPORATION', 'CORP',
            'INCORPORATED', 'INC', 'COMPANY', 'CO', 'LLC', 'LLP'
        }
    
    def normalize(self, name: str) -> str:
        """Normalize instrument name for matching"""
        if not name:
            return ""
        
        # Convert to uppercase
        normalized = name.upper().strip()
        
        # Remove special characters except spaces and hyphens
        normalized = re.sub(r'[^\w\s\-]', '', normalized)
        
        # Split into words
        words = normalized.split()
        
        # Expand abbreviations
        words = [self.abbreviations.get(word, word) for word in words]
        
        # Remove stop words (except at the beginning)
        if len(words) > 1:
            words = [words[0]] + [word for word in words[1:] if word not in self.stop_words]
        
        # Remove common suffixes for better matching
        if words and words[-1] in self.company_suffixes:
            words = words[:-1]
        
        return ' '.join(words)
    
    def extract_keywords(self, name: str) -> List[str]:
        """Extract searchable keywords from name"""
        normalized = self.normalize(name)
        words = normalized.split()
        
        # Remove very short words
        keywords = [word for word in words if len(word) > 2]
        
        return keywords


class CanonicalIdGenerator:
    """Generator for canonical instrument IDs"""
    
    @staticmethod
    def generate(
        primary_identifier: InstrumentIdentifier,
        asset_class: AssetClass,
        name: str
    ) -> str:
        """Generate canonical ID based on primary identifier"""
        
        if primary_identifier.identifier_type == IdentifierType.ISIN:
            return f"ISIN:{primary_identifier.value}"
        
        elif primary_identifier.identifier_type == IdentifierType.AMFI_CODE:
            return f"AMFI:{primary_identifier.value}"
        
        elif primary_identifier.identifier_type == IdentifierType.CUSIP:
            return f"CUSIP:{primary_identifier.value}"
        
        elif primary_identifier.identifier_type == IdentifierType.SYMBOL:
            exchange = primary_identifier.exchange or "UNK"
            return f"{exchange}:{primary_identifier.value}"
        
        else:  # Manual or unknown
            # Generate hash-based ID for manual assets
            name_hash = hashlib.md5(name.encode('utf-8')).hexdigest()[:8].upper()
            return f"MANUAL:{asset_class.value.upper()}:{name_hash}"


class InstrumentCanonicalizer:
    """Main canonicalization service"""
    
    def __init__(self):
        self.logger = structlog.get_logger("InstrumentCanonicalizer")
        self.name_normalizer = NameNormalizer()
        
        # Initialize matchers
        self.matchers = [
            ExactMatcher(),
            FuzzyNameMatcher(),
        ]
        
        # Cache for performance
        self._cache: Dict[str, CanonicalInstrument] = {}
    
    def canonicalize(
        self,
        name: str,
        identifiers: List[InstrumentIdentifier],
        asset_class: AssetClass,
        currency: Currency,
        existing_instruments: List[CanonicalInstrument],
        exchange: Optional[Exchange] = None
    ) -> CanonicalInstrument:
        """Canonicalize an instrument"""
        
        # Create cache key
        cache_key = self._create_cache_key(name, identifiers)
        
        # Check cache first
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        # Try to find matches in existing instruments
        matches = self._find_matches(identifiers, existing_instruments)
        
        if matches:
            # Return best match
            best_match = max(matches, key=lambda x: x[1])[0]
            self.logger.info(
                "Found existing instrument match",
                name=name,
                canonical_id=best_match.canonical_id,
                confidence=max(matches, key=lambda x: x[1])[1]
            )
            
            # Update cache
            self._cache[cache_key] = best_match
            return best_match
        
        # Create new canonical instrument
        canonical_instrument = self._create_new_instrument(
            name, identifiers, asset_class, currency, exchange
        )
        
        # Update cache
        self._cache[cache_key] = canonical_instrument
        
        self.logger.info(
            "Created new canonical instrument",
            name=name,
            canonical_id=canonical_instrument.canonical_id,
            asset_class=asset_class.value
        )
        
        return canonical_instrument
    
    def _find_matches(
        self,
        query_identifiers: List[InstrumentIdentifier],
        existing_instruments: List[CanonicalInstrument]
    ) -> List[Tuple[CanonicalInstrument, float]]:
        """Find matches using all matchers"""
        all_matches = []
        
        for matcher in self.matchers:
            matches = matcher.match(query_identifiers, existing_instruments)
            all_matches.extend(matches)
        
        # Remove duplicates and sort by confidence
        unique_matches = {}
        for instrument, confidence in all_matches:
            key = instrument.canonical_id
            if key not in unique_matches or confidence > unique_matches[key][1]:
                unique_matches[key] = (instrument, confidence)
        
        return list(unique_matches.values())
    
    def _create_new_instrument(
        self,
        name: str,
        identifiers: List[InstrumentIdentifier],
        asset_class: AssetClass,
        currency: Currency,
        exchange: Optional[Exchange]
    ) -> CanonicalInstrument:
        """Create new canonical instrument"""
        
        # Determine primary identifier
        primary_identifier = self._select_primary_identifier(identifiers)
        
        # Generate canonical ID
        canonical_id = CanonicalIdGenerator.generate(
            primary_identifier, asset_class, name
        )
        
        # Normalize name
        normalized_name = self.name_normalizer.normalize(name)
        
        return CanonicalInstrument(
            canonical_id=canonical_id,
            name=normalized_name,
            asset_class=asset_class,
            currency=currency,
            primary_exchange=exchange,
            identifiers=identifiers,
            confidence_score=1.0
        )
    
    def _select_primary_identifier(self, identifiers: List[InstrumentIdentifier]) -> InstrumentIdentifier:
        """Select the best identifier as primary"""
        
        # Priority order: ISIN > AMFI > CUSIP > SYMBOL > MANUAL
        priority = {
            IdentifierType.ISIN: 1,
            IdentifierType.AMFI_CODE: 2,
            IdentifierType.CUSIP: 3,
            IdentifierType.SYMBOL: 4,
            IdentifierType.MANUAL: 5
        }
        
        # Sort by priority and return first
        sorted_identifiers = sorted(identifiers, key=lambda x: priority.get(x.identifier_type, 99))
        return sorted_identifiers[0] if sorted_identifiers else identifiers[0]
    
    def _create_cache_key(self, name: str, identifiers: List[InstrumentIdentifier]) -> str:
        """Create cache key for instrument"""
        # Sort identifiers for consistent key
        sorted_ids = sorted(
            [(id.identifier_type.value, id.value, id.exchange or "") for id in identifiers]
        )
        
        key_parts = [name] + [f"{t}:{v}:{e}" for t, v, e in sorted_ids]
        return hashlib.md5("|".join(key_parts).encode()).hexdigest()
    
    def add_identifier_mapping(
        self,
        canonical_id: str,
        new_identifier: InstrumentIdentifier
    ) -> bool:
        """Add new identifier mapping to existing instrument"""
        
        # Find instrument in cache
        for cached_instrument in self._cache.values():
            if cached_instrument.canonical_id == canonical_id:
                # Check if identifier already exists
                for existing_id in cached_instrument.identifiers:
                    if (existing_id.identifier_type == new_identifier.identifier_type and
                        existing_id.value == new_identifier.value):
                        return False  # Already exists
                
                # Add new identifier
                cached_instrument.identifiers.append(new_identifier)
                
                self.logger.info(
                    "Added identifier mapping",
                    canonical_id=canonical_id,
                    identifier_type=new_identifier.identifier_type.value,
                    identifier_value=new_identifier.value
                )
                
                return True
        
        return False
    
    def clear_cache(self):
        """Clear the canonicalization cache"""
        self._cache.clear()
        self.logger.info("Cleared canonicalization cache")


# Create global canonicalizer instance
instrument_canonicalizer = InstrumentCanonicalizer()
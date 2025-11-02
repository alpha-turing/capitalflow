import re
from typing import List, Dict, Any, Optional
from datetime import datetime
from decimal import Decimal
import PyPDF2
import io

from app.ingestion.base import BaseParser, ParsedTransaction, ParsedHolding, parser_factory
from app.db.models import TransactionType, Currency


class CASParser(BaseParser):
    """Parser for CAMS/KFin Consolidated Account Statement (CAS) PDFs"""
    
    def __init__(self):
        super().__init__()
        self.patterns = {
            'cas_title': re.compile(r'CONSOLIDATED ACCOUNT STATEMENT|CAS', re.IGNORECASE),
            'cams_signature': re.compile(r'CAMS|Computer Age Management Services', re.IGNORECASE),
            'kfin_signature': re.compile(r'KFintech|Karvy Fintech', re.IGNORECASE),
            'statement_period': re.compile(r'Statement Period[\s:]+(\d{2}[/-]\d{2}[/-]\d{4}) to (\d{2}[/-]\d{2}[/-]\d{4})'),
            'investor_info': re.compile(r'PAN[\s:]+([A-Z]{5}[0-9]{4}[A-Z]{1})'),
            'folio_section': re.compile(r'Folio No[\s:]+([A-Z0-9/]+)', re.IGNORECASE),
            'scheme_name': re.compile(r'Scheme[\s:]+(.+?)(?=\n|Advisor)', re.IGNORECASE),
            'registrar': re.compile(r'Registrar[\s:]+(.+?)(?=\n)', re.IGNORECASE),
            
            # Transaction patterns
            'transaction_line': re.compile(
                r'(\d{2}[/-]\d{2}[/-]\d{4})\s+'  # Date
                r'(.+?)\s+'  # Transaction description
                r'([\d,.-]+)\s+'  # Amount
                r'([\d,.-]+)\s+'  # Units
                r'([\d,.-]+)\s+'  # Price/NAV
                r'([\d,.-]+)'  # Balance units
                , re.MULTILINE
            ),
            
            # Holding patterns
            'current_value': re.compile(
                r'Closing Unit Balance[\s:]+?([\d,.-]+)\s+'
                r'NAV on (\d{2}[/-]\d{2}[/-]\d{4})[\s:]+?([\d,.-]+)\s+'
                r'Value on \d{2}[/-]\d{2}[/-]\d{4}[\s:]+?([\d,.-]+)'
                , re.MULTILINE
            ),
            
            'amfi_code': re.compile(r'AMFI[\s:]+([0-9]+)'),
            'isin': re.compile(r'ISIN[\s:]+([A-Z]{2}[A-Z0-9]{10})'),
        }
    
    def can_parse(self, file_content: bytes, filename: str) -> bool:
        """Check if this is a CAMS/KFin CAS PDF"""
        try:
            text = self._extract_pdf_text(file_content)
            
            has_cas_title = bool(self.patterns['cas_title'].search(text))
            has_cams = bool(self.patterns['cams_signature'].search(text))
            has_kfin = bool(self.patterns['kfin_signature'].search(text))
            
            self.logger.info(
                "CAS parser check",
                filename=filename,
                has_cas_title=has_cas_title,
                has_cams=has_cams,
                has_kfin=has_kfin
            )
            
            return has_cas_title and (has_cams or has_kfin)
            
        except Exception as e:
            self.logger.error("Error checking CAS PDF", filename=filename, error=str(e))
            return False
    
    def parse_transactions(self, file_content: bytes, filename: str) -> List[ParsedTransaction]:
        """Parse mutual fund transactions from CAS"""
        transactions = []
        
        try:
            text = self._extract_pdf_text(file_content)
            
            # Extract basic info
            statement_period = self._extract_statement_period(text)
            pan = self._extract_pan(text)
            
            # Parse folio sections
            folio_sections = self._split_into_folios(text)
            
            for folio_data in folio_sections:
                folio_transactions = self._parse_folio_transactions(folio_data, pan)
                transactions.extend(folio_transactions)
            
            self.logger.info(
                "Parsed CAS transactions",
                filename=filename,
                transaction_count=len(transactions),
                folio_count=len(folio_sections)
            )
            
        except Exception as e:
            self.logger.error("Error parsing CAS PDF", filename=filename, error=str(e))
        
        return transactions
    
    def parse_holdings(self, file_content: bytes, filename: str) -> List[ParsedHolding]:
        """Parse current holdings from CAS"""
        holdings = []
        
        try:
            text = self._extract_pdf_text(file_content)
            pan = self._extract_pan(text)
            folio_sections = self._split_into_folios(text)
            
            for folio_data in folio_sections:
                holding = self._parse_folio_holding(folio_data, pan)
                if holding:
                    holdings.append(holding)
            
            self.logger.info(
                "Parsed CAS holdings",
                filename=filename,
                holding_count=len(holdings)
            )
            
        except Exception as e:
            self.logger.error("Error parsing CAS holdings", filename=filename, error=str(e))
        
        return holdings
    
    def _extract_pdf_text(self, file_content: bytes) -> str:
        """Extract text from PDF content"""
        text = ""
        pdf_file = io.BytesIO(file_content)
        
        try:
            reader = PyPDF2.PdfReader(pdf_file)
            
            for page in reader.pages:
                text += page.extract_text() + "\n"
                
        except Exception as e:
            self.logger.error("Error extracting PDF text", error=str(e))
            raise
        
        return text
    
    def _extract_statement_period(self, text: str) -> Optional[tuple]:
        """Extract statement period from CAS"""
        match = self.patterns['statement_period'].search(text)
        if match:
            start_date = self._parse_date(match.group(1))
            end_date = self._parse_date(match.group(2))
            return (start_date, end_date)
        return None
    
    def _extract_pan(self, text: str) -> Optional[str]:
        """Extract PAN from CAS"""
        match = self.patterns['investor_info'].search(text)
        return match.group(1) if match else None
    
    def _split_into_folios(self, text: str) -> List[Dict[str, Any]]:
        """Split CAS text into individual folio sections"""
        folios = []
        
        # Find all folio sections
        folio_matches = list(self.patterns['folio_section'].finditer(text))
        
        for i, match in enumerate(folio_matches):
            start_pos = match.start()
            end_pos = folio_matches[i + 1].start() if i + 1 < len(folio_matches) else len(text)
            
            folio_text = text[start_pos:end_pos]
            folio_number = match.group(1)
            
            # Extract scheme info
            scheme_match = self.patterns['scheme_name'].search(folio_text)
            scheme_name = scheme_match.group(1).strip() if scheme_match else "Unknown Scheme"
            
            # Extract AMFI code and ISIN
            amfi_match = self.patterns['amfi_code'].search(folio_text)
            amfi_code = amfi_match.group(1) if amfi_match else None
            
            isin_match = self.patterns['isin'].search(folio_text)
            isin = isin_match.group(1) if isin_match else None
            
            folios.append({
                'folio_number': folio_number,
                'scheme_name': scheme_name,
                'amfi_code': amfi_code,
                'isin': isin,
                'text': folio_text
            })
        
        return folios
    
    def _parse_folio_transactions(self, folio_data: Dict[str, Any], pan: Optional[str]) -> List[ParsedTransaction]:
        """Parse transactions for a single folio"""
        transactions = []
        folio_text = folio_data['text']
        
        transaction_matches = self.patterns['transaction_line'].findall(folio_text)
        
        for match in transaction_matches:
            try:
                date_str, description, amount_str, units_str, price_str, balance_str = match
                
                # Parse date
                transaction_date = self._parse_date(date_str)
                
                # Determine transaction type
                txn_type = self._determine_transaction_type(description)
                
                # Parse amounts
                units = self._parse_decimal(units_str)
                price = self._parse_decimal(price_str)
                amount = self._parse_decimal(amount_str)
                
                # Skip if invalid data
                if units == 0 or price == 0:
                    continue
                
                transaction = ParsedTransaction(
                    transaction_type=txn_type,
                    transaction_date=transaction_date,
                    quantity=abs(units),  # Units can be negative for redemption
                    price=price,
                    gross_amount=abs(amount),
                    instrument_name=folio_data['scheme_name'],
                    amfi_code=folio_data['amfi_code'],
                    isin=folio_data['isin'],
                    currency=Currency.INR,
                    source_reference=f"CAS-{folio_data['folio_number']}-{transaction_date.strftime('%Y%m%d')}",
                    raw_data={
                        'folio_number': folio_data['folio_number'],
                        'description': description,
                        'balance_units': balance_str,
                        'pan': pan
                    }
                )
                
                if self.validate_transaction(transaction):
                    transactions.append(transaction)
                    
            except Exception as e:
                self.logger.error("Error parsing CAS transaction", match=match, error=str(e))
                continue
        
        return transactions
    
    def _parse_folio_holding(self, folio_data: Dict[str, Any], pan: Optional[str]) -> Optional[ParsedHolding]:
        """Parse current holding for a single folio"""
        folio_text = folio_data['text']
        
        holding_match = self.patterns['current_value'].search(folio_text)
        
        if holding_match:
            try:
                units_str, nav_date_str, nav_str, value_str = holding_match.groups()
                
                units = self._parse_decimal(units_str)
                nav = self._parse_decimal(nav_str)
                market_value = self._parse_decimal(value_str)
                nav_date = self._parse_date(nav_date_str)
                
                return ParsedHolding(
                    folio_number=folio_data['folio_number'],
                    scheme_name=folio_data['scheme_name'],
                    units=units,
                    nav=nav,
                    market_value=market_value,
                    valuation_date=nav_date,
                    amfi_code=folio_data['amfi_code'],
                    isin=folio_data['isin'],
                    pan=pan,
                    raw_data=folio_data
                )
                
            except Exception as e:
                self.logger.error("Error parsing CAS holding", folio=folio_data['folio_number'], error=str(e))
        
        return None
    
    def _determine_transaction_type(self, description: str) -> TransactionType:
        """Determine transaction type from description"""
        desc_lower = description.lower()
        
        if any(word in desc_lower for word in ['purchase', 'investment', 'sip', 'lumpsum']):
            return TransactionType.BUY
        elif any(word in desc_lower for word in ['redemption', 'withdrawal']):
            return TransactionType.SELL
        elif 'dividend' in desc_lower:
            return TransactionType.DIVIDEND
        else:
            # Default to buy for mutual funds
            return TransactionType.BUY
    
    def _parse_date(self, date_str: str) -> datetime:
        """Parse date string with multiple formats"""
        for fmt in ['%d/%m/%Y', '%d-%m-%Y', '%d/%m/%y', '%d-%m-%y']:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        
        raise ValueError(f"Could not parse date: {date_str}")
    
    def _parse_decimal(self, value: str) -> Decimal:
        """Parse decimal value from string, handling Indian number format"""
        if not value or value.strip() == "":
            return Decimal('0')
        
        # Remove commas and spaces, handle negative values
        clean_value = re.sub(r'[,\s]', '', value.strip())
        
        # Handle parentheses as negative (common in financial statements)
        if clean_value.startswith('(') and clean_value.endswith(')'):
            clean_value = '-' + clean_value[1:-1]
        
        try:
            return Decimal(clean_value)
        except Exception:
            self.logger.warning("Could not parse decimal value", value=value)
            return Decimal('0')


# Register the parser
parser_factory.register_parser(CASParser())
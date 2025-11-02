import re
from typing import List, Dict, Any, Optional
from datetime import datetime
from decimal import Decimal
import PyPDF2
import io

from app.ingestion.base import BaseParser, ParsedTransaction, parser_factory
from app.db.models import TransactionType, Currency


class ICICIDirectParser(BaseParser):
    """Parser for ICICI Direct contract note PDFs"""
    
    def __init__(self):
        super().__init__()
        self.patterns = {
            'contract_note': re.compile(r'CONTRACT NOTE', re.IGNORECASE),
            'icici_direct': re.compile(r'ICICI DIRECT|ICICI Securities', re.IGNORECASE),
            'trade_date': re.compile(r'Trade Date[\s:]+(\d{2}[/-]\d{2}[/-]\d{4})'),
            'settlement_date': re.compile(r'Settlement Date[\s:]+(\d{2}[/-]\d{2}[/-]\d{4})'),
            'client_code': re.compile(r'Client Code[\s:]+([A-Z0-9]+)'),
            'transaction_table': re.compile(
                r'(BUY|SELL)\s+'  # Transaction type
                r'([A-Z0-9&\s]+?)\s+'  # Stock name
                r'(\d+)\s+'  # Quantity
                r'([\d.,]+)\s+'  # Rate
                r'([\d.,]+)\s+'  # Gross Amount
                r'([\d.,]+)\s+'  # Brokerage
                r'([\d.,]+)\s+'  # Total
                , re.MULTILINE | re.IGNORECASE
            ),
            'isin_mapping': re.compile(r'([A-Z0-9&\s]+?)\s+([A-Z]{2}[A-Z0-9]{10})', re.MULTILINE),
            'exchange_info': re.compile(r'NSE|BSE', re.IGNORECASE),
        }
    
    def can_parse(self, file_content: bytes, filename: str) -> bool:
        """Check if this is an ICICI Direct contract note"""
        try:
            # Try to extract text from PDF
            text = self._extract_pdf_text(file_content)
            
            # Check for ICICI Direct signatures
            has_contract_note = bool(self.patterns['contract_note'].search(text))
            has_icici_signature = bool(self.patterns['icici_direct'].search(text))
            
            self.logger.info(
                "ICICI Direct parser check",
                filename=filename,
                has_contract_note=has_contract_note,
                has_icici_signature=has_icici_signature
            )
            
            return has_contract_note and has_icici_signature
            
        except Exception as e:
            self.logger.error("Error checking ICICI Direct PDF", filename=filename, error=str(e))
            return False
    
    def parse_transactions(self, file_content: bytes, filename: str) -> List[ParsedTransaction]:
        """Parse transactions from ICICI Direct contract note"""
        transactions = []
        
        try:
            text = self._extract_pdf_text(file_content)
            
            # Extract basic info
            trade_date = self._extract_trade_date(text)
            settlement_date = self._extract_settlement_date(text)
            client_code = self._extract_client_code(text)
            
            # Extract ISIN mappings
            isin_mappings = self._extract_isin_mappings(text)
            
            # Extract transactions
            raw_transactions = self._extract_transaction_data(text)
            
            for raw_txn in raw_transactions:
                try:
                    transaction = self._parse_single_transaction(
                        raw_txn, trade_date, settlement_date, isin_mappings, client_code
                    )
                    
                    if self.validate_transaction(transaction):
                        transactions.append(transaction)
                    else:
                        self.logger.warning("Invalid transaction found", transaction=raw_txn)
                        
                except Exception as e:
                    self.logger.error("Error parsing transaction", raw_txn=raw_txn, error=str(e))
                    continue
            
            self.logger.info(
                "Parsed ICICI Direct transactions",
                filename=filename,
                transaction_count=len(transactions)
            )
            
        except Exception as e:
            self.logger.error("Error parsing ICICI Direct PDF", filename=filename, error=str(e))
        
        return transactions
    
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
    
    def _extract_trade_date(self, text: str) -> datetime:
        """Extract trade date from contract note"""
        match = self.patterns['trade_date'].search(text)
        if match:
            date_str = match.group(1)
            # Handle different date formats
            for fmt in ['%d/%m/%Y', '%d-%m-%Y', '%d/%m/%y', '%d-%m-%y']:
                try:
                    return datetime.strptime(date_str, fmt)
                except ValueError:
                    continue
        
        raise ValueError("Could not extract trade date")
    
    def _extract_settlement_date(self, text: str) -> Optional[datetime]:
        """Extract settlement date from contract note"""
        match = self.patterns['settlement_date'].search(text)
        if match:
            date_str = match.group(1)
            # Handle different date formats
            for fmt in ['%d/%m/%Y', '%d-%m-%Y', '%d/%m/%y', '%d-%m-%y']:
                try:
                    return datetime.strptime(date_str, fmt)
                except ValueError:
                    continue
        
        # If no settlement date found, return None
        return None
    
    def _extract_client_code(self, text: str) -> str:
        """Extract client code from contract note"""
        match = self.patterns['client_code'].search(text)
        return match.group(1) if match else ""
    
    def _extract_isin_mappings(self, text: str) -> Dict[str, str]:
        """Extract ISIN mappings for instruments"""
        mappings = {}
        
        matches = self.patterns['isin_mapping'].findall(text)
        for instrument_name, isin in matches:
            # Clean up instrument name
            clean_name = re.sub(r'\s+', ' ', instrument_name.strip())
            mappings[clean_name] = isin
        
        return mappings
    
    def _extract_transaction_data(self, text: str) -> List[Dict[str, Any]]:
        """Extract raw transaction data from text"""
        transactions = []
        
        matches = self.patterns['transaction_table'].findall(text)
        
        for match in matches:
            txn_type, instrument_name, quantity, rate, gross_amount, brokerage, total = match
            
            transactions.append({
                'type': txn_type.upper(),
                'instrument_name': instrument_name.strip(),
                'quantity': quantity,
                'rate': rate,
                'gross_amount': gross_amount,
                'brokerage': brokerage,
                'total': total
            })
        
        return transactions
    
    def _parse_single_transaction(
        self, 
        raw_txn: Dict[str, Any], 
        trade_date: datetime,
        settlement_date: Optional[datetime],
        isin_mappings: Dict[str, str],
        client_code: str
    ) -> ParsedTransaction:
        """Parse a single transaction from raw data"""
        
        # Determine transaction type
        txn_type = TransactionType.BUY if raw_txn['type'] == 'BUY' else TransactionType.SELL
        
        # Clean and normalize instrument name
        instrument_name = re.sub(r'\s+', ' ', raw_txn['instrument_name'].strip())
        
        # Get ISIN if available
        isin = isin_mappings.get(instrument_name)
        
        # Parse numeric values
        quantity = self._parse_decimal(raw_txn['quantity'])
        price = self._parse_decimal(raw_txn['rate'])
        gross_amount = self._parse_decimal(raw_txn['gross_amount'])
        brokerage = self._parse_decimal(raw_txn['brokerage'])
        
        # Calculate other charges (total - gross_amount - brokerage)
        total_amount = self._parse_decimal(raw_txn['total'])
        other_charges = total_amount - gross_amount - brokerage
        
        return ParsedTransaction(
            transaction_type=txn_type,
            transaction_date=trade_date,
            settlement_date=settlement_date,
            quantity=quantity,
            price=price,
            gross_amount=gross_amount,
            brokerage=brokerage,
            taxes=Decimal('0'),  # ICICI combines taxes in other charges
            other_charges=other_charges,
            net_amount=total_amount,
            instrument_name=instrument_name,
            isin=isin,
            currency=Currency.INR,
            exchange="NSE",  # Default to NSE, can be refined
            source_reference=f"ICICI-{client_code}-{trade_date.strftime('%Y%m%d')}",
            raw_data=raw_txn
        )
    
    def _parse_decimal(self, value: str) -> Decimal:
        """Parse decimal value from string, handling Indian number format"""
        if not value or value.strip() == "":
            return Decimal('0')
        
        # Remove commas and spaces
        clean_value = re.sub(r'[,\s]', '', value.strip())
        
        try:
            return Decimal(clean_value)
        except Exception:
            self.logger.warning("Could not parse decimal value", value=value)
            return Decimal('0')


# Register the parser
parser_factory.register_parser(ICICIDirectParser())
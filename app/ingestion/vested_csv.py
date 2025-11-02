import csv
from typing import List, Dict, Any, Optional
from datetime import datetime
from decimal import Decimal
import io

from app.ingestion.base import BaseParser, ParsedTransaction, parser_factory
from app.db.models import TransactionType, Currency


class VestedCSVParser(BaseParser):
    """Parser for Vested US equities CSV exports"""
    
    def __init__(self):
        super().__init__()
        
        # Expected column mappings for different Vested CSV formats
        self.column_mappings = {
            # Standard Vested format
            'standard': {
                'symbol': ['Symbol', 'Ticker', 'Stock Symbol'],
                'company_name': ['Company Name', 'Name', 'Company'],
                'transaction_type': ['Transaction Type', 'Type', 'Action'],
                'transaction_date': ['Date', 'Transaction Date', 'Trade Date'],
                'settlement_date': ['Settlement Date'],
                'quantity': ['Quantity', 'Shares', 'Units'],
                'price': ['Price', 'Unit Price', 'Price per Share'],
                'gross_amount': ['Total Amount', 'Gross Amount', 'Amount'],
                'fees': ['Fees', 'Commission', 'Brokerage'],
                'currency': ['Currency'],
                'cusip': ['CUSIP'],
                'isin': ['ISIN'],
            }
        }
    
    def can_parse(self, file_content: bytes, filename: str) -> bool:
        """Check if this is a Vested CSV file"""
        try:
            # Check if it's a CSV file
            if not filename.lower().endswith('.csv'):
                return False
            
            # Try to parse as CSV and check headers
            content_str = file_content.decode('utf-8')
            csv_reader = csv.DictReader(io.StringIO(content_str))
            headers = csv_reader.fieldnames or []
            
            # Check for Vested-specific headers
            vested_indicators = [
                'Symbol', 'Ticker', 'Stock Symbol', 
                'Transaction Type', 'Type', 'Action',
                'Company Name', 'Company'
            ]
            
            # Check if we have enough matching headers
            matches = sum(1 for indicator in vested_indicators 
                         if any(indicator.lower() in header.lower() for header in headers))
            
            has_vested_format = matches >= 3  # Require at least 3 matching headers
            
            self.logger.info(
                "Vested CSV parser check",
                filename=filename,
                headers=headers,
                matches=matches,
                has_vested_format=has_vested_format
            )
            
            return has_vested_format
            
        except Exception as e:
            self.logger.error("Error checking Vested CSV", filename=filename, error=str(e))
            return False
    
    def parse_transactions(self, file_content: bytes, filename: str) -> List[ParsedTransaction]:
        """Parse transactions from Vested CSV"""
        transactions = []
        
        try:
            content_str = file_content.decode('utf-8')
            csv_reader = csv.DictReader(io.StringIO(content_str))
            
            # Detect column mapping
            column_mapping = self._detect_column_mapping(list(csv_reader.fieldnames or []))
            
            for row_num, row in enumerate(csv_reader, start=1):
                try:
                    transaction = self._parse_single_transaction(row, column_mapping, row_num)
                    
                    if transaction and self.validate_transaction(transaction):
                        transactions.append(transaction)
                    elif transaction:
                        self.logger.warning("Invalid transaction found", row_num=row_num, row=row)
                        
                except Exception as e:
                    self.logger.error("Error parsing CSV row", row_num=row_num, row=row, error=str(e))
                    continue
            
            self.logger.info(
                "Parsed Vested CSV transactions",
                filename=filename,
                transaction_count=len(transactions),
                total_rows=row_num if 'row_num' in locals() else 0
            )
            
        except Exception as e:
            self.logger.error("Error parsing Vested CSV", filename=filename, error=str(e))
        
        return transactions
    
    def _detect_column_mapping(self, headers: List[str]) -> Dict[str, str]:
        """Detect which columns map to which fields"""
        mapping = {}
        
        for field, possible_headers in self.column_mappings['standard'].items():
            for header in headers:
                for possible_header in possible_headers:
                    if possible_header.lower() in header.lower():
                        mapping[field] = header
                        break
                if field in mapping:
                    break
        
        self.logger.info("Detected column mapping", mapping=mapping)
        return mapping
    
    def _parse_single_transaction(
        self, 
        row: Dict[str, str], 
        column_mapping: Dict[str, str], 
        row_num: int
    ) -> Optional[ParsedTransaction]:
        """Parse a single transaction from CSV row"""
        
        try:
            # Extract basic fields
            symbol = self._get_column_value(row, column_mapping, 'symbol')
            company_name = self._get_column_value(row, column_mapping, 'company_name')
            
            # Use company name as instrument name if available, otherwise use symbol
            instrument_name = company_name or symbol
            if not instrument_name:
                self.logger.warning("No instrument name or symbol found", row_num=row_num)
                return None
            
            # Parse transaction type
            txn_type_str = self._get_column_value(row, column_mapping, 'transaction_type')
            txn_type = self._parse_transaction_type(txn_type_str)
            
            # Parse dates
            transaction_date = self._parse_date(
                self._get_column_value(row, column_mapping, 'transaction_date')
            )
            
            settlement_date_str = self._get_column_value(row, column_mapping, 'settlement_date')
            settlement_date = self._parse_date(settlement_date_str) if settlement_date_str else None
            
            # Parse numeric values
            quantity = self._parse_decimal(self._get_column_value(row, column_mapping, 'quantity'))
            price = self._parse_decimal(self._get_column_value(row, column_mapping, 'price'))
            gross_amount = self._parse_decimal(self._get_column_value(row, column_mapping, 'gross_amount'))
            fees = self._parse_decimal(self._get_column_value(row, column_mapping, 'fees'))
            
            # Parse currency
            currency_str = self._get_column_value(row, column_mapping, 'currency')
            currency = Currency.USD if currency_str and 'USD' in currency_str.upper() else Currency.USD
            
            # Extract identifiers
            cusip = self._get_column_value(row, column_mapping, 'cusip')
            isin = self._get_column_value(row, column_mapping, 'isin')
            
            # Validate essential fields
            if quantity <= 0 or price <= 0:
                self.logger.warning("Invalid quantity or price", row_num=row_num, quantity=quantity, price=price)
                return None
            
            return ParsedTransaction(
                transaction_type=txn_type,
                transaction_date=transaction_date,
                settlement_date=settlement_date,
                quantity=quantity,
                price=price,
                gross_amount=gross_amount,
                brokerage=fees,  # Vested fees include brokerage
                taxes=Decimal('0'),  # Taxes typically included in fees for US trades
                other_charges=Decimal('0'),
                instrument_name=instrument_name,
                symbol=symbol,
                cusip=cusip,
                isin=isin,
                currency=currency,
                exchange="NASDAQ",  # Default exchange for US stocks
                source_reference=f"VESTED-{row_num}",
                raw_data=dict(row)
            )
            
        except Exception as e:
            self.logger.error("Error parsing transaction row", row_num=row_num, error=str(e))
            return None
    
    def _get_column_value(self, row: Dict[str, str], column_mapping: Dict[str, str], field: str) -> Optional[str]:
        """Get value from row using column mapping"""
        column_name = column_mapping.get(field)
        if column_name and column_name in row:
            return row[column_name].strip() if row[column_name] else None
        return None
    
    def _parse_transaction_type(self, txn_type_str: Optional[str]) -> TransactionType:
        """Parse transaction type from string"""
        if not txn_type_str:
            return TransactionType.BUY  # Default
        
        txn_type_lower = txn_type_str.lower()
        
        if any(word in txn_type_lower for word in ['buy', 'purchase', 'long']):
            return TransactionType.BUY
        elif any(word in txn_type_lower for word in ['sell', 'sale', 'short']):
            return TransactionType.SELL
        elif 'dividend' in txn_type_lower:
            return TransactionType.DIVIDEND
        else:
            # Default to BUY for unknown types
            return TransactionType.BUY
    
    def _parse_date(self, date_str: Optional[str]) -> datetime:
        """Parse date string with multiple formats"""
        if not date_str:
            raise ValueError("Empty date string")
        
        # Common date formats used by Vested
        date_formats = [
            '%Y-%m-%d',      # 2024-01-15
            '%m/%d/%Y',      # 01/15/2024
            '%d/%m/%Y',      # 15/01/2024
            '%Y-%m-%d %H:%M:%S',  # 2024-01-15 10:30:00
            '%m/%d/%y',      # 01/15/24
            '%d-%m-%Y',      # 15-01-2024
        ]
        
        for fmt in date_formats:
            try:
                parsed_date = datetime.strptime(date_str, fmt)
                # Make the datetime timezone-aware (UTC)
                from datetime import timezone
                return parsed_date.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        
        raise ValueError(f"Could not parse date: {date_str}")
    
    def _parse_decimal(self, value_str: Optional[str]) -> Decimal:
        """Parse decimal value from string"""
        if not value_str or value_str.strip() == "":
            return Decimal('0')
        
        # Remove currency symbols, commas, and spaces
        clean_value = value_str.strip()
        clean_value = clean_value.replace('$', '').replace(',', '').replace(' ', '')
        
        # Handle parentheses as negative
        if clean_value.startswith('(') and clean_value.endswith(')'):
            clean_value = '-' + clean_value[1:-1]
        
        try:
            return Decimal(clean_value)
        except Exception:
            self.logger.warning("Could not parse decimal value", value=value_str)
            return Decimal('0')


# Register the parser
parser_factory.register_parser(VestedCSVParser())
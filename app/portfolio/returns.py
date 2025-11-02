from typing import List, Dict, Tuple, Optional
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from dataclasses import dataclass
import structlog
import math

from app.db.models import Transaction, TransactionType, Currency


def _normalize_datetime(dt: datetime) -> datetime:
    """Ensure datetime is timezone-aware by adding UTC if naive"""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


@dataclass
class CashFlow:
    """Cash flow for returns calculation"""
    date: datetime
    amount: Decimal  # Negative for outflows (purchases), positive for inflows (sales/dividends)
    transaction_type: TransactionType
    transaction_id: Optional[str] = None


@dataclass
class PerformanceMetrics:
    """Portfolio performance metrics"""
    
    # Time-weighted return (TWR)
    twr_annualized: Optional[Decimal] = None
    twr_total: Optional[Decimal] = None
    
    # Money-weighted return (XIRR)
    xirr_annualized: Optional[Decimal] = None
    
    # Simple metrics
    total_invested: Decimal = Decimal('0')
    current_value: Decimal = Decimal('0')
    total_return: Decimal = Decimal('0')
    total_return_percentage: Decimal = Decimal('0')
    
    # Time period
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    days_invested: int = 0
    
    # Additional metrics
    volatility: Optional[Decimal] = None
    sharpe_ratio: Optional[Decimal] = None
    max_drawdown: Optional[Decimal] = None


class ReturnsCalculator:
    """Calculator for portfolio returns using XIRR and TWR methodologies"""
    
    def __init__(self):
        self.logger = structlog.get_logger("ReturnsCalculator")
    
    def calculate_xirr(
        self,
        cash_flows: List[CashFlow],
        current_value: Decimal,
        valuation_date: datetime
    ) -> Optional[Decimal]:
        """
        Calculate XIRR (Extended Internal Rate of Return) - Money-weighted return
        
        XIRR accounts for the timing and size of cash flows
        """
        
        if not cash_flows:
            return None
        
        # Prepare cash flows for XIRR calculation
        dates = []
        amounts = []
        
        # Add all historical cash flows
        for cf in cash_flows:
            dates.append(cf.date)
            amounts.append(float(cf.amount))
        
        # Add current value as final cash flow
        dates.append(valuation_date)
        amounts.append(float(current_value))
        
        try:
            # Use Newton-Raphson method to find XIRR
            xirr = self._calculate_xirr_newton_raphson(dates, amounts)
            
            if xirr is not None:
                self.logger.info(
                    "Calculated XIRR",
                    xirr_percentage=f"{float(xirr) * 100:.2f}%",
                    cash_flows_count=len(cash_flows)
                )
                
                return Decimal(str(xirr))
            
        except Exception as e:
            self.logger.error("Error calculating XIRR", error=str(e))
        
        return None
    
    def calculate_twr(
        self,
        transactions: List[Transaction],
        portfolio_values: List[Tuple[datetime, Decimal]],
        start_value: Decimal = Decimal('0')
    ) -> Optional[Decimal]:
        """
        Calculate TWR (Time-Weighted Return)
        
        TWR eliminates the effect of cash flows and measures pure investment performance
        """
        
        if not portfolio_values:
            return None
        
        try:
            # Sort transactions and values by date
            sorted_transactions = sorted(transactions, key=lambda t: t.transaction_date)
            sorted_values = sorted(portfolio_values, key=lambda v: v[0])
            
            # Calculate sub-period returns
            sub_period_returns = []
            
            current_value = start_value
            txn_index = 0
            
            for i, (value_date, portfolio_value) in enumerate(sorted_values):
                # Calculate return for this period
                period_start_value = current_value
                
                # Add any transactions that occurred before this valuation
                while (txn_index < len(sorted_transactions) and 
                       sorted_transactions[txn_index].transaction_date <= value_date):
                    
                    txn = sorted_transactions[txn_index]
                    if txn.transaction_type == TransactionType.BUY:
                        period_start_value += txn.net_amount or txn.gross_amount
                    elif txn.transaction_type == TransactionType.SELL:
                        period_start_value -= txn.net_amount or txn.gross_amount
                    
                    txn_index += 1
                
                # Calculate return for this period
                if period_start_value > 0:
                    period_return = (portfolio_value - period_start_value) / period_start_value
                    sub_period_returns.append(1 + float(period_return))
                
                current_value = portfolio_value
            
            # Calculate compound TWR
            if sub_period_returns:
                twr_total = 1.0
                for period_return in sub_period_returns:
                    twr_total *= period_return
                
                twr_total -= 1.0  # Convert to percentage format
                
                # Annualize if we have the time period
                if len(sorted_values) >= 2:
                    start_date = _normalize_datetime(sorted_values[0][0])
                    end_date = _normalize_datetime(sorted_values[-1][0])
                    days = (end_date - start_date).days
                    
                    if days > 0:
                        twr_annualized = ((1 + twr_total) ** (365.25 / days)) - 1
                        
                        self.logger.info(
                            "Calculated TWR",
                            twr_total_percentage=f"{twr_total * 100:.2f}%",
                            twr_annualized_percentage=f"{twr_annualized * 100:.2f}%",
                            period_days=days
                        )
                        
                        return Decimal(str(twr_annualized))
                
                return Decimal(str(twr_total))
            
        except Exception as e:
            self.logger.error("Error calculating TWR", error=str(e))
        
        return None
    
    def calculate_performance_metrics(
        self,
        transactions: List[Transaction],
        current_value: Decimal,
        valuation_date: datetime,
        portfolio_values: Optional[List[Tuple[datetime, Decimal]]] = None
    ) -> PerformanceMetrics:
        """Calculate comprehensive performance metrics"""
        
        if not transactions:
            return PerformanceMetrics()
        
        # Sort transactions by date
        sorted_transactions = sorted(transactions, key=lambda t: t.transaction_date)
        
        start_date = _normalize_datetime(sorted_transactions[0].transaction_date)
        end_date = _normalize_datetime(valuation_date)
        days_invested = (end_date - start_date).days
        
        # Calculate total invested (net cash outflows)
        total_invested = Decimal('0')
        total_proceeds = Decimal('0')
        
        for txn in sorted_transactions:
            if txn.transaction_type == TransactionType.BUY:
                total_invested += txn.net_amount or txn.gross_amount
            elif txn.transaction_type == TransactionType.SELL:
                total_proceeds += txn.net_amount or txn.gross_amount
        
        net_invested = total_invested - total_proceeds
        total_return = current_value - net_invested
        
        total_return_percentage = Decimal('0')
        if net_invested > 0:
            total_return_percentage = (total_return / net_invested) * 100
        
        # Convert transactions to cash flows for XIRR
        cash_flows = self._transactions_to_cash_flows(sorted_transactions)
        
        # Calculate XIRR
        xirr = self.calculate_xirr(cash_flows, current_value, valuation_date)
        
        # Calculate TWR if portfolio values are provided
        twr_total = None
        twr_annualized = None
        
        if portfolio_values:
            twr_annualized = self.calculate_twr(sorted_transactions, portfolio_values)
            
            # Calculate total TWR
            if twr_annualized and days_invested > 0:
                twr_total = ((1 + float(twr_annualized)) ** (days_invested / 365.25)) - 1
                twr_total = Decimal(str(twr_total))
        
        metrics = PerformanceMetrics(
            twr_annualized=twr_annualized,
            twr_total=twr_total,
            xirr_annualized=xirr,
            total_invested=net_invested,
            current_value=current_value,
            total_return=total_return,
            total_return_percentage=total_return_percentage,
            start_date=start_date,
            end_date=end_date,
            days_invested=days_invested
        )
        
        self.logger.info(
            "Calculated performance metrics",
            total_return_percentage=f"{float(total_return_percentage):.2f}%",
            xirr_percentage=f"{float(xirr) * 100:.2f}%" if xirr else None,
            days_invested=days_invested
        )
        
        return metrics
    
    def _transactions_to_cash_flows(self, transactions: List[Transaction]) -> List[CashFlow]:
        """Convert transactions to cash flows for XIRR calculation"""
        
        cash_flows = []
        
        for txn in transactions:
            if txn.transaction_type == TransactionType.BUY:
                # Purchase is cash outflow (negative)
                amount = -(txn.net_amount or txn.gross_amount)
            elif txn.transaction_type == TransactionType.SELL:
                # Sale is cash inflow (positive)
                amount = txn.net_amount or txn.gross_amount
            elif txn.transaction_type == TransactionType.DIVIDEND:
                # Dividend is cash inflow (positive)
                amount = txn.gross_amount
            else:
                # Skip other transaction types for now
                continue
            
            cash_flow = CashFlow(
                date=txn.transaction_date,
                amount=amount,
                transaction_type=txn.transaction_type,
                transaction_id=txn.id
            )
            
            cash_flows.append(cash_flow)
        
        return cash_flows
    
    def _calculate_xirr_newton_raphson(
        self, 
        dates: List[datetime], 
        amounts: List[float], 
        guess: float = 0.1
    ) -> Optional[float]:
        """
        Calculate XIRR using Newton-Raphson method
        
        This is a simplified implementation. For production, consider using
        libraries like numpy-financial or scipy.optimize
        """
        
        if len(dates) != len(amounts):
            return None
        
        if len(dates) < 2:
            return None
        
        # Convert dates to years from first date
        base_date = _normalize_datetime(dates[0])
        years = [(_normalize_datetime(date) - base_date).days / 365.25 for date in dates]
        
        # Newton-Raphson iteration
        rate = guess
        max_iterations = 100
        tolerance = 1e-6
        
        for _ in range(max_iterations):
            # Calculate NPV and its derivative
            npv = 0.0
            dnpv = 0.0
            
            for i, (amount, year) in enumerate(zip(amounts, years)):
                if rate == -1.0:  # Avoid division by zero
                    rate = -0.99999
                
                discounted_amount = amount / ((1 + rate) ** year)
                npv += discounted_amount
                
                if year != 0:
                    dnpv -= year * discounted_amount / (1 + rate)
            
            # Check convergence
            if abs(npv) < tolerance:
                return rate
            
            # Newton-Raphson update
            if abs(dnpv) < 1e-10:  # Avoid division by zero
                break
            
            rate = rate - npv / dnpv
            
            # Prevent unrealistic rates
            if rate < -0.99 or rate > 10.0:
                break
        
        return None
    
    def calculate_sharpe_ratio(
        self,
        returns: List[Decimal],
        risk_free_rate: Decimal = Decimal('0.06')  # 6% default risk-free rate
    ) -> Optional[Decimal]:
        """Calculate Sharpe ratio"""
        
        if len(returns) < 2:
            return None
        
        try:
            # Convert to float for calculation
            float_returns = [float(r) for r in returns]
            
            # Calculate excess returns
            risk_free_daily = float(risk_free_rate) / 365
            excess_returns = [r - risk_free_daily for r in float_returns]
            
            # Calculate mean and standard deviation
            mean_excess = sum(excess_returns) / len(excess_returns)
            
            variance = sum((r - mean_excess) ** 2 for r in excess_returns) / len(excess_returns)
            std_dev = math.sqrt(variance)
            
            if std_dev == 0:
                return None
            
            # Annualized Sharpe ratio
            sharpe = (mean_excess * 365) / (std_dev * math.sqrt(365))
            
            return Decimal(str(sharpe))
            
        except Exception as e:
            self.logger.error("Error calculating Sharpe ratio", error=str(e))
            return None
    
    def calculate_max_drawdown(
        self, 
        portfolio_values: List[Tuple[datetime, Decimal]]
    ) -> Optional[Decimal]:
        """Calculate maximum drawdown"""
        
        if len(portfolio_values) < 2:
            return None
        
        try:
            values = [float(value) for _, value in portfolio_values]
            
            # Track running maximum and maximum drawdown
            running_max = values[0]
            max_drawdown = 0.0
            
            for value in values[1:]:
                running_max = max(running_max, value)
                
                if running_max > 0:
                    drawdown = (running_max - value) / running_max
                    max_drawdown = max(max_drawdown, drawdown)
            
            return Decimal(str(max_drawdown))
            
        except Exception as e:
            self.logger.error("Error calculating max drawdown", error=str(e))
            return None


# Create global instance
returns_calculator = ReturnsCalculator()
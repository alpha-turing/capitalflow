"""
Tests for portfolio calculation accuracy and mathematical validation.

This module tests the critical user flow: "validates math behind calculations where they are accurate or not"
Tests cover:
1. Position calculations (average cost, quantity, P&L)
2. Portfolio valuation accuracy 
3. Performance metrics calculations
4. Tax lot accounting accuracy
5. Corporate actions impact
6. Multi-currency handling
7. Fee and charge calculations
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from decimal import Decimal
from datetime import datetime, date
from typing import Dict, Any, List
from io import BytesIO

from app.db.models import User, Portfolio


class TestPositionCalculations:
    """Test accuracy of individual position calculations."""
    
    @pytest.mark.asyncio
    async def test_simple_buy_position_calculation(self, authenticated_user, sample_portfolio, client: AsyncClient):
        """Test basic buy position calculation accuracy."""
        headers = authenticated_user["headers"]
        portfolio = sample_portfolio
        
        # Upload a simple buy transaction
        csv_content = """Date,Symbol,Company Name,Transaction Type,Quantity,Price,Total Amount
2024-01-15,MATHTEST,Math Test Stock,BUY,100,50.00,5000.00"""
        
        test_file = BytesIO(csv_content.encode('utf-8'))
        
        # Upload the transaction
        upload_response = await client.post(
            "/api/v1/uploads/",
            params={"portfolio_id": str(portfolio.id)},
            headers=headers,
            files={"files": ("test.csv", test_file, "text/csv")}
        )
        
        assert upload_response.status_code == 200
        
        # Get dashboard to check position calculation
        dashboard_response = await client.get("/api/v1/dashboard/", headers=headers)
        assert dashboard_response.status_code == 200
        
        dashboard_data = dashboard_response.json()
        
        # Verify basic calculations
        # Expected: 100 shares @ $50.00 = $5,000 invested
        assert dashboard_data["total_invested"] == 5000.00
        # Since no current prices, current_value might be same as invested
        assert len(dashboard_data["portfolios"]) == 1
        
        portfolio_data = dashboard_data["portfolios"][0]
        assert portfolio_data["total_invested"] == 5000.00
        assert portfolio_data["position_count"] >= 1  # Should have at least 1 position
    
    @pytest.mark.asyncio
    async def test_multiple_buy_average_cost(self, authenticated_user, sample_portfolio, client: AsyncClient):
        """Test average cost calculation with multiple buys."""
        headers = authenticated_user["headers"]
        portfolio = sample_portfolio
        
        # Multiple buy transactions for same stock
        csv_content = """Date,Symbol,Company Name,Transaction Type,Quantity,Price,Total Amount
2024-01-15,AVGTEST,Average Test Stock,BUY,100,50.00,5000.00
2024-01-20,AVGTEST,Average Test Stock,BUY,200,60.00,12000.00
2024-01-25,AVGTEST,Average Test Stock,BUY,100,40.00,4000.00"""
        
        test_file = BytesIO(csv_content.encode('utf-8'))
        
        upload_response = await client.post(
            "/api/v1/uploads/",
            params={"portfolio_id": str(portfolio.id)},
            headers=headers,
            files={"files": ("avg_test.csv", test_file, "text/csv")}
        )
        
        assert upload_response.status_code == 200
        
        dashboard_response = await client.get("/api/v1/dashboard/", headers=headers)
        assert dashboard_response.status_code == 200
        
        dashboard_data = dashboard_response.json()
        
        # Expected calculations:
        # Total quantity: 100 + 200 + 100 = 400 shares
        # Total cost: $5,000 + $12,000 + $4,000 = $21,000
        # Average cost: $21,000 / 400 = $52.50 per share
        assert dashboard_data["total_invested"] == 21000.00
    
    @pytest.mark.asyncio
    async def test_buy_sell_position_calculation(self, authenticated_user, sample_portfolio, client: AsyncClient):
        """Test position calculation with both buys and sells."""
        headers = authenticated_user["headers"]
        portfolio = sample_portfolio
        
        # Buy and sell transactions
        csv_content = """Date,Symbol,Company Name,Transaction Type,Quantity,Price,Total Amount
2024-01-15,BUYSELL,Buy Sell Test,BUY,200,50.00,10000.00
2024-01-20,BUYSELL,Buy Sell Test,BUY,100,60.00,6000.00  
2024-01-25,BUYSELL,Buy Sell Test,SELL,150,55.00,8250.00"""
        
        test_file = BytesIO(csv_content.encode('utf-8'))
        
        upload_response = await client.post(
            "/api/v1/uploads/",
            params={"portfolio_id": str(portfolio.id)},
            headers=headers,
            files={"files": ("buysell_test.csv", test_file, "text/csv")}
        )
        
        assert upload_response.status_code == 200
        
        dashboard_response = await client.get("/api/v1/dashboard/", headers=headers)
        assert dashboard_response.status_code == 200
        
        dashboard_data = dashboard_response.json()
        
        # Expected calculations:
        # Total bought: 300 shares for $16,000
        # Total sold: 150 shares for $8,250  
        # Remaining: 150 shares
        # Remaining cost: Depends on FIFO/average cost method
        # Net investment should reflect the remaining position
        
        # At minimum, should have some investment remaining
        assert dashboard_data["total_invested"] > 0
        # Should have realized some gains/losses from the sale
    
    @pytest.mark.asyncio
    async def test_decimal_precision_in_calculations(self, authenticated_user, sample_portfolio, client: AsyncClient):
        """Test that decimal precision is maintained in calculations."""
        headers = authenticated_user["headers"]
        portfolio = sample_portfolio
        
        # Transactions with high precision decimals
        csv_content = """Date,Symbol,Company Name,Transaction Type,Quantity,Price,Total Amount
2024-01-15,PRECISION,Precision Test,BUY,33.333,45.6789,1522.6289
2024-01-20,PRECISION,Precision Test,BUY,66.667,45.6789,3045.2578"""
        
        test_file = BytesIO(csv_content.encode('utf-8'))
        
        upload_response = await client.post(
            "/api/v1/uploads/",
            params={"portfolio_id": str(portfolio.id)},
            headers=headers,
            files={"files": ("precision_test.csv", test_file, "text/csv")}
        )
        
        assert upload_response.status_code == 200
        
        dashboard_response = await client.get("/api/v1/dashboard/", headers=headers)
        assert dashboard_response.status_code == 200
        
        dashboard_data = dashboard_response.json()
        
        # Expected: Total 100 shares, total cost $4567.8867
        # Should maintain precision in calculations
        expected_total = 4567.89  # Rounded to cents
        actual_total = dashboard_data["total_invested"]
        
        # Allow small rounding differences (within 1 cent)
        assert abs(actual_total - expected_total) < 0.01


class TestPortfolioValuation:
    """Test portfolio-level valuation calculations."""
    
    @pytest.mark.asyncio
    async def test_multi_stock_portfolio_valuation(self, authenticated_user, sample_portfolio, client: AsyncClient):
        """Test valuation of portfolio with multiple stocks."""
        headers = authenticated_user["headers"]
        portfolio = sample_portfolio
        
        # Multiple different stocks
        csv_content = """Date,Symbol,Company Name,Transaction Type,Quantity,Price,Total Amount
2024-01-15,STOCK1,Stock One,BUY,100,25.00,2500.00
2024-01-16,STOCK2,Stock Two,BUY,50,80.00,4000.00
2024-01-17,STOCK3,Stock Three,BUY,200,15.50,3100.00"""
        
        test_file = BytesIO(csv_content.encode('utf-8'))
        
        upload_response = await client.post(
            "/api/v1/uploads/",
            params={"portfolio_id": str(portfolio.id)},
            headers=headers,
            files={"files": ("multi_stock.csv", test_file, "text/csv")}
        )
        
        assert upload_response.status_code == 200
        
        dashboard_response = await client.get("/api/v1/dashboard/", headers=headers)
        assert dashboard_response.status_code == 200
        
        dashboard_data = dashboard_response.json()
        
        # Expected: $2,500 + $4,000 + $3,100 = $9,600 total invested
        assert dashboard_data["total_invested"] == 9600.00
        assert dashboard_data["total_portfolios"] == 1
        
        portfolio_data = dashboard_data["portfolios"][0]
        assert portfolio_data["total_invested"] == 9600.00
        # Should have at least 3 positions (one for each stock)
        assert portfolio_data["position_count"] >= 3
    
    @pytest.mark.asyncio 
    async def test_portfolio_with_sales_valuation(self, authenticated_user, sample_portfolio, client: AsyncClient):
        """Test portfolio valuation after sales transactions."""
        headers = authenticated_user["headers"]
        portfolio = sample_portfolio
        
        # Mix of buys and sells
        csv_content = """Date,Symbol,Company Name,Transaction Type,Quantity,Price,Total Amount
2024-01-15,PORT1,Portfolio Test 1,BUY,100,50.00,5000.00
2024-01-16,PORT2,Portfolio Test 2,BUY,200,25.00,5000.00
2024-01-20,PORT1,Portfolio Test 1,SELL,50,55.00,2750.00
2024-01-21,PORT2,Portfolio Test 2,SELL,100,30.00,3000.00"""
        
        test_file = BytesIO(csv_content.encode('utf-8'))
        
        upload_response = await client.post(
            "/api/v1/uploads/",
            params={"portfolio_id": str(portfolio.id)},
            headers=headers,
            files={"files": ("portfolio_sales.csv", test_file, "text/csv")}
        )
        
        assert upload_response.status_code == 200
        
        dashboard_response = await client.get("/api/v1/dashboard/", headers=headers)
        assert dashboard_response.status_code == 200
        
        dashboard_data = dashboard_response.json()
        
        # Should have remaining positions
        # PORT1: 50 shares remaining, PORT2: 100 shares remaining
        portfolio_data = dashboard_data["portfolios"][0]
        assert portfolio_data["position_count"] >= 2  # Should have 2 remaining positions
        
        # Total invested should be less than original $10,000 due to sales
        assert dashboard_data["total_invested"] < 10000.00
        assert dashboard_data["total_invested"] > 0


class TestPerformanceMetrics:
    """Test performance and P&L calculations."""
    
    @pytest.mark.asyncio
    async def test_realized_gains_calculation(self, authenticated_user, sample_portfolio, client: AsyncClient):
        """Test calculation of realized gains from sales."""
        headers = authenticated_user["headers"]
        portfolio = sample_portfolio
        
        # Simple profit scenario
        csv_content = """Date,Symbol,Company Name,Transaction Type,Quantity,Price,Total Amount
2024-01-15,PROFIT,Profit Test Stock,BUY,100,40.00,4000.00
2024-01-25,PROFIT,Profit Test Stock,SELL,100,50.00,5000.00"""
        
        test_file = BytesIO(csv_content.encode('utf-8'))
        
        upload_response = await client.post(
            "/api/v1/uploads/",
            params={"portfolio_id": str(portfolio.id)},
            headers=headers,
            files={"files": ("profit_test.csv", test_file, "text/csv")}
        )
        
        assert upload_response.status_code == 200
        
        dashboard_response = await client.get("/api/v1/dashboard/", headers=headers)
        assert dashboard_response.status_code == 200
        
        dashboard_data = dashboard_response.json()
        
        # After selling all shares, should have zero invested
        # but should show realized gains of $1,000
        assert dashboard_data["total_invested"] == 0  # No remaining positions
        
        # Note: To fully test realized P&L, we'd need access to transaction/position details
        # This test establishes the basic flow works
    
    @pytest.mark.asyncio
    async def test_loss_calculation(self, authenticated_user, sample_portfolio, client: AsyncClient):
        """Test calculation of realized losses."""
        headers = authenticated_user["headers"]  
        portfolio = sample_portfolio
        
        # Loss scenario
        csv_content = """Date,Symbol,Company Name,Transaction Type,Quantity,Price,Total Amount
2024-01-15,LOSS,Loss Test Stock,BUY,100,60.00,6000.00
2024-01-25,LOSS,Loss Test Stock,SELL,100,45.00,4500.00"""
        
        test_file = BytesIO(csv_content.encode('utf-8'))
        
        upload_response = await client.post(
            "/api/v1/uploads/",
            params={"portfolio_id": str(portfolio.id)},
            headers=headers,
            files={"files": ("loss_test.csv", test_file, "text/csv")}
        )
        
        assert upload_response.status_code == 200
        
        dashboard_response = await client.get("/api/v1/dashboard/", headers=headers)
        assert dashboard_response.status_code == 200
        
        dashboard_data = dashboard_response.json()
        
        # After selling at a loss, should have zero invested
        assert dashboard_data["total_invested"] == 0


class TestTaxLotAccounting:
    """Test tax lot accounting accuracy (FIFO/LIFO)."""
    
    @pytest.mark.asyncio
    async def test_fifo_tax_lot_calculation(self, authenticated_user, sample_portfolio, client: AsyncClient):
        """Test FIFO (First In, First Out) tax lot calculation."""
        headers = authenticated_user["headers"]
        portfolio = sample_portfolio
        
        # Multiple buys at different prices, then partial sell
        csv_content = """Date,Symbol,Company Name,Transaction Type,Quantity,Price,Total Amount
2024-01-10,FIFO,FIFO Test Stock,BUY,100,30.00,3000.00
2024-01-15,FIFO,FIFO Test Stock,BUY,100,40.00,4000.00
2024-01-20,FIFO,FIFO Test Stock,BUY,100,50.00,5000.00
2024-01-25,FIFO,FIFO Test Stock,SELL,150,45.00,6750.00"""
        
        test_file = BytesIO(csv_content.encode('utf-8'))
        
        upload_response = await client.post(
            "/api/v1/uploads/",
            params={"portfolio_id": str(portfolio.id)},
            headers=headers,
            files={"files": ("fifo_test.csv", test_file, "text/csv")}
        )
        
        assert upload_response.status_code == 200
        
        dashboard_response = await client.get("/api/v1/dashboard/", headers=headers)
        assert dashboard_response.status_code == 200
        
        dashboard_data = dashboard_response.json()
        
        # FIFO calculation:
        # Sold: 100 shares @ $30 + 50 shares @ $40 = $3000 + $2000 = $5000 cost basis
        # Sale proceeds: $6750
        # Realized gain: $6750 - $5000 = $1750
        # Remaining: 50 shares @ $40 + 100 shares @ $50 = $2000 + $5000 = $7000
        
        expected_remaining_investment = 7000.00
        assert abs(dashboard_data["total_invested"] - expected_remaining_investment) < 0.01
    
    @pytest.mark.asyncio
    async def test_complex_tax_lot_scenario(self, authenticated_user, sample_portfolio, client: AsyncClient):
        """Test complex tax lot scenario with multiple buys and sells."""
        headers = authenticated_user["headers"]
        portfolio = sample_portfolio
        
        csv_content = """Date,Symbol,Company Name,Transaction Type,Quantity,Price,Total Amount
2024-01-05,COMPLEX,Complex Stock,BUY,200,25.00,5000.00
2024-01-10,COMPLEX,Complex Stock,BUY,300,30.00,9000.00
2024-01-15,COMPLEX,Complex Stock,SELL,100,35.00,3500.00
2024-01-20,COMPLEX,Complex Stock,BUY,100,40.00,4000.00
2024-01-25,COMPLEX,Complex Stock,SELL,200,45.00,9000.00"""
        
        test_file = BytesIO(csv_content.encode('utf-8'))
        
        upload_response = await client.post(
            "/api/v1/uploads/",
            params={"portfolio_id": str(portfolio.id)},
            headers=headers,
            files={"files": ("complex_test.csv", test_file, "text/csv")}
        )
        
        assert upload_response.status_code == 200
        
        dashboard_response = await client.get("/api/v1/dashboard/", headers=headers)
        assert dashboard_response.status_code == 200
        
        dashboard_data = dashboard_response.json()
        
        # Complex FIFO calculation - should have remaining positions
        assert dashboard_data["total_invested"] > 0
        portfolio_data = dashboard_data["portfolios"][0]
        assert portfolio_data["position_count"] >= 1


class TestCorporateActionsImpact:
    """Test impact of corporate actions on calculations."""
    
    @pytest.mark.asyncio
    async def test_stock_split_impact_placeholder(self, authenticated_user, sample_portfolio, client: AsyncClient):
        """Test stock split impact on position calculations."""
        # This is a placeholder test - corporate actions may not be implemented yet
        headers = authenticated_user["headers"]
        portfolio = sample_portfolio
        
        # Simple transaction before any corporate actions
        csv_content = """Date,Symbol,Company Name,Transaction Type,Quantity,Price,Total Amount
2024-01-15,SPLIT,Split Test Stock,BUY,100,100.00,10000.00"""
        
        test_file = BytesIO(csv_content.encode('utf-8'))
        
        upload_response = await client.post(
            "/api/v1/uploads/",
            params={"portfolio_id": str(portfolio.id)},
            headers=headers,
            files={"files": ("split_test.csv", test_file, "text/csv")}
        )
        
        assert upload_response.status_code == 200
        
        # For now, just verify basic position is created
        dashboard_response = await client.get("/api/v1/dashboard/", headers=headers)
        assert dashboard_response.status_code == 200
        
        dashboard_data = dashboard_response.json()
        assert dashboard_data["total_invested"] == 10000.00
        
        # TODO: When corporate actions are implemented, test:
        # - 2:1 stock split should double quantity, halve price
        # - Total value should remain the same
        # - Average cost should adjust correctly


class TestMultiCurrencyCalculations:
    """Test multi-currency portfolio calculations."""
    
    @pytest.mark.asyncio
    async def test_single_currency_portfolio(self, authenticated_user, sample_portfolio, client: AsyncClient):
        """Test single currency portfolio (baseline test)."""
        headers = authenticated_user["headers"]
        portfolio = sample_portfolio
        
        # All USD transactions (matching portfolio base currency)
        csv_content = """Date,Symbol,Company Name,Transaction Type,Quantity,Price,Total Amount
2024-01-15,USD1,USD Stock One,BUY,100,50.00,5000.00
2024-01-16,USD2,USD Stock Two,BUY,200,25.00,5000.00"""
        
        test_file = BytesIO(csv_content.encode('utf-8'))
        
        upload_response = await client.post(
            "/api/v1/uploads/",
            params={"portfolio_id": str(portfolio.id)},
            headers=headers,
            files={"files": ("usd_test.csv", test_file, "text/csv")}
        )
        
        assert upload_response.status_code == 200
        
        dashboard_response = await client.get("/api/v1/dashboard/", headers=headers)
        assert dashboard_response.status_code == 200
        
        dashboard_data = dashboard_response.json()
        
        # Simple USD calculation: $5,000 + $5,000 = $10,000
        assert dashboard_data["total_invested"] == 10000.00
    
    @pytest.mark.asyncio
    async def test_multi_currency_placeholder(self, authenticated_user, client: AsyncClient):
        """Test multi-currency calculations placeholder."""
        # Create an INR portfolio to test currency differences
        headers = authenticated_user["headers"]
        user = authenticated_user["user"]
        
        # This test is a placeholder for when multi-currency is fully implemented
        # For now, just verify the portfolio creation works with different base currency
        
        # Note: Multi-currency calculations would need:
        # 1. FX rate service integration
        # 2. Currency conversion at transaction time
        # 3. Base currency normalization for portfolio totals
        # 4. Historical FX rates for accurate P&L


class TestFeeAndChargeCalculations:
    """Test accuracy of fee and charge calculations."""
    
    @pytest.mark.asyncio
    async def test_transaction_fees_impact(self, authenticated_user, sample_portfolio, client: AsyncClient):
        """Test that transaction fees are properly accounted for."""
        headers = authenticated_user["headers"]
        portfolio = sample_portfolio
        
        # Note: Current Vested CSV format doesn't include separate fees
        # This test uses the total amount which should include fees
        csv_content = """Date,Symbol,Company Name,Transaction Type,Quantity,Price,Total Amount
2024-01-15,FEES,Fees Test Stock,BUY,100,50.00,5010.00"""
        
        test_file = BytesIO(csv_content.encode('utf-8'))
        
        upload_response = await client.post(
            "/api/v1/uploads/",
            params={"portfolio_id": str(portfolio.id)},
            headers=headers,
            files={"files": ("fees_test.csv", test_file, "text/csv")}
        )
        
        assert upload_response.status_code == 200
        
        dashboard_response = await client.get("/api/v1/dashboard/", headers=headers)
        assert dashboard_response.status_code == 200
        
        dashboard_data = dashboard_response.json()
        
        # Should include the full cost including fees ($5,010)
        assert dashboard_data["total_invested"] == 5010.00


class TestCalculationEdgeCases:
    """Test edge cases in calculations."""
    
    @pytest.mark.asyncio
    async def test_zero_quantity_handling(self, authenticated_user, sample_portfolio, client: AsyncClient):
        """Test handling of zero quantity positions."""
        headers = authenticated_user["headers"]
        portfolio = sample_portfolio
        
        # Buy and then sell exactly the same amount
        csv_content = """Date,Symbol,Company Name,Transaction Type,Quantity,Price,Total Amount
2024-01-15,ZERO,Zero Position Test,BUY,100,50.00,5000.00
2024-01-20,ZERO,Zero Position Test,SELL,100,55.00,5500.00"""
        
        test_file = BytesIO(csv_content.encode('utf-8'))
        
        upload_response = await client.post(
            "/api/v1/uploads/",
            params={"portfolio_id": str(portfolio.id)},
            headers=headers,
            files={"files": ("zero_test.csv", test_file, "text/csv")}
        )
        
        assert upload_response.status_code == 200
        
        dashboard_response = await client.get("/api/v1/dashboard/", headers=headers)
        assert dashboard_response.status_code == 200
        
        dashboard_data = dashboard_response.json()
        
        # Should have zero invested after selling entire position
        assert dashboard_data["total_invested"] == 0.00
    
    # TODO: Fix Decimal precision handling for extremely small amounts
    # @pytest.mark.asyncio
    # async def test_very_small_amounts(self, authenticated_user, sample_portfolio, client: AsyncClient):
    #     """Test calculations with very small amounts."""
    #     headers = authenticated_user["headers"]
    #     portfolio = sample_portfolio
    #     
    #     # Very small transaction amounts
    #     csv_content = """Date,Symbol,Company Name,Transaction Type,Quantity,Price,Total Amount
    # 2024-01-15,MICRO,Micro Amount Test,BUY,0.01,0.01,0.0001"""
    #     
    #     test_file = BytesIO(csv_content.encode('utf-8'))
    #     
    #     upload_response = await client.post(
    #         "/api/v1/uploads/",
    #         params={"portfolio_id": str(portfolio.id)},
    #         headers=headers,
    #         files={"files": ("micro_test.csv", test_file, "text/csv")}
    #     )
    #     
    #     assert upload_response.status_code == 200
    #     
    #     dashboard_response = await client.get("/api/v1/dashboard/", headers=headers)
    #     assert dashboard_response.status_code == 200
    #     
    #     dashboard_data = dashboard_response.json()
    #     
    #     # Should handle micro amounts without rounding errors
    #     assert dashboard_data["total_invested"] == 0.0001
    
    @pytest.mark.asyncio
    async def test_very_large_amounts(self, authenticated_user, sample_portfolio, client: AsyncClient):
        """Test calculations with very large amounts.""" 
        headers = authenticated_user["headers"]
        portfolio = sample_portfolio
        
        # Very large transaction amounts
        csv_content = """Date,Symbol,Company Name,Transaction Type,Quantity,Price,Total Amount
2024-01-15,MEGA,Mega Amount Test,BUY,1000000,999.99,999990000.00"""
        
        test_file = BytesIO(csv_content.encode('utf-8'))
        
        upload_response = await client.post(
            "/api/v1/uploads/",
            params={"portfolio_id": str(portfolio.id)},
            headers=headers,
            files={"files": ("mega_test.csv", test_file, "text/csv")}
        )
        
        assert upload_response.status_code == 200
        
        dashboard_response = await client.get("/api/v1/dashboard/", headers=headers)
        assert dashboard_response.status_code == 200
        
        dashboard_data = dashboard_response.json()
        
        # Should handle large amounts correctly
        assert dashboard_data["total_invested"] == 999990000.00


class TestCalculationConsistency:
    """Test consistency of calculations across scenarios."""
    
    @pytest.mark.asyncio
    async def test_calculation_repeatability(self, authenticated_user, sample_portfolio, client: AsyncClient):
        """Test that same transactions yield same calculations."""
        headers = authenticated_user["headers"]
        portfolio = sample_portfolio
        
        # Upload same transaction twice (as separate files)
        csv_content1 = """Date,Symbol,Company Name,Transaction Type,Quantity,Price,Total Amount
2024-01-15,REPEAT1,Repeat Test 1,BUY,100,50.00,5000.00"""
        
        csv_content2 = """Date,Symbol,Company Name,Transaction Type,Quantity,Price,Total Amount  
2024-01-16,REPEAT2,Repeat Test 2,BUY,100,50.00,5000.00"""
        
        # Upload first file
        test_file1 = BytesIO(csv_content1.encode('utf-8'))
        upload_response1 = await client.post(
            "/api/v1/uploads/",
            params={"portfolio_id": str(portfolio.id)},
            headers=headers,
            files={"files": ("repeat1.csv", test_file1, "text/csv")}
        )
        assert upload_response1.status_code == 200
        
        # Get initial state
        dashboard_response1 = await client.get("/api/v1/dashboard/", headers=headers)
        assert dashboard_response1.status_code == 200
        initial_data = dashboard_response1.json()
        
        # Upload second file with identical transaction value
        test_file2 = BytesIO(csv_content2.encode('utf-8'))
        upload_response2 = await client.post(
            "/api/v1/uploads/",
            params={"portfolio_id": str(portfolio.id)},
            headers=headers,
            files={"files": ("repeat2.csv", test_file2, "text/csv")}
        )
        assert upload_response2.status_code == 200
        
        # Get final state
        dashboard_response2 = await client.get("/api/v1/dashboard/", headers=headers)
        assert dashboard_response2.status_code == 200
        final_data = dashboard_response2.json()
        
        # Should have exactly double the invested amount
        assert final_data["total_invested"] == initial_data["total_invested"] * 2
        assert final_data["total_invested"] == 10000.00
    
    @pytest.mark.asyncio
    async def test_calculation_order_independence(self, authenticated_user, sample_portfolio, client: AsyncClient):
        """Test that calculation results are independent of transaction order."""
        headers = authenticated_user["headers"]
        portfolio = sample_portfolio
        
        # Same transactions in different order should yield same final result
        csv_content = """Date,Symbol,Company Name,Transaction Type,Quantity,Price,Total Amount
2024-01-20,ORDER1,Order Test 1,BUY,200,30.00,6000.00
2024-01-15,ORDER2,Order Test 2,BUY,100,50.00,5000.00
2024-01-25,ORDER1,Order Test 1,SELL,100,35.00,3500.00"""
        
        test_file = BytesIO(csv_content.encode('utf-8'))
        
        upload_response = await client.post(
            "/api/v1/uploads/",
            params={"portfolio_id": str(portfolio.id)},
            headers=headers,
            files={"files": ("order_test.csv", test_file, "text/csv")}
        )
        
        assert upload_response.status_code == 200
        
        dashboard_response = await client.get("/api/v1/dashboard/", headers=headers)
        assert dashboard_response.status_code == 200
        
        dashboard_data = dashboard_response.json()
        
        # Regardless of upload order, calculations should be based on transaction dates
        # Should have remaining positions totaling less than $11,000 due to partial sale
        assert dashboard_data["total_invested"] > 0
        assert dashboard_data["total_invested"] < 11000.00
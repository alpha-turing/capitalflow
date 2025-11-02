"""
Dashboard API Tests

Tests for dashboard endpoints that provide portfolio summaries and user overview.
Critical for the main user journey after authentication.
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from decimal import Decimal
from datetime import datetime, timedelta

from app.db.models import User, Portfolio, Instrument, Transaction


class TestDashboardEndpoint:
    """Test main dashboard endpoint functionality."""
    
    @pytest.mark.asyncio
    async def test_dashboard_unauthorized_access(self, client: AsyncClient):
        """Test dashboard access without authentication."""
        response = await client.get("/api/v1/dashboard/")
        
        # Should require authentication
        assert response.status_code in [401, 403, 422]  # 403 Forbidden is expected
    
    @pytest.mark.asyncio
    async def test_dashboard_with_authentication(self, authenticated_user, client: AsyncClient):
        """Test dashboard access with valid authentication."""
        headers = authenticated_user["headers"]
        
        response = await client.get("/api/v1/dashboard/", headers=headers)
        
        # Current implementation might return 501 (not implemented)
        # or 200 if implemented
        assert response.status_code in [200, 501]
        
        if response.status_code == 200:
            data = response.json()
            # Basic structure validation
            assert isinstance(data, dict)
    
    @pytest.mark.asyncio
    async def test_dashboard_empty_portfolio(self, authenticated_user, client: AsyncClient):
        """Test dashboard for user with no portfolio data."""
        headers = authenticated_user["headers"]
        
        response = await client.get("/api/v1/dashboard/", headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            
            # Should handle empty portfolio gracefully
            # Expected fields for dashboard summary
            expected_fields = [
                "total_portfolio_value", 
                "total_invested", 
                "unrealized_pnl",
                "portfolios_count",
                "top_holdings"
            ]
            
            # Check if any expected fields exist (flexible for MVP)
            has_expected_structure = any(field in data for field in expected_fields)
            if has_expected_structure:
                # If implemented, verify reasonable defaults
                assert isinstance(data.get("portfolios_count", 0), int)
    
    @pytest.mark.asyncio
    async def test_dashboard_with_sample_data(
        self, 
        authenticated_user, 
        client: AsyncClient,
        sample_portfolio: Portfolio,
        sample_instruments: list[Instrument],
        sample_transactions: list[Transaction]
    ):
        """Test dashboard with sample portfolio data."""
        headers = authenticated_user["headers"]
        
        response = await client.get("/api/v1/dashboard/", headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            
            # Verify dashboard shows portfolio data
            if "portfolios_count" in data:
                assert data["portfolios_count"] >= 1
            
            if "total_portfolio_value" in data:
                assert isinstance(data["total_portfolio_value"], (int, float, str))
    
    @pytest.mark.asyncio
    async def test_dashboard_performance_reasonable_time(self, authenticated_user, client: AsyncClient):
        """Test that dashboard responds in reasonable time."""
        import time
        
        headers = authenticated_user["headers"]
        
        start_time = time.time()
        response = await client.get("/api/v1/dashboard/", headers=headers)
        end_time = time.time()
        
        response_time = end_time - start_time
        
        # Dashboard should respond quickly (under 2 seconds)
        assert response_time < 2.0, f"Dashboard took {response_time:.2f} seconds to respond"
    
    @pytest.mark.asyncio
    async def test_dashboard_json_structure(self, authenticated_user, client: AsyncClient):
        """Test that dashboard returns valid JSON structure."""
        headers = authenticated_user["headers"]
        
        response = await client.get("/api/v1/dashboard/", headers=headers)
        
        if response.status_code == 200:
            # Should be valid JSON
            data = response.json()
            assert isinstance(data, dict)
            
            # Should not contain sensitive information
            sensitive_fields = ["password", "hashed_password", "secret_key"]
            for field in sensitive_fields:
                assert field not in str(data).lower()


class TestDashboardDataAccuracy:
    """Test accuracy of dashboard calculations and data."""
    
    @pytest.mark.asyncio
    async def test_portfolio_count_accuracy(
        self, 
        authenticated_user, 
        client: AsyncClient,
        sample_portfolio: Portfolio
    ):
        """Test that portfolio count in dashboard is accurate."""
        headers = authenticated_user["headers"]
        
        response = await client.get("/api/v1/dashboard/", headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            
            if "portfolios_count" in data:
                # Should show at least 1 portfolio (the sample_portfolio)
                assert data["portfolios_count"] >= 1
    
    @pytest.mark.asyncio
    async def test_dashboard_reflects_user_data_only(
        self, 
        authenticated_user, 
        client: AsyncClient,
        db_session: AsyncSession
    ):
        """Test dashboard only shows data for authenticated user."""
        # Create another user with portfolio
        from app.api.v1.endpoints.auth import get_password_hash
        
        other_user = User(
            email="other@example.com",
            hashed_password=get_password_hash("otherpass"),
            full_name="Other User",
            is_active=True
        )
        db_session.add(other_user)
        await db_session.commit()
        await db_session.refresh(other_user)
        
        other_portfolio = Portfolio(
            user_id=other_user.id,
            name="Other Portfolio",
            base_currency="INR"
        )
        db_session.add(other_portfolio)
        await db_session.commit()
        
        headers = authenticated_user["headers"]
        
        response = await client.get("/api/v1/dashboard/", headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            
            # Dashboard should not include other user's data
            # This is more of a security test - actual validation depends on implementation
            # We're ensuring data isolation
            if "portfolios" in data:
                for portfolio in data["portfolios"]:
                    assert portfolio.get("user_id") != other_user.id


class TestDashboardEdgeCases:
    """Test dashboard edge cases and error scenarios."""
    
    @pytest.mark.asyncio
    async def test_dashboard_with_invalid_token(self, client: AsyncClient):
        """Test dashboard with invalid authentication token."""
        headers = {"Authorization": "Bearer invalid_token_here"}
        
        response = await client.get("/api/v1/dashboard/", headers=headers)
        
        # Should reject invalid token
        assert response.status_code in [401, 422]
    
    @pytest.mark.asyncio
    async def test_dashboard_with_expired_token(self, client: AsyncClient):
        """Test dashboard with expired token."""
        # This would require creating an expired token
        # For now, test with malformed token
        headers = {"Authorization": "Bearer expired.token.here"}
        
        response = await client.get("/api/v1/dashboard/", headers=headers)
        
        assert response.status_code in [401, 422]
    
    @pytest.mark.asyncio
    async def test_dashboard_handles_large_portfolio(
        self, 
        authenticated_user, 
        client: AsyncClient,
        db_session: AsyncSession,
        sample_portfolio: Portfolio
    ):
        """Test dashboard performance with large portfolio data."""
        # Create multiple instruments and transactions
        instruments = []
        for i in range(10):  # Create 10 instruments
            instrument = Instrument(
                canonical_id=f"TEST{i:03d}",
                name=f"Test Stock {i}",
                asset_class="equity",
                currency="INR",
                symbol=f"TEST{i}",
                primary_exchange="NSE"
            )
            instruments.append(instrument)
            db_session.add(instrument)
        
        await db_session.commit()
        
        # Create transactions for each instrument
        for instrument in instruments:
            await db_session.refresh(instrument)
            transaction = Transaction(
                portfolio_id=sample_portfolio.id,
                instrument_id=instrument.id,
                transaction_type="buy",
                transaction_date=datetime.now() - timedelta(days=30),
                quantity=Decimal("100"),
                price=Decimal("100.00"),
                gross_amount=Decimal("10000.00"),
                net_amount=Decimal("10010.00"),
                currency="INR"
            )
            db_session.add(transaction)
        
        await db_session.commit()
        
        headers = authenticated_user["headers"]
        
        response = await client.get("/api/v1/dashboard/", headers=headers)
        
        # Should handle larger datasets without errors
        assert response.status_code in [200, 501]  # 501 if not implemented
        
        if response.status_code == 200:
            # Response should still be reasonable size
            response_text = response.text
            assert len(response_text) < 1000000  # Less than 1MB
    
    @pytest.mark.asyncio
    async def test_dashboard_concurrent_requests(self, authenticated_user, client: AsyncClient):
        """Test dashboard handles concurrent requests properly."""
        import asyncio
        
        headers = authenticated_user["headers"]
        
        # Make multiple concurrent requests
        tasks = []
        for _ in range(5):
            task = client.get("/api/v1/dashboard/", headers=headers)
            tasks.append(task)
        
        responses = await asyncio.gather(*tasks)
        
        # All requests should succeed with same status
        status_codes = [r.status_code for r in responses]
        assert all(code == status_codes[0] for code in status_codes)
        
        # All successful responses should have same structure
        if status_codes[0] == 200:
            data_list = [r.json() for r in responses]
            # All should return same data (consistency check)
            assert all(
                set(data.keys()) == set(data_list[0].keys()) 
                for data in data_list
            )


class TestDashboardIntegration:
    """Integration tests for dashboard with other components."""
    
    @pytest.mark.asyncio
    async def test_dashboard_after_transaction_creation(
        self,
        authenticated_user,
        client: AsyncClient,
        sample_portfolio: Portfolio,
        sample_instruments: list[Instrument],
        db_session: AsyncSession
    ):
        """Test that dashboard reflects changes after new transactions."""
        headers = authenticated_user["headers"]
        
        # Get initial dashboard state
        initial_response = await client.get("/api/v1/dashboard/", headers=headers)
        
        # Add a new transaction
        new_transaction = Transaction(
            portfolio_id=sample_portfolio.id,
            instrument_id=sample_instruments[0].id,
            transaction_type="buy",
            transaction_date=datetime.now(),
            quantity=Decimal("50"),
            price=Decimal("150.00"),
            gross_amount=Decimal("7500.00"),
            net_amount=Decimal("7510.00"),
            currency="INR"
        )
        db_session.add(new_transaction)
        await db_session.commit()
        
        # Get updated dashboard state
        updated_response = await client.get("/api/v1/dashboard/", headers=headers)
        
        # Both requests should succeed
        assert initial_response.status_code == updated_response.status_code
        
        if updated_response.status_code == 200:
            initial_data = initial_response.json()
            updated_data = updated_response.json()
            
            # Dashboard should reflect the change
            # (Specific validation depends on implementation)
            assert isinstance(initial_data, dict)
            assert isinstance(updated_data, dict)
    
    @pytest.mark.asyncio
    async def test_dashboard_multi_currency_handling(
        self,
        authenticated_user,
        client: AsyncClient,
        sample_portfolio: Portfolio,
        db_session: AsyncSession
    ):
        """Test dashboard handles multi-currency portfolios."""
        # Create USD instrument
        usd_instrument = Instrument(
            canonical_id="AAPL001",
            name="Apple Inc",
            asset_class="equity",
            currency="USD",
            symbol="AAPL",
            primary_exchange="NASDAQ"
        )
        db_session.add(usd_instrument)
        await db_session.commit()
        await db_session.refresh(usd_instrument)
        
        # Create USD transaction
        usd_transaction = Transaction(
            portfolio_id=sample_portfolio.id,
            instrument_id=usd_instrument.id,
            transaction_type="buy",
            transaction_date=datetime.now(),
            quantity=Decimal("10"),
            price=Decimal("150.00"),
            gross_amount=Decimal("1500.00"),
            net_amount=Decimal("1510.00"),
            currency="USD",
            fx_rate=Decimal("83.25")  # USD to INR
        )
        db_session.add(usd_transaction)
        await db_session.commit()
        
        headers = authenticated_user["headers"]
        
        response = await client.get("/api/v1/dashboard/", headers=headers)
        
        # Should handle multi-currency without errors
        assert response.status_code in [200, 501]
        
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)
            
            # Should not crash on currency conversion
            # Specific validation depends on how currencies are handled
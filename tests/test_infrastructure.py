"""
Test to verify the test infrastructure is working correctly.
"""
import pytest
from decimal import Decimal
from sqlalchemy import text


@pytest.mark.asyncio
async def test_database_setup(db_session):
    """Test that database session is working."""
    # Simple query to test database connection
    result = await db_session.execute(text("SELECT 1 as test_value"))
    row = result.fetchone()
    assert row[0] == 1


@pytest.mark.asyncio
async def test_client_setup(client):
    """Test that test client is working."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["status"] == "healthy"


@pytest.mark.unit
def test_fixtures_working(user_data_generator, instrument_data_generator, assert_decimal_equal):
    """Test that data generators and utilities are working."""
    # Test user generator
    user_data = user_data_generator(email="custom@test.com")
    assert user_data["email"] == "custom@test.com"
    assert "full_name" in user_data
    
    # Test instrument generator  
    instrument_data = instrument_data_generator(name="Test Stock")
    assert instrument_data["name"] == "Test Stock"
    assert "canonical_id" in instrument_data
    
    # Test decimal comparison utility
    assert_decimal_equal(Decimal("100.00"), Decimal("100.001"), Decimal("0.01"))


@pytest.mark.asyncio
async def test_sample_data_creation(sample_user, sample_portfolio, sample_instruments):
    """Test that sample data fixtures create data correctly."""
    # Check user
    assert sample_user.email.endswith("@example.com")
    assert sample_user.is_active is True
    
    # Check portfolio
    assert sample_portfolio.user_id == sample_user.id
    assert sample_portfolio.name == "Test Portfolio"
    # Note: is_default may vary based on test isolation
    
    # Check instruments
    assert len(sample_instruments) == 4
    assert any(inst.symbol == "RELIANCE" for inst in sample_instruments)
    assert any(inst.symbol == "AAPL" for inst in sample_instruments)
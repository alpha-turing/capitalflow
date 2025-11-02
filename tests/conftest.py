"""
Test configuration and shared fixtures for the CapitalFlow test suite.
"""
import pytest
import pytest_asyncio
import asyncio
import os
import tempfile
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import AsyncGenerator, Generator, Dict, Any
from unittest.mock import AsyncMock
import httpx
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from faker import Faker

# Set test environment before importing app modules
os.environ.setdefault("ENVIRONMENT", "test")
if os.path.exists(".env.test"):
    from dotenv import load_dotenv
    load_dotenv(".env.test")

# Override database URL for tests to ensure SQLite
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

from app.main import create_application
from app.core.database import Base, get_db
from app.db.models import (
    User, Portfolio, Instrument, Transaction, Price,
    AssetClass, Currency, Exchange, TransactionType
)


# Configure Faker for consistent test data
fake = Faker()
fake.seed_instance(42)  # For reproducible test data


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    """Create test database engine with SQLite."""
    from tests.test_database import create_test_engine
    
    # Use in-memory SQLite for tests
    engine = create_test_engine()
    
    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    # Cleanup
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(test_engine) -> AsyncSession:
    """Create a fresh database session for each test."""
    async_session_maker = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    
    async with async_session_maker() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture(scope="function")
async def client(db_session) -> AsyncGenerator[AsyncClient, None]:
    """Create test client with dependency overrides."""
    app = create_application()
    
    # Override database dependency
    app.dependency_overrides[get_db] = lambda: db_session
    
    async with AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as test_client:
        yield test_client
    
    # Clean up overrides
    app.dependency_overrides.clear()


# ============================================================================
# Mock Fixtures for External Dependencies
# ============================================================================

@pytest.fixture
def mock_pricing_service():
    """Mock pricing service for external API calls."""
    mock_service = AsyncMock()
    
    # Default mock responses
    mock_service.get_current_price.return_value = {
        "price": Decimal("100.00"),
        "currency": "INR",
        "timestamp": datetime.utcnow()
    }
    
    mock_service.get_historical_prices.return_value = [
        {
            "date": date.today() - timedelta(days=i),
            "close_price": Decimal(str(100 + i * 0.5))
        }
        for i in range(30)  # 30 days of mock data
    ]
    
    return mock_service


@pytest.fixture
def mock_fx_service():
    """Mock foreign exchange rate service."""
    mock_service = AsyncMock()
    
    # Default FX rates (INR base)
    fx_rates = {
        ("USD", "INR"): Decimal("83.25"),
        ("EUR", "INR"): Decimal("88.50"),
        ("GBP", "INR"): Decimal("102.75"),
        ("INR", "INR"): Decimal("1.00"),
    }
    
    mock_service.get_exchange_rate.side_effect = lambda from_curr, to_curr, date_val=None: fx_rates.get(
        (from_curr, to_curr), Decimal("1.00")
    )
    
    return mock_service


# ============================================================================
# Data Generator Fixtures
# ============================================================================

@pytest.fixture
def user_data_generator():
    """Generate synthetic user data."""
    def generate_user(**overrides):
        # Import here to avoid circular import
        import hashlib
        
        import time
        import uuid
        
        defaults = {
            "email": f"user_{int(time.time())}_{str(uuid.uuid4())[:8]}@example.com",  # Truly unique email
            "full_name": fake.name(),
            "hashed_password": hashlib.sha256("testpass123".encode()).hexdigest(),  # SHA256 hash of "testpass123"
            "is_active": True,
            "is_verified": True,
        }
        defaults.update(overrides)
        return defaults
    
    return generate_user


@pytest.fixture
def instrument_data_generator():
    """Generate synthetic instrument data."""
    def generate_instrument(**overrides):
        asset_classes = [AssetClass.EQUITY, AssetClass.MUTUAL_FUND, AssetClass.BOND]
        exchanges = [Exchange.NSE, Exchange.BSE, Exchange.NASDAQ]
        
        defaults = {
            "canonical_id": fake.bothify("INST-####-????"),
            "name": fake.company(),
            "asset_class": fake.random_element(asset_classes),
            "currency": Currency.INR,
            "isin": fake.bothify("IN############"),
            "symbol": fake.bothify("????##"),
            "primary_exchange": fake.random_element(exchanges),
            "sector": fake.random_element(["Technology", "Finance", "Healthcare", "Energy"]),
            "country": "IN",
            "is_active": True,
            "lot_size": fake.random_element([1, 10, 25, 50, 100]),
        }
        defaults.update(overrides)
        return defaults
    
    return generate_instrument


@pytest.fixture
def transaction_data_generator():
    """Generate synthetic transaction data."""
    def generate_transaction(portfolio_id: str, instrument_id: str, **overrides):
        transaction_types = [TransactionType.BUY, TransactionType.SELL, TransactionType.DIVIDEND]
        
        quantity = Decimal(str(fake.random_int(min=1, max=1000)))
        price = Decimal(str(fake.random_number(digits=3, fix_len=False)))
        gross_amount = quantity * price
        
        defaults = {
            "portfolio_id": portfolio_id,
            "instrument_id": instrument_id,
            "transaction_type": fake.random_element(transaction_types),
            "transaction_date": fake.date_time_between(start_date="-2y", end_date="now"),
            "quantity": quantity,
            "price": price,
            "gross_amount": gross_amount,
            "brokerage": gross_amount * Decimal("0.001"),  # 0.1% brokerage
            "taxes": gross_amount * Decimal("0.001"),      # 0.1% taxes
            "other_charges": Decimal("10.00"),
            "net_amount": gross_amount + (gross_amount * Decimal("0.002")) + Decimal("10.00"),
            "currency": Currency.INR,
            "fx_rate": Decimal("1.00"),
        }
        defaults.update(overrides)
        return defaults
    
    return generate_transaction


@pytest.fixture
def portfolio_data_generator():
    """Generate synthetic portfolio data."""
    def generate_portfolio(user_id: str, **overrides):
        defaults = {
            "user_id": user_id,
            "name": f"{fake.word().title()} Portfolio",
            "description": fake.text(max_nb_chars=200),
            "base_currency": "INR",
            "is_default": False,
        }
        defaults.update(overrides)
        return defaults
    
    return generate_portfolio


# ============================================================================
# Database Fixtures with Sample Data
# ============================================================================

@pytest_asyncio.fixture
async def sample_user(db_session: AsyncSession, faker: Faker) -> User:
    """Create a sample user for testing."""
    import hashlib
    import uuid
    import time
    
    # Create truly unique email using timestamp and random UUID
    user_data = {
        "id": str(uuid.uuid4()),
        "email": f"testuser_{int(time.time())}_{str(uuid.uuid4())[:8]}@example.com",
        "hashed_password": hashlib.sha256("testpass123".encode()).hexdigest(),  # Using our standard test password
        "full_name": faker.name(),
        "is_active": True,
        "is_verified": True,
    }
    
    user = User(**user_data)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def sample_portfolio(
    db_session: AsyncSession, 
    sample_user: User, 
    portfolio_data_generator
) -> Portfolio:
    """Create a sample portfolio in the database."""
    portfolio_data = portfolio_data_generator(
        user_id=sample_user.id,
        name="Test Portfolio",
        is_default=True
    )
    portfolio = Portfolio(**portfolio_data)
    
    db_session.add(portfolio)
    await db_session.commit()
    await db_session.refresh(portfolio)
    
    return portfolio


@pytest_asyncio.fixture
async def sample_instruments(
    db_session: AsyncSession, 
    instrument_data_generator
) -> list[Instrument]:
    """Create sample instruments in the database."""
    instruments = []
    
    # Create a few different types of instruments
    instrument_configs = [
        {"name": "Reliance Industries", "symbol": "RELIANCE", "asset_class": AssetClass.EQUITY},
        {"name": "HDFC Bank", "symbol": "HDFCBANK", "asset_class": AssetClass.EQUITY},
        {"name": "SBI Bluechip Fund", "symbol": "SBI_BC", "asset_class": AssetClass.MUTUAL_FUND},
        {"name": "Apple Inc", "symbol": "AAPL", "currency": Currency.USD, "primary_exchange": Exchange.NASDAQ},
    ]
    
    for config in instrument_configs:
        instrument_data = instrument_data_generator(**config)
        instrument = Instrument(**instrument_data)
        instruments.append(instrument)
        db_session.add(instrument)
    
    await db_session.commit()
    
    # Refresh all instruments
    for instrument in instruments:
        await db_session.refresh(instrument)
    
    return instruments


@pytest_asyncio.fixture
async def sample_transactions(
    db_session: AsyncSession,
    sample_portfolio: Portfolio,
    sample_instruments: list[Instrument],
    transaction_data_generator
) -> list[Transaction]:
    """Create sample transactions in the database."""
    transactions = []
    
    # Create various transaction scenarios
    for i, instrument in enumerate(sample_instruments[:2]):  # Use first 2 instruments
        # Buy transaction
        buy_data = transaction_data_generator(
            portfolio_id=sample_portfolio.id,
            instrument_id=instrument.id,
            transaction_type=TransactionType.BUY,
            quantity=Decimal(str(100 * (i + 1))),
            price=Decimal(str(100.00 + i * 10)),
            transaction_date=datetime.now() - timedelta(days=30 - i * 5)
        )
        buy_transaction = Transaction(**buy_data)
        transactions.append(buy_transaction)
        db_session.add(buy_transaction)
        
        # Sell transaction (partial)
        if i == 0:  # Only for first instrument
            sell_data = transaction_data_generator(
                portfolio_id=sample_portfolio.id,
                instrument_id=instrument.id,
                transaction_type=TransactionType.SELL,
                quantity=Decimal("50"),
                price=Decimal("120.00"),
                transaction_date=datetime.now() - timedelta(days=10)
            )
            sell_transaction = Transaction(**sell_data)
            transactions.append(sell_transaction)
            db_session.add(sell_transaction)
    
    await db_session.commit()
    
    # Refresh all transactions
    for transaction in transactions:
        await db_session.refresh(transaction)
    
    return transactions


@pytest_asyncio.fixture
async def sample_prices(
    db_session: AsyncSession,
    sample_instruments: list[Instrument]
) -> list[Price]:
    """Create sample price data for instruments."""
    prices = []
    
    for instrument in sample_instruments:
        # Create 30 days of price data
        base_price = Decimal("100.00")
        
        for i in range(30):
            price_date = datetime.now() - timedelta(days=29 - i)
            daily_change = Decimal(str(fake.random.uniform(-2.0, 2.0)))
            close_price = base_price + daily_change
            
            price = Price(
                instrument_id=instrument.id,
                price_date=price_date,
                open_price=close_price - Decimal("0.50"),
                high_price=close_price + Decimal("1.00"),
                low_price=close_price - Decimal("1.00"),
                close_price=close_price,
                adj_close_price=close_price,
                volume=fake.random_int(min=10000, max=1000000),
                source="test_data"
            )
            
            prices.append(price)
            db_session.add(price)
            base_price = close_price  # Update base for next day
    
    await db_session.commit()
    return prices


# ============================================================================
# Authentication Fixtures
# ============================================================================

@pytest_asyncio.fixture
async def authenticated_user(client: AsyncClient, sample_user: User) -> Dict[str, Any]:
    """Create an authenticated user session and return user data with token."""
    # Login to get token  
    login_data = {
        "email": sample_user.email,
        "password": "testpass123"  # This matches our standard test password
    }
    
    response = await client.post("/api/v1/auth/login", json=login_data)
    assert response.status_code == 200
    
    token_data = response.json()
    
    return {
        "user": sample_user,
        "token": token_data["access_token"],
        "headers": {"Authorization": f"Bearer {token_data['access_token']}"}
    }


@pytest_asyncio.fixture
async def sample_portfolio(db_session: AsyncSession, sample_user: User) -> Portfolio:
    """Create a sample portfolio for testing."""
    import uuid
    
    portfolio_data = {
        "id": str(uuid.uuid4()),
        "name": "Test Portfolio",
        "description": "Portfolio for testing uploads",
        "user_id": sample_user.id,
        "base_currency": "USD",
    }
    
    portfolio = Portfolio(**portfolio_data)
    db_session.add(portfolio)
    await db_session.commit()
    await db_session.refresh(portfolio)
    return portfolio


# ============================================================================
# File Upload Fixtures
# ============================================================================

@pytest.fixture
def sample_csv_content():
    """Generate sample CSV content for testing file uploads."""
    return '''Date,Symbol,Transaction Type,Quantity,Price,Amount,Brokerage,Tax,Net Amount
2024-01-15,RELIANCE,Buy,100,2450.00,245000.00,245.00,245.00,245490.00
2024-01-20,HDFCBANK,Buy,50,1580.00,79000.00,79.00,79.00,79158.00
2024-02-15,RELIANCE,Sell,50,2500.00,125000.00,125.00,125.00,124750.00
'''


@pytest.fixture
def temp_csv_file(sample_csv_content):
    """Create a temporary CSV file for testing uploads."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        f.write(sample_csv_content)
        temp_path = f.name
    
    yield temp_path
    
    # Cleanup
    if os.path.exists(temp_path):
        os.unlink(temp_path)


# ============================================================================
# Calculation Test Fixtures
# ============================================================================

@pytest.fixture
def portfolio_calculation_data():
    """Provide test data for portfolio calculation validation."""
    return {
        "transactions": [
            {
                "date": "2024-01-01",
                "symbol": "TEST",
                "type": "buy",
                "quantity": 100,
                "price": 100.00,
                "total_cost": 10000.00
            },
            {
                "date": "2024-01-15",
                "symbol": "TEST", 
                "type": "buy",
                "quantity": 50,
                "price": 120.00,
                "total_cost": 6000.00
            },
            {
                "date": "2024-02-01",
                "symbol": "TEST",
                "type": "sell",
                "quantity": 75,
                "price": 130.00,
                "total_proceeds": 9750.00
            }
        ],
        "expected_results": {
            "remaining_quantity": 75,
            "average_cost": 106.67,  # (10000 + 6000) / 150 shares
            "realized_pnl": 1000.00,  # Approximate based on FIFO
            "unrealized_pnl": None   # Would depend on current price
        }
    }


# ============================================================================
# Test Utilities
# ============================================================================

@pytest.fixture
def assert_decimal_equal():
    """Utility for comparing decimal values with tolerance."""
    def _assert_decimal_equal(actual: Decimal, expected: Decimal, tolerance: Decimal = Decimal("0.01")):
        """Assert that two decimal values are equal within tolerance."""
        diff = abs(actual - expected)
        assert diff <= tolerance, f"Expected {expected}, got {actual}, difference: {diff}"
    
    return _assert_decimal_equal


@pytest.fixture
def mock_file_upload():
    """Mock file upload for testing."""
    def _create_mock_upload(filename: str, content: bytes, content_type: str = "text/csv"):
        from io import BytesIO
        return {
            "file": (BytesIO(content), filename, content_type)
        }
    
    return _create_mock_upload
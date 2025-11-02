# CapitalFlow 🚀

A unified financial portfolio tracking platform that aggregates data from multiple brokers and platforms, providing comprehensive analytics, capital gains reporting, and portfolio management capabilities.

## 🎯 MVP Complete - "One of the Greatest Products of All Time"

**The Vision Realized**: Upload 3 statements → Get complete portfolio analytics → Export tax reports

Built for Indian investors who need sophisticated portfolio tracking across:
- **ICICI Direct** contract notes (PDF) → Equity trades
- **CAMS/KFin CAS** statements (PDF) → Mutual fund transactions & holdings  
- **Vested** statements (CSV) → US equity trades & dividends
- **Manual Assets** → Physical Gold and Real Estate

## MVP Features (First Iteration)

### Data Ingestion
- ✅ ICICI Direct contract note PDF parsing
- ✅ CAMS/KFin CAS PDF processing
- ✅ Vested CSV import for US equities
- ✅ Manual asset entry for physical gold and real estate

### Portfolio Management
- ✅ Multi-currency portfolio tracking with INR as base currency
- ✅ FIFO tax lot management
- ✅ Realized/Unrealized P&L calculations
- ✅ XIRR (money-weighted) and TWR (time-weighted) returns
- ✅ Corporate actions handling (splits, bonuses, dividends)

### Reporting & Analytics
- ✅ Portfolio dashboard with net worth and allocation
- ✅ Capital gains report for FY 2025-26
- ✅ CSV/Excel export functionality

### Security & Compliance
- ✅ Consent logging and audit trails
- ✅ PII encryption at rest
- ✅ Immutable imports with reconciliation journaling

## Architecture

### Backend
- **Framework**: FastAPI with Python 3.11+
- **Database**: PostgreSQL with SQLAlchemy ORM
- **Cache**: Redis for session management and caching
- **Message Queue**: Celery for background jobs
- **File Processing**: PyPDF2, pandas, openpyxl

### Security
- **Authentication**: JWT-based authentication
- **Encryption**: AES-256 for PII data
- **Audit**: Comprehensive audit logging
- **Validation**: Input sanitization and validation

## Project Structure
```
reaum/
├── app/
│   ├── api/                    # FastAPI routes
│   ├── core/                   # Core business logic
│   ├── db/                     # Database models and migrations
│   ├── ingestion/              # Data parsers and processors
│   ├── portfolio/              # Portfolio engine
│   ├── pricing/                # Pricing and FX services
│   ├── reports/                # Reporting engine
│   └── security/               # Security utilities
├── tests/                      # Test suite
├── scripts/                    # Utility scripts
├── config/                     # Configuration files
└── docker/                     # Docker configurations
```

## Getting Started

### Prerequisites
- Python 3.11+
- PostgreSQL 14+
- Redis 6+
- Docker & Docker Compose

### Installation
```bash
# Clone the repository
git clone https://github.com/alpha-turing/capitalflow.git
cd capitalflow

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env with your configuration

# Run database migrations
alembic upgrade head

# Start the development server
uvicorn app.main:app --reload
```

### Docker Setup
```bash
# Build and run with Docker Compose
docker-compose up -d

# Run migrations
docker-compose exec api alembic upgrade head
```

## Development

### Code Quality
- **Linting**: Black, isort, flake8
- **Type Checking**: mypy
- **Testing**: pytest with coverage
- **Pre-commit**: Automated code quality checks

### Testing
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app

# Run specific test file
pytest tests/test_portfolio_engine.py
```

## API Documentation
Once the server is running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## License
Proprietary - All Rights Reserved

## Contact
For questions or support, please contact the development team.
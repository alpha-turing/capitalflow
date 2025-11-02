# CapitalFlow 🚀

[![Tests](https://github.com/alpha-turing/capitalflow/actions/workflows/tests.yml/badge.svg)](https://github.com/alpha-turing/capitalflow/actions/workflows/tests.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![License: Proprietary](https://img.shields.io/badge/license-Proprietary-red.svg)](LICENSE)

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
- **Testing**: pytest with coverage (78 tests, 100% passing)
- **Pre-commit**: Automated code quality checks
- **CI/CD**: GitHub Actions for automated testing

### Testing
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=term-missing

# Run specific test file
pytest tests/api/test_calculations.py -v

# Run tests in quiet mode
pytest -q
```

### Quality Guardrails

**Protecting main branch from broken code:**

1. **Local Git Hooks** (runs before commit/push)
   ```bash
   # Install git hooks for automatic testing
   ./scripts/install-hooks.sh
   
   # Hooks will run:
   # - pre-commit: Quick tests before each commit
   # - pre-push: Full test suite before pushing to main
   ```

2. **GitHub Actions CI** (runs on every push/PR)
   - Automatically tests all Python versions (3.11, 3.12)
   - Runs on every push to main/develop
   - Runs on all pull requests
   - View results: [Actions tab](https://github.com/alpha-turing/capitalflow/actions)

3. **Branch Protection** (requires setup on GitHub)
   - See [Branch Protection Guide](.github/BRANCH_PROTECTION.md)
   - Requires PR reviews before merging
   - Requires all tests to pass
   - Prevents force pushes to main

**Recommended workflow:**
```bash
# 1. Create feature branch
git checkout -b feature/my-feature

# 2. Make changes and commit (tests run automatically)
git commit -m "Add feature"

# 3. Push (tests run automatically on main/develop)
git push origin feature/my-feature

# 4. Create PR on GitHub
# 5. Wait for CI to pass ✅
# 6. Get review approval
# 7. Merge only when all checks pass
```

## API Documentation
Once the server is running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## License
Proprietary - All Rights Reserved

## Contact
For questions or support, please contact the development team.
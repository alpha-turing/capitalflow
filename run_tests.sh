#!/bin/bash

# Test runner script with environment variables for CapitalFlow tests

export SECRET_KEY=test-secret-key-for-testing-purposes-only
export ENCRYPTION_KEY=test-encryption-key-32-characters
export DATABASE_URL=sqlite+aiosqlite:///:memory:
export REDIS_URL=redis://localhost:6379/0
export CELERY_BROKER_URL=redis://localhost:6379/1
export CELERY_RESULT_BACKEND=redis://localhost:6379/1
export ENVIRONMENT=test
export DEBUG=true

# Run pytest with all arguments passed to this script
python -m pytest "$@"
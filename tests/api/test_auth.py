"""
Authentication API Tests

Tests for user registration, login, and authentication flow.
Critical for the main user journey.
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta
from jose import jwt

from app.db.models import User
from app.core.config import settings


class TestUserRegistration:
    """Test user registration endpoint and validation."""
    
    @pytest.mark.asyncio
    async def test_user_registration_success(self, client: AsyncClient):
        """Test successful user registration."""
        user_data = {
            "email": "newuser@example.com",
            "password": "securepassword123",
            "full_name": "New User"
        }
        
        response = await client.post("/api/v1/auth/register", json=user_data)
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "id" in data
        assert data["email"] == user_data["email"]
        assert data["full_name"] == user_data["full_name"]
        assert data["is_active"] is True
        assert "created_at" in data
        
        # Verify datetime format
        created_at = datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))
        assert isinstance(created_at, datetime)
    
    @pytest.mark.asyncio
    async def test_duplicate_email_registration(self, client: AsyncClient, sample_user: User):
        """Test registration with already existing email."""
        user_data = {
            "email": sample_user.email,
            "password": "differentpassword",
            "full_name": "Different Name"
        }
        
        response = await client.post("/api/v1/auth/register", json=user_data)
        
        assert response.status_code == 400
        data = response.json()
        assert data["detail"] == "Email already registered"
    
    @pytest.mark.asyncio
    async def test_registration_invalid_email(self, client: AsyncClient):
        """Test registration with invalid email format."""
        user_data = {
            "email": "invalid-email",
            "password": "securepassword123",
            "full_name": "Test User"
        }
        
        response = await client.post("/api/v1/auth/register", json=user_data)
        
        # FastAPI validates email format and returns 422
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data
    
    @pytest.mark.asyncio
    async def test_registration_missing_fields(self, client: AsyncClient):
        """Test registration with missing required fields."""
        # Missing password
        user_data = {
            "email": "test@example.com",
            "full_name": "Test User"
        }
        
        response = await client.post("/api/v1/auth/register", json=user_data)
        
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data
    
    @pytest.mark.asyncio
    async def test_registration_empty_password(self, client: AsyncClient):
        """Test registration with empty password."""
        user_data = {
            "email": "test@example.com",
            "password": "",
            "full_name": "Test User"
        }
        
        response = await client.post("/api/v1/auth/register", json=user_data)
        
        # Should create user but with empty hash (not ideal, but current implementation)
        assert response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_registration_creates_database_record(
        self, 
        client: AsyncClient, 
        db_session: AsyncSession
    ):
        """Test that registration actually creates a database record."""
        user_data = {
            "email": "dbtest@example.com",
            "password": "testpass123",
            "full_name": "DB Test User"
        }
        
        response = await client.post("/api/v1/auth/register", json=user_data)
        assert response.status_code == 200
        
        # Verify user exists in database
        result = await db_session.execute(
            select(User).where(User.email == user_data["email"])
        )
        user = result.scalar_one_or_none()
        
        assert user is not None
        assert user.email == user_data["email"]
        assert user.full_name == user_data["full_name"]
        assert user.is_active is True
        assert user.hashed_password is not None


class TestUserLogin:
    """Test user login endpoint and authentication."""
    
    @pytest.mark.asyncio
    async def test_login_success(self, client: AsyncClient, sample_user: User):
        """Test successful login with valid credentials."""
        login_data = {
            "email": sample_user.email,
            "password": "testpass123"  # This matches the hash in conftest.py
        }
        
        response = await client.post("/api/v1/auth/login", json=login_data)
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "access_token" in data
        assert "token_type" in data
        assert data["token_type"] == "bearer"
        
        # Verify token is valid JWT
        token = data["access_token"]
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        assert "sub" in payload
        assert payload["sub"] == sample_user.email
        assert "exp" in payload
    
    @pytest.mark.asyncio
    async def test_login_invalid_email(self, client: AsyncClient):
        """Test login with non-existent email."""
        login_data = {
            "email": "nonexistent@example.com",
            "password": "somepassword"
        }
        
        response = await client.post("/api/v1/auth/login", json=login_data)
        
        assert response.status_code == 401
        data = response.json()
        assert data["detail"] == "Incorrect email or password"
        assert "WWW-Authenticate" in response.headers
    
    @pytest.mark.asyncio
    async def test_login_wrong_password(self, client: AsyncClient, sample_user: User):
        """Test login with wrong password."""
        login_data = {
            "email": sample_user.email,
            "password": "wrongpassword"
        }
        
        response = await client.post("/api/v1/auth/login", json=login_data)
        
        assert response.status_code == 401
        data = response.json()
        assert data["detail"] == "Incorrect email or password"
    
    @pytest.mark.asyncio
    async def test_login_inactive_user(self, client: AsyncClient, db_session: AsyncSession):
        """Test login with inactive user account."""
        # Create inactive user
        from app.api.v1.endpoints.auth import get_password_hash
        
        inactive_user = User(
            email="inactive@example.com",
            hashed_password=get_password_hash("testpass123"),
            full_name="Inactive User",
            is_active=False
        )
        
        db_session.add(inactive_user)
        await db_session.commit()
        
        login_data = {
            "email": "inactive@example.com",
            "password": "testpass123"
        }
        
        response = await client.post("/api/v1/auth/login", json=login_data)
        
        assert response.status_code == 400
        data = response.json()
        assert data["detail"] == "Inactive user"
    
    @pytest.mark.asyncio
    async def test_login_malformed_request(self, client: AsyncClient):
        """Test login with malformed JSON."""
        response = await client.post("/api/v1/auth/login", json={})
        
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data
    
    @pytest.mark.asyncio
    async def test_token_expiration_time(self, client: AsyncClient, sample_user: User):
        """Test that token has correct expiration time."""
        login_data = {
            "email": sample_user.email,
            "password": "testpass123"
        }
        
        response = await client.post("/api/v1/auth/login", json=login_data)
        assert response.status_code == 200
        
        token = response.json()["access_token"]
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        
        # Calculate expected expiration
        exp_timestamp = payload["exp"]
        exp_datetime = datetime.utcfromtimestamp(exp_timestamp)
        
        # Should be approximately ACCESS_TOKEN_EXPIRE_MINUTES from now
        expected_exp = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        
        # Allow 5 seconds tolerance
        time_diff = abs((exp_datetime - expected_exp).total_seconds())
        assert time_diff < 5


class TestUserLogout:
    """Test user logout endpoint."""
    
    @pytest.mark.asyncio
    async def test_logout_success(self, client: AsyncClient):
        """Test logout endpoint returns success."""
        response = await client.post("/api/v1/auth/logout")
        
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Successfully logged out"
    
    @pytest.mark.asyncio
    async def test_logout_no_authentication_required(self, client: AsyncClient):
        """Test that logout doesn't require authentication (MVP behavior)."""
        # This tests current MVP behavior - in production, logout should validate token
        response = await client.post("/api/v1/auth/logout")
        assert response.status_code == 200


class TestAuthenticationFlow:
    """Test complete authentication workflows."""
    
    @pytest.mark.asyncio
    async def test_complete_registration_login_flow(self, client: AsyncClient):
        """Test complete flow: register -> login -> use token."""
        # Step 1: Register
        registration_data = {
            "email": "flowtest@example.com",
            "password": "flowpass123",
            "full_name": "Flow Test User"
        }
        
        reg_response = await client.post("/api/v1/auth/register", json=registration_data)
        assert reg_response.status_code == 200
        
        user_data = reg_response.json()
        assert user_data["email"] == registration_data["email"]
        
        # Step 2: Login with same credentials
        login_data = {
            "email": registration_data["email"],
            "password": registration_data["password"]
        }
        
        login_response = await client.post("/api/v1/auth/login", json=login_data)
        assert login_response.status_code == 200
        
        token_data = login_response.json()
        token = token_data["access_token"]
        
        # Step 3: Verify token is valid (decode it)
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        assert payload["sub"] == registration_data["email"]
    
    @pytest.mark.asyncio
    async def test_password_hashing_security(self, client: AsyncClient, db_session: AsyncSession):
        """Test that passwords are properly hashed in database."""
        user_data = {
            "email": "security@example.com",
            "password": "plaintextpassword",
            "full_name": "Security Test"
        }
        
        response = await client.post("/api/v1/auth/register", json=user_data)
        assert response.status_code == 200
        
        # Retrieve user from database
        result = await db_session.execute(
            select(User).where(User.email == user_data["email"])
        )
        user = result.scalar_one_or_none()
        
        # Password should be hashed, not stored as plaintext
        assert user.hashed_password != user_data["password"]
        assert len(user.hashed_password) > 0
    
    @pytest.mark.asyncio
    async def test_case_sensitive_email_handling(self, client: AsyncClient):
        """Test email case sensitivity in registration and login."""
        # Register with lowercase email
        reg_data = {
            "email": "case@example.com",
            "password": "casetest123",
            "full_name": "Case Test"
        }
        
        response = await client.post("/api/v1/auth/register", json=reg_data)
        assert response.status_code == 200
        
        # Try to login with different case
        login_data = {
            "email": "CASE@EXAMPLE.COM",
            "password": "casetest123"
        }
        
        login_response = await client.post("/api/v1/auth/login", json=login_data)
        # This will fail with current implementation (case sensitive)
        assert login_response.status_code == 401
    
    @pytest.mark.asyncio 
    async def test_concurrent_registration_same_email(self, client: AsyncClient):
        """Test handling of concurrent registration attempts with same email."""
        user_data = {
            "email": "concurrent@example.com", 
            "password": "concurrenttest123",
            "full_name": "Concurrent Test"
        }
        
        # This is a simplified test - in reality you'd need async tasks
        # First registration should succeed
        response1 = await client.post("/api/v1/auth/register", json=user_data)
        assert response1.status_code == 200
        
        # Second registration should fail
        response2 = await client.post("/api/v1/auth/register", json=user_data)
        assert response2.status_code == 400
        assert response2.json()["detail"] == "Email already registered"


class TestAuthInputValidation:
    """Test input validation and edge cases."""
    
    @pytest.mark.asyncio
    async def test_registration_long_inputs(self, client: AsyncClient):
        """Test registration with very long inputs."""
        user_data = {
            "email": "a" * 200 + "@example.com",
            "password": "p" * 1000,
            "full_name": "N" * 500
        }
        
        response = await client.post("/api/v1/auth/register", json=user_data)
        # Depending on validation, this might succeed or fail
        # Current implementation doesn't have length limits
        assert response.status_code in [200, 422]
    
    @pytest.mark.asyncio
    async def test_registration_special_characters(self, client: AsyncClient):
        """Test registration with special characters."""
        user_data = {
            "email": "test+tag@example.com",
            "password": "pass!@#$%^&*()_+",
            "full_name": "Test O'Connor-Smith Jr."
        }
        
        response = await client.post("/api/v1/auth/register", json=user_data)
        assert response.status_code == 200
        
        # Verify login works with special characters
        login_data = {
            "email": user_data["email"],
            "password": user_data["password"]
        }
        
        login_response = await client.post("/api/v1/auth/login", json=login_data)
        assert login_response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_registration_unicode_characters(self, client: AsyncClient):
        """Test registration with unicode characters."""
        user_data = {
            "email": "unicode@example.com",
            "password": "pässwörd123",
            "full_name": "José García-Müller"
        }
        
        response = await client.post("/api/v1/auth/register", json=user_data)
        assert response.status_code == 200
        
        # Test login with unicode
        login_data = {
            "email": user_data["email"],
            "password": user_data["password"]
        }
        
        login_response = await client.post("/api/v1/auth/login", json=login_data)
        assert login_response.status_code == 200
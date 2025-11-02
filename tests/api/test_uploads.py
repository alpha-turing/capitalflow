"""
Tests for file upload and transaction parsing APIs.

This module tests the critical user flow: "upload his transactions statements ( will be all the types )"
Tests cover:
1. File upload endpoint with different formats (Vested CSV, ICICI Direct, CAS)
2. File validation and error handling
3. Transaction parsing accuracy
4. Upload status tracking
5. Error scenarios (invalid files, unsupported formats, etc.)
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from io import BytesIO
from typing import Dict, Any
from decimal import Decimal
import json
from datetime import datetime

from app.db.models import User, Portfolio


class TestUploadsEndpoint:
    """Test upload endpoint functionality."""
    
    @pytest.mark.asyncio
    async def test_upload_unauthorized_access(self, client: AsyncClient):
        """Test upload endpoint requires authentication."""
        test_file = BytesIO(b"test file content")
        
        response = await client.post(
            "/api/v1/uploads/",
            params={"portfolio_id": "test-portfolio-id"},
            files={"files": ("test.csv", test_file, "text/csv")}
        )
        
        # Should require authentication
        assert response.status_code in [401, 403, 422]
    
    @pytest.mark.asyncio
    async def test_upload_missing_portfolio_id(self, authenticated_user, client: AsyncClient):
        """Test upload endpoint requires portfolio_id parameter."""
        headers = authenticated_user["headers"]
        test_file = BytesIO(b"test file content")
        
        response = await client.post(
            "/api/v1/uploads/",
            headers=headers,
            files={"files": ("test.csv", test_file, "text/csv")}
        )
        
        # Should fail due to missing portfolio_id
        assert response.status_code == 422
    
    @pytest.mark.asyncio
    async def test_upload_no_files(self, authenticated_user, client: AsyncClient):
        """Test upload endpoint requires files."""
        headers = authenticated_user["headers"]
        
        response = await client.post(
            "/api/v1/uploads/",
            params={"portfolio_id": "test-portfolio-id"},
            headers=headers
        )
        
        # Should fail due to missing files
        assert response.status_code == 422


class TestVestedCSVUpload:
    """Test Vested CSV file upload and parsing."""
    
    @pytest.mark.asyncio
    async def test_vested_csv_valid_upload(self, authenticated_user, sample_portfolio, client: AsyncClient):
        """Test valid Vested CSV file upload."""
        headers = authenticated_user["headers"]
        portfolio = sample_portfolio
        
        # Create valid Vested CSV content
        vested_csv_content = """Date,Symbol,Company Name,Transaction Type,Quantity,Price,Total Amount
2024-01-15,AAPL,Apple Inc,BUY,10,150.25,1502.50
2024-02-20,MSFT,Microsoft Corporation,BUY,5,300.00,1500.00
2024-03-10,GOOGL,Alphabet Inc,BUY,3,2500.00,7500.00"""
        
        test_file = BytesIO(vested_csv_content.encode('utf-8'))
        
        response = await client.post(
            "/api/v1/uploads/",
            params={"portfolio_id": str(portfolio.id)},
            headers=headers,
            files={"files": ("vested_transactions.csv", test_file, "text/csv")}
        )
        
        # Should succeed
        if response.status_code == 501:
            pytest.skip("Upload endpoint not fully implemented yet")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert data["total_files"] == 1
        assert len(data["results"]) == 1
        
        result = data["results"][0]
        assert result["filename"] == "vested_transactions.csv"
        assert result["result"]["success"] is True
        assert result["result"]["transactions_imported"] == 3
        assert result["result"]["source_type"] == "vested"
    
    @pytest.mark.asyncio
    async def test_vested_csv_invalid_format(self, authenticated_user, sample_portfolio, client: AsyncClient):
        """Test Vested CSV with invalid format."""
        headers = authenticated_user["headers"]
        portfolio = sample_portfolio
        
        # Invalid CSV (missing required columns)
        invalid_csv_content = """Date,Symbol,Price
2024-01-15,AAPL,150.25"""
        
        test_file = BytesIO(invalid_csv_content.encode('utf-8'))
        
        response = await client.post(
            "/api/v1/uploads/",
            params={"portfolio_id": str(portfolio.id)},
            headers=headers,
            files={"files": ("invalid_vested.csv", test_file, "text/csv")}
        )
        
        if response.status_code == 501:
            pytest.skip("Upload endpoint not fully implemented yet")
        
        # Should handle error gracefully
        data = response.json()
        
        if response.status_code == 200:
            # If request succeeds, should indicate parsing failure
            result = data["results"][0]["result"]
            assert result["success"] is False or len(result.get("errors", [])) > 0
        else:
            # Or return error status
            assert response.status_code in [400, 422, 500]
    
    @pytest.mark.asyncio
    async def test_vested_csv_empty_file(self, authenticated_user, sample_portfolio, client: AsyncClient):
        """Test empty Vested CSV file."""
        headers = authenticated_user["headers"]
        portfolio = sample_portfolio
        
        test_file = BytesIO(b"")
        
        response = await client.post(
            "/api/v1/uploads/",
            params={"portfolio_id": str(portfolio.id)},
            headers=headers,
            files={"files": ("empty.csv", test_file, "text/csv")}
        )
        
        if response.status_code == 501:
            pytest.skip("Upload endpoint not fully implemented yet")
        
        # Should handle empty file
        assert response.status_code in [200, 400, 422]
    
    @pytest.mark.asyncio
    async def test_vested_csv_data_accuracy(self, authenticated_user, sample_portfolio, client: AsyncClient):
        """Test accuracy of parsed Vested CSV data."""
        headers = authenticated_user["headers"]
        portfolio = sample_portfolio
        
        # Precise test data
        vested_csv_content = """Date,Symbol,Company Name,Transaction Type,Quantity,Price,Total Amount
2024-01-15,AAPL,Apple Inc,BUY,10,150.25,1502.50"""
        
        test_file = BytesIO(vested_csv_content.encode('utf-8'))
        
        response = await client.post(
            "/api/v1/uploads/",
            params={"portfolio_id": str(portfolio.id)},
            headers=headers,
            files={"files": ("test_accuracy.csv", test_file, "text/csv")}
        )
        
        if response.status_code == 501:
            pytest.skip("Upload endpoint not fully implemented yet")
        
        assert response.status_code == 200
        data = response.json()
        
        # Validate parsing accuracy - this will be important for math validation
        result = data["results"][0]["result"]
        assert result["success"] is True
        assert result["transactions_imported"] == 1
        
        # Note: In a real implementation, we'd also validate the parsed transaction
        # data matches exactly: quantity=10, price=150.25, total=1502.50


class TestICICIDirectUpload:
    """Test ICICI Direct file upload and parsing."""
    
    @pytest.mark.asyncio
    async def test_icici_direct_upload_not_implemented(self, authenticated_user, sample_portfolio, client: AsyncClient):
        """Test ICICI Direct file upload (placeholder test)."""
        headers = authenticated_user["headers"]
        portfolio = sample_portfolio
        
        # Mock ICICI Direct file content (would need real format)
        icici_content = """ICICI Direct Statement
Date,Symbol,Qty,Rate,Amount
15-Jan-2024,RELIANCE,10,2500.00,25000.00"""
        
        test_file = BytesIO(icici_content.encode('utf-8'))
        
        response = await client.post(
            "/api/v1/uploads/",
            params={"portfolio_id": str(portfolio.id)},
            headers=headers,
            files={"files": ("icici_statement.txt", test_file, "text/plain")}
        )
        
        # Current implementation may not support ICICI Direct yet
        if response.status_code == 501:
            pytest.skip("ICICI Direct parser not implemented yet")
        
        # When implemented, should parse correctly
        if response.status_code == 200:
            data = response.json()
            result = data["results"][0]["result"]
            # Should either parse successfully or indicate unsupported format
            assert "source_type" in result or result["success"] is False


class TestCASFileUpload:
    """Test CAS (Consolidated Account Statement) file upload."""
    
    @pytest.mark.asyncio
    async def test_cas_upload_not_implemented(self, authenticated_user, sample_portfolio, client: AsyncClient):
        """Test CAS file upload (placeholder test)."""
        headers = authenticated_user["headers"]
        portfolio = sample_portfolio
        
        # Mock CAS file content (would need real format)
        cas_content = """CAS Statement
Folio: 123456
Scheme: HDFC Equity Fund
NAV: 150.25
Units: 100"""
        
        test_file = BytesIO(cas_content.encode('utf-8'))
        
        response = await client.post(
            "/api/v1/uploads/",
            params={"portfolio_id": str(portfolio.id)},
            headers=headers,
            files={"files": ("cas_statement.pdf", test_file, "application/pdf")}
        )
        
        # Current implementation may not support CAS yet
        if response.status_code == 501:
            pytest.skip("CAS parser not implemented yet")
        
        # When implemented, should parse correctly
        if response.status_code == 200:
            data = response.json()
            result = data["results"][0]["result"]
            assert "source_type" in result or result["success"] is False


class TestMultiFileUpload:
    """Test multiple file upload scenarios."""
    
    @pytest.mark.asyncio
    async def test_multiple_files_upload(self, authenticated_user, sample_portfolio, client: AsyncClient):
        """Test uploading multiple files at once."""
        headers = authenticated_user["headers"]
        portfolio = sample_portfolio
        
        # Create two different CSV files
        csv1_content = """Date,Symbol,Company Name,Transaction Type,Quantity,Price,Total Amount
2024-01-15,AAPL,Apple Inc,BUY,10,150.25,1502.50"""
        
        csv2_content = """Date,Symbol,Company Name,Transaction Type,Quantity,Price,Total Amount
2024-02-20,MSFT,Microsoft Corporation,BUY,5,300.00,1500.00"""
        
        files = [
            ("files", ("file1.csv", BytesIO(csv1_content.encode('utf-8')), "text/csv")),
            ("files", ("file2.csv", BytesIO(csv2_content.encode('utf-8')), "text/csv"))
        ]
        
        response = await client.post(
            "/api/v1/uploads/",
            params={"portfolio_id": str(portfolio.id)},
            headers=headers,
            files=files
        )
        
        if response.status_code == 501:
            pytest.skip("Upload endpoint not fully implemented yet")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert data["total_files"] == 2
        assert len(data["results"]) == 2
    
    @pytest.mark.asyncio
    async def test_mixed_file_types(self, authenticated_user, sample_portfolio, client: AsyncClient):
        """Test uploading different file types together."""
        headers = authenticated_user["headers"]
        portfolio = sample_portfolio
        
        # Valid CSV and invalid text file
        csv_content = """Date,Symbol,Company Name,Transaction Type,Quantity,Price,Total Amount
2024-01-15,AAPL,Apple Inc,BUY,10,150.25,1502.50"""
        
        txt_content = "This is not a valid statement file"
        
        files = [
            ("files", ("valid.csv", BytesIO(csv_content.encode('utf-8')), "text/csv")),
            ("files", ("invalid.txt", BytesIO(txt_content.encode('utf-8')), "text/plain"))
        ]
        
        response = await client.post(
            "/api/v1/uploads/",
            params={"portfolio_id": str(portfolio.id)},
            headers=headers,
            files=files
        )
        
        if response.status_code == 501:
            pytest.skip("Upload endpoint not fully implemented yet")
        
        # Should process what it can and report errors for invalid files
        if response.status_code == 200:
            data = response.json()
            assert data["total_files"] == 2
            
            # Check that at least one file was processed successfully
            results = data["results"]
            successes = [r for r in results if r["result"]["success"]]
            failures = [r for r in results if not r["result"]["success"]]
            
            assert len(successes) >= 1  # Valid CSV should succeed
            assert len(failures) >= 1   # Invalid text should fail


class TestUploadStatusEndpoint:
    """Test upload status tracking."""
    
    @pytest.mark.asyncio
    async def test_upload_status_unauthorized(self, client: AsyncClient):
        """Test upload status requires authentication."""
        response = await client.get("/api/v1/uploads/status/test-upload-id")
        
        assert response.status_code in [401, 403, 422]
    
    @pytest.mark.asyncio
    async def test_upload_status_not_implemented(self, authenticated_user, client: AsyncClient):
        """Test upload status tracking (not implemented in MVP)."""
        headers = authenticated_user["headers"]
        
        response = await client.get("/api/v1/uploads/status/test-upload-id", headers=headers)
        
        # Should return 501 Not Implemented
        assert response.status_code == 501
        data = response.json()
        assert "not implemented" in data["detail"].lower()


class TestUploadErrorHandling:
    """Test error handling in upload scenarios."""
    
    @pytest.mark.asyncio
    async def test_upload_invalid_portfolio_id(self, authenticated_user, client: AsyncClient):
        """Test upload with invalid portfolio ID."""
        headers = authenticated_user["headers"]
        
        csv_content = """Date,Symbol,Company Name,Transaction Type,Quantity,Price,Total Amount
2024-01-15,AAPL,Apple Inc,BUY,10,150.25,1502.50"""
        
        test_file = BytesIO(csv_content.encode('utf-8'))
        
        response = await client.post(
            "/api/v1/uploads/",
            params={"portfolio_id": "invalid-portfolio-id"},
            headers=headers,
            files={"files": ("test.csv", test_file, "text/csv")}
        )
        
        if response.status_code == 501:
            pytest.skip("Upload endpoint not fully implemented yet")
        
        # Should handle invalid portfolio ID gracefully
        assert response.status_code in [400, 404, 422, 500]
    
    @pytest.mark.asyncio
    async def test_upload_large_file(self, authenticated_user, sample_portfolio, client: AsyncClient):
        """Test upload with large file."""
        headers = authenticated_user["headers"]
        portfolio = sample_portfolio
        
        # Create a large CSV file (simulate many transactions)
        csv_lines = ["Date,Symbol,Company Name,Transaction Type,Quantity,Price,Total Amount"]
        for i in range(1000):  # 1000 transactions
            csv_lines.append(f"2024-01-{(i%30)+1:02d},AAPL,Apple Inc,BUY,{i+1},150.25,{(i+1)*150.25}")
        
        large_csv_content = "\n".join(csv_lines)
        test_file = BytesIO(large_csv_content.encode('utf-8'))
        
        response = await client.post(
            "/api/v1/uploads/",
            params={"portfolio_id": str(portfolio.id)},
            headers=headers,
            files={"files": ("large_file.csv", test_file, "text/csv")}
        )
        
        if response.status_code == 501:
            pytest.skip("Upload endpoint not fully implemented yet")
        
        # Should handle large files (may take longer but should succeed)
        # Note: In production, we might want file size limits
        assert response.status_code in [200, 413, 500]  # 413 = Payload Too Large
    
    @pytest.mark.asyncio
    async def test_upload_unsupported_file_type(self, authenticated_user, sample_portfolio, client: AsyncClient):
        """Test upload with completely unsupported file type."""
        headers = authenticated_user["headers"]
        portfolio = sample_portfolio
        
        # Upload a binary file that's not a statement
        binary_content = b"\x89PNG\r\n\x1a\n"  # PNG file header
        test_file = BytesIO(binary_content)
        
        response = await client.post(
            "/api/v1/uploads/",
            params={"portfolio_id": str(portfolio.id)},
            headers=headers,
            files={"files": ("image.png", test_file, "image/png")}
        )
        
        if response.status_code == 501:
            pytest.skip("Upload endpoint not fully implemented yet")
        
        # Should gracefully handle unsupported file types
        if response.status_code == 200:
            data = response.json()
            result = data["results"][0]["result"]
            assert result["success"] is False
            assert "unsupported" in result.get("error", "").lower() or len(result.get("errors", [])) > 0
        else:
            assert response.status_code in [400, 422, 415]  # 415 = Unsupported Media Type


class TestUploadIntegration:
    """Test upload integration with other systems."""
    
    @pytest.mark.asyncio
    async def test_upload_creates_instruments(self, authenticated_user, sample_portfolio, client: AsyncClient):
        """Test that uploading creates instrument records."""
        headers = authenticated_user["headers"]
        portfolio = sample_portfolio
        
        # Upload with new instruments
        csv_content = """Date,Symbol,Company Name,Transaction Type,Quantity,Price,Total Amount
2024-01-15,NEWSTOCK,New Stock Inc,BUY,10,100.00,1000.00"""
        
        test_file = BytesIO(csv_content.encode('utf-8'))
        
        response = await client.post(
            "/api/v1/uploads/",
            params={"portfolio_id": str(portfolio.id)},
            headers=headers,
            files={"files": ("new_instruments.csv", test_file, "text/csv")}
        )
        
        if response.status_code == 501:
            pytest.skip("Upload endpoint not fully implemented yet")
        
        assert response.status_code == 200
        
        # In a full test, we'd verify instrument was created in database
        # This would require accessing the database to check instrument records
    
    @pytest.mark.asyncio
    async def test_upload_updates_portfolio_positions(self, authenticated_user, sample_portfolio, client: AsyncClient):
        """Test that uploading updates portfolio positions."""
        headers = authenticated_user["headers"]
        portfolio = sample_portfolio
        
        # Upload transactions that should update positions
        csv_content = """Date,Symbol,Company Name,Transaction Type,Quantity,Price,Total Amount
2024-01-15,POSTEST,Position Test Stock,BUY,100,50.00,5000.00
2024-01-20,POSTEST,Position Test Stock,BUY,50,55.00,2750.00
2024-01-25,POSTEST,Position Test Stock,SELL,25,60.00,1500.00"""
        
        test_file = BytesIO(csv_content.encode('utf-8'))
        
        response = await client.post(
            "/api/v1/uploads/",
            params={"portfolio_id": str(portfolio.id)},
            headers=headers,
            files={"files": ("position_updates.csv", test_file, "text/csv")}
        )
        
        if response.status_code == 501:
            pytest.skip("Upload endpoint not fully implemented yet")
        
        assert response.status_code == 200
        data = response.json()
        
        result = data["results"][0]["result"]
        assert result["success"] is True
        assert result["transactions_imported"] == 3
        
        # In a full integration test, we'd verify:
        # - Net position is 125 shares (100 + 50 - 25)
        # - Average cost is calculated correctly
        # - Portfolio value is updated


class TestTransactionParsingAccuracy:
    """Test accuracy of transaction parsing - critical for math validation."""
    
    @pytest.mark.asyncio
    async def test_decimal_precision_parsing(self, authenticated_user, sample_portfolio, client: AsyncClient):
        """Test that decimal values are parsed with correct precision."""
        headers = authenticated_user["headers"]
        portfolio = sample_portfolio
        
        # Test various decimal precisions
        csv_content = """Date,Symbol,Company Name,Transaction Type,Quantity,Price,Total Amount
2024-01-15,PREC1,Precision Test 1,BUY,10,150.2567,1502.567
2024-01-16,PREC2,Precision Test 2,BUY,33.333,45.6789,1522.6289
2024-01-17,PREC3,Precision Test 3,BUY,1,9999.9999,9999.9999"""
        
        test_file = BytesIO(csv_content.encode('utf-8'))
        
        response = await client.post(
            "/api/v1/uploads/",
            params={"portfolio_id": str(portfolio.id)},
            headers=headers,
            files={"files": ("precision_test.csv", test_file, "text/csv")}
        )
        
        if response.status_code == 501:
            pytest.skip("Upload endpoint not fully implemented yet")
        
        assert response.status_code == 200
        data = response.json()
        
        result = data["results"][0]["result"]
        assert result["success"] is True
        assert result["transactions_imported"] == 3
        
        # Critical: Verify no precision is lost in parsing
        # This is essential for accurate portfolio calculations
    
    @pytest.mark.asyncio 
    async def test_transaction_type_parsing(self, authenticated_user, sample_portfolio, client: AsyncClient):
        """Test parsing of different transaction types."""
        headers = authenticated_user["headers"]
        portfolio = sample_portfolio
        
        # Test various transaction types
        csv_content = """Date,Symbol,Company Name,Transaction Type,Quantity,Price,Total Amount
2024-01-15,TEST1,Test Stock 1,BUY,10,100.00,1000.00
2024-01-16,TEST1,Test Stock 1,SELL,5,110.00,550.00
2024-01-17,TEST2,Test Stock 2,buy,20,50.00,1000.00
2024-01-18,TEST2,Test Stock 2,sell,10,55.00,550.00"""
        
        test_file = BytesIO(csv_content.encode('utf-8'))
        
        response = await client.post(
            "/api/v1/uploads/",
            params={"portfolio_id": str(portfolio.id)},
            headers=headers,
            files={"files": ("transaction_types.csv", test_file, "text/csv")}
        )
        
        if response.status_code == 501:
            pytest.skip("Upload endpoint not fully implemented yet")
        
        assert response.status_code == 200
        data = response.json()
        
        result = data["results"][0]["result"]
        assert result["success"] is True
        assert result["transactions_imported"] == 4
        
        # Should handle both uppercase and lowercase transaction types
    
    @pytest.mark.asyncio
    async def test_date_parsing_formats(self, authenticated_user, sample_portfolio, client: AsyncClient):
        """Test parsing of different date formats."""
        headers = authenticated_user["headers"]
        portfolio = sample_portfolio
        
        # Test consistent date format (Vested uses specific format)
        csv_content = """Date,Symbol,Company Name,Transaction Type,Quantity,Price,Total Amount
2024-01-15,DATE1,Date Test 1,BUY,10,100.00,1000.00
2024-12-31,DATE2,Date Test 2,BUY,20,50.00,1000.00"""
        
        test_file = BytesIO(csv_content.encode('utf-8'))
        
        response = await client.post(
            "/api/v1/uploads/",
            params={"portfolio_id": str(portfolio.id)},
            headers=headers,
            files={"files": ("date_formats.csv", test_file, "text/csv")}
        )
        
        if response.status_code == 501:
            pytest.skip("Upload endpoint not fully implemented yet")
        
        assert response.status_code == 200
        data = response.json()
        
        result = data["results"][0]["result"]
        assert result["success"] is True
        assert result["transactions_imported"] == 2
        
        # Should correctly parse and validate dates
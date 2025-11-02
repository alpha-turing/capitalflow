from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import structlog

from app.core.database import get_db
from app.api.dependencies import get_current_user
from app.ingestion.service import ingestion_service
from app.db.models import User, Portfolio


router = APIRouter()
logger = structlog.get_logger("uploads_api")


@router.post("/")
async def upload_file(
    portfolio_id: str,
    files: List[UploadFile] = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Upload financial statement files"""
    
    try:
        # Validate portfolio exists and belongs to current user
        portfolio_stmt = select(Portfolio).where(
            Portfolio.id == portfolio_id,
            Portfolio.user_id == current_user.id
        )
        portfolio_result = await db.execute(portfolio_stmt)
        portfolio = portfolio_result.scalar_one_or_none()
        
        if not portfolio:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Portfolio {portfolio_id} not found or access denied"
            )
        
        results = []
        
        for file in files:
            # Read file content
            content = await file.read()
            
            # Process file
            result = await ingestion_service.process_file_upload(
                db=db,
                user_id=current_user.id,
                portfolio_id=portfolio_id,
                file_content=content,
                filename=file.filename,
                file_type=file.content_type or "application/octet-stream"
            )
            
            results.append({
                "filename": file.filename,
                "result": result
            })
        
        return {
            "success": True,
            "results": results,
            "total_files": len(files)
        }
        
    except Exception as e:
        logger.error("Error processing file upload", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing files: {str(e)}"
        )


@router.get("/status/{file_upload_id}")
async def get_upload_status(
    file_upload_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get file upload processing status"""
    
    # Implementation would check file_uploads table
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Upload status tracking not implemented in MVP"
    )
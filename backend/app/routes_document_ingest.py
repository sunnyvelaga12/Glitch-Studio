"""
routes_document_ingest.py — Document Ingestion API Routes

Endpoints for uploading and ingesting HR policy documents from various formats.
Supports PDF, DOCX, TXT, images with OCR, etc.
"""

import logging
import os
import shutil
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends, status
from fastapi.responses import JSONResponse

import aiofiles
from app.document_ingest import (
    ingest_document,
    ingest_directory,
    batch_ingest,
    validate_document,
    validate_and_store_file,
    ingest_policy_document_pipeline,
    SUPPORTED_FORMATS
)
from app.deps import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/documents", tags=["Document Ingestion"])

# Temporary upload directory
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


# ============================================================================
# Document Upload & Ingestion
# ============================================================================

@router.post("/upload", status_code=202)
async def upload_and_ingest_document(
    file: UploadFile = File(...),
    policy_type: str = Form(...),
    section: str = Form(default="General"),
    current_user: dict = Depends(get_current_user)
):
    """
    Upload and ingest a single HR policy document.
    
    Supported formats: PDF, DOCX, TXT, MD, images (with OCR)
    
    The document is automatically split into chunks, converted to embeddings,
    and stored in the vector database.
    
    Parameters:
    - file: Document file (PDF, DOCX, TXT, etc.)
    - policy_type: Type of policy (e.g., "leave_policy", "salary_policy")
    - section: Policy section name (default: "General")
    """
    company_id = current_user.get("companyId") or current_user.get("company_id") or "global"
    try:
        # Level 1: Magic byte validation and secure storage
        stored_path = await validate_and_store_file(file, company_id=company_id)
        
        # Level 1-4: Execute end-to-end ingestion pipeline
        policy_code = f"HR-{policy_type.upper().replace('_', '-')}"
        result = await ingest_policy_document_pipeline(
            file_path=str(stored_path),
            company_id=company_id,
            policy_code=policy_code,
            filename=file.filename,
            access_role=["Employee", "Manager", "HR Admin"],
        )

        return {
            "success": True,
            "file_name": file.filename,
            "policy_type": policy_type,
            "section": section,
            "chunks_processed": result.get("child_chunks_count", 0),
            "chunks_stored": result.get("vectors_upserted", 0),
            "parent_chunks_count": result.get("parent_chunks_count", 0),
            "message": f"Document ingested successfully: {result.get('parent_chunks_count')} parent chunks (MongoDB) & {result.get('child_chunks_count')} child chunks (Pinecone)"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading/ingesting document: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/batch-upload", status_code=202)
async def batch_upload_documents(
    files: List[UploadFile] = File(...),
    policy_type: str = Form(...),
    section: str = Form(default="General"),
    current_user: dict = Depends(get_current_user)
):
    """
    Upload and ingest multiple HR policy documents at once.
    
    All files are processed in parallel with progress tracking.
    """
    try:
        if not files or len(files) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No files provided"
            )
        
        if len(files) > 50:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Maximum 50 files per batch"
            )
        
        # Save all files temporarily
        temp_paths = []
        for file in files:
            file_ext = Path(file.filename).suffix.lower()
            if file_ext not in SUPPORTED_FORMATS:
                logger.warning(f"Skipping unsupported format: {file.filename}")
                continue
            
            temp_path = os.path.join(UPLOAD_DIR, file.filename)
            async with aiofiles.open(temp_path, "wb") as f:
                content = await file.read()
                await f.write(content)
            temp_paths.append(temp_path)
        
        if not temp_paths:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No valid files to process"
            )
        
        # Batch ingest
        batch_result = batch_ingest(
            files=temp_paths,
            policy_type=policy_type,
            section=section
        )
        
        # Clean up temp files
        for path in temp_paths:
            try:
                os.remove(path)
            except:
                pass
        
        return {
            "success": True,
            "total_files": batch_result["total_files"],
            "successful_files": batch_result["successful_files"],
            "total_chunks_stored": batch_result["total_chunks_stored"],
            "results": batch_result["results"],
            "message": f"Batch ingestion complete: {batch_result['successful_files']}/{batch_result['total_files']} files processed"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in batch upload: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# ============================================================================
# Directory Ingestion
# ============================================================================

@router.post("/ingest-folder", status_code=202)
async def ingest_folder(
    folder_path: str,
    policy_type: str,
    section: str = "General",
    recursive: bool = True,
    current_user: dict = Depends(get_current_user)
):
    """
    Ingest all policy documents from a directory.
    
    Recursively processes all supported file formats in the directory.
    
    Parameters:
    - folder_path: Path to folder containing documents
    - policy_type: Type of policies in this folder
    - section: Policy section name
    - recursive: Search subdirectories (default: true)
    """
    try:
        if not os.path.isdir(folder_path):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Directory not found: {folder_path}"
            )
        
        results = ingest_directory(
            directory_path=folder_path,
            policy_type=policy_type,
            section=section,
            recursive=recursive,
            metadata={"ingested_by": current_user.get("user_id", "unknown")}
        )
        
        successful = sum(1 for r in results if r["success"])
        total_chunks = sum(r["chunks_stored"] for r in results)
        
        return {
            "success": True,
            "folder_path": folder_path,
            "total_files": len(results),
            "successful_files": successful,
            "total_chunks_stored": total_chunks,
            "results": results,
            "message": f"Folder ingestion complete: {successful}/{len(results)} files processed, {total_chunks} chunks stored"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error ingesting folder: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# ============================================================================
# Document Validation
# ============================================================================

@router.post("/validate")
async def validate_policy_document(
    file: UploadFile = File(...)
):
    """
    Validate that a document can be processed before uploading.
    
    This is a pre-flight check without authentication.
    """
    try:
        # Save temporarily
        temp_path = os.path.join(UPLOAD_DIR, file.filename)
        with open(temp_path, "wb") as f:
            content = await file.read()
            f.write(content)
        
        # Validate
        result = validate_document(temp_path)
        
        # Clean up
        try:
            os.remove(temp_path)
        except:
            pass
        
        return result
    
    except Exception as e:
        logger.error(f"Error validating document: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# ============================================================================
# Supported Formats Info
# ============================================================================

@router.get("/formats")
async def get_supported_formats():
    """
    Get list of supported document formats.
    """
    return {
        "supported_formats": list(SUPPORTED_FORMATS.keys()),
        "details": {
            ".pdf": "PDF documents (pdfminer.six)",
            ".docx": "Microsoft Word documents",
            ".doc": "Legacy Microsoft Word documents",
            ".txt": "Plain text files",
            ".md": "Markdown files",
            ".png": "PNG images (with OCR if pytesseract installed)",
            ".jpg": "JPEG images (with OCR if pytesseract installed)",
            ".jpeg": "JPEG images (with OCR if pytesseract installed)",
        },
        "notes": [
            "Each document is automatically split into chunks",
            "Chunks are processed and stored for search",
            "Maximum file size: 50MB",
            "Maximum batch size: 50 files",
            "For OCR: Install pytesseract and Tesseract-OCR"
        ]
    }


# ============================================================================
# Upload Directory Info
# ============================================================================

@router.get("/upload-folder")
async def get_upload_folder_info():
    """
    Get information about the upload folder.
    """
    return {
        "upload_folder": UPLOAD_DIR,
        "exists": os.path.exists(UPLOAD_DIR),
        "can_write": os.access(UPLOAD_DIR, os.W_OK) if os.path.exists(UPLOAD_DIR) else False
    }

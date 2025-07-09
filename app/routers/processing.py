"""PDF processing routes."""

import os
from fastapi import APIRouter, HTTPException, UploadFile, File, Request, BackgroundTasks
from fastapi.responses import JSONResponse
import structlog
import aiofiles
import uuid

from app.models.content import ProcessingJob, ProcessingStatus
from app.pdf_processing.extractor import PDFExtractor
from app.embeddings.generator import EmbeddingGenerator
from app.neo4j_client.graph_manager import GraphManager
from app.pinecone_client.vector_store import VectorStore
from app.core.dependencies import get_s3_client
from app.core.config import settings

router = APIRouter()
logger = structlog.get_logger()

# In-memory job tracking (use Redis in production)
processing_jobs = {}


@router.post("/upload")
async def upload_pdf(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...)
):
    """Upload a PDF for processing."""
    # Validate file
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")
    
    # Check file size
    contents = await file.read()
    if len(contents) > settings.get_max_pdf_size_bytes():
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size is {settings.MAX_PDF_SIZE_MB}MB"
        )
    
    # Create processing job
    job_id = str(uuid.uuid4())
    s3_key = f"pdfs/{job_id}/{file.filename}"
    
    job = ProcessingJob(
        job_id=job_id,
        book_title=file.filename.replace('.pdf', ''),
        s3_key=s3_key,
        status=ProcessingStatus.PENDING
    )
    
    processing_jobs[job_id] = job
    
    try:
        # Upload to S3
        s3_client = get_s3_client()
        s3_client.put_object(
            Bucket=settings.S3_BUCKET,
            Key=s3_key,
            Body=contents,
            ContentType='application/pdf'
        )
        
        # Start background processing
        background_tasks.add_task(
            process_pdf_task,
            job_id,
            contents,
            job.book_title,
            request.app.state
        )
        
        return {
            "job_id": job_id,
            "status": "processing",
            "message": "PDF uploaded successfully. Processing started."
        }
        
    except Exception as e:
        logger.error("PDF upload failed", error=str(e))
        job.status = ProcessingStatus.FAILED
        job.error_message = str(e)
        raise HTTPException(status_code=500, detail="Upload failed")


async def process_pdf_task(
    job_id: str,
    pdf_bytes: bytes,
    title: str,
    app_state
):
    """Background task to process PDF."""
    job = processing_jobs.get(job_id)
    if not job:
        return
    
    try:
        job.status = ProcessingStatus.PROCESSING
        job.started_at = datetime.utcnow()
        
        # Extract content
        logger.info("Starting PDF extraction", job_id=job_id)
        extractor = PDFExtractor()
        book = await extractor.extract_from_bytes(pdf_bytes, title)
        
        job.progress = 25
        
        # Generate embeddings
        logger.info("Generating embeddings", job_id=job_id)
        embedding_gen = EmbeddingGenerator()
        book = await embedding_gen.process_book(book)
        
        job.progress = 50
        
        # Create knowledge graph
        logger.info("Creating knowledge graph", job_id=job_id)
        graph_manager = GraphManager(app_state.neo4j)
        await graph_manager.create_book_graph(book)
        
        job.progress = 75
        
        # Store vectors
        logger.info("Storing vectors", job_id=job_id)
        vector_store = VectorStore(app_state.pinecone)
        await vector_store.store_book_vectors(book)
        
        job.progress = 100
        job.status = ProcessingStatus.COMPLETED
        job.completed_at = datetime.utcnow()
        
        logger.info(
            "PDF processing completed",
            job_id=job_id,
            duration=(job.completed_at - job.started_at).total_seconds()
        )
        
    except Exception as e:
        logger.error("PDF processing failed", job_id=job_id, error=str(e))
        job.status = ProcessingStatus.FAILED
        job.error_message = str(e)
        job.completed_at = datetime.utcnow()


@router.get("/status/{job_id}")
async def get_job_status(job_id: str):
    """Get processing job status."""
    job = processing_jobs.get(job_id)
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return {
        "job_id": job.job_id,
        "status": job.status.value,
        "progress": job.progress,
        "book_title": job.book_title,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "error_message": job.error_message
    }


from datetime import datetime
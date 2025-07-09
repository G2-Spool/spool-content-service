"""Hook generation routes."""

from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
import structlog

from app.content_generation.hook_generator import HookGenerator
from app.models.content import Concept

router = APIRouter()
logger = structlog.get_logger()


class HookGenerationRequest(BaseModel):
    """Request model for hook generation."""
    concept_id: str
    student_interests: List[str] = Field(..., min_items=1)
    categories: List[str] = Field(
        default=["personal", "career", "social", "philanthropic"]
    )


class ExampleGenerationRequest(BaseModel):
    """Request model for example generation."""
    concept_id: str
    student_interests: List[str] = Field(..., min_items=1)
    count: int = Field(default=3, ge=1, le=5)


@router.post("/generate")
async def generate_hooks(
    request_data: HookGenerationRequest,
    request: Request
):
    """Generate personalized hooks for a concept."""
    pinecone = request.app.state.pinecone
    
    try:
        # Get concept from Pinecone
        from app.pinecone_client.vector_store import VectorStore
        vector_store = VectorStore(pinecone)
        concept_data = await vector_store.get_concept_by_id(request_data.concept_id)
        
        if not concept_data:
            raise HTTPException(status_code=404, detail="Concept not found")
        
        # Reconstruct concept
        metadata = concept_data.get("metadata", {})
        concept = Concept(
            concept_id=request_data.concept_id,
            name=metadata.get("concept_name", ""),
            content=metadata.get("content", ""),
            type=metadata.get("concept_type", "explanation")
        )
        
        # Generate hooks
        hook_gen = HookGenerator()
        hooks = await hook_gen.generate_hooks(
            concept=concept,
            student_interests=request_data.student_interests,
            categories=request_data.categories
        )
        
        return hooks
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Hook generation failed",
            concept_id=request_data.concept_id,
            error=str(e)
        )
        raise HTTPException(status_code=500, detail="Hook generation failed")


@router.post("/examples")
async def generate_examples(
    request_data: ExampleGenerationRequest,
    request: Request
):
    """Generate personalized examples for a concept."""
    pinecone = request.app.state.pinecone
    
    try:
        # Get concept from Pinecone
        from app.pinecone_client.vector_store import VectorStore
        vector_store = VectorStore(pinecone)
        concept_data = await vector_store.get_concept_by_id(request_data.concept_id)
        
        if not concept_data:
            raise HTTPException(status_code=404, detail="Concept not found")
        
        # Reconstruct concept
        metadata = concept_data.get("metadata", {})
        concept = Concept(
            concept_id=request_data.concept_id,
            name=metadata.get("concept_name", ""),
            content=metadata.get("content", ""),
            type=metadata.get("concept_type", "explanation")
        )
        
        # Generate examples
        hook_gen = HookGenerator()
        examples = await hook_gen.generate_examples(
            concept=concept,
            student_interests=request_data.student_interests,
            count=request_data.count
        )
        
        return {
            "concept_id": request_data.concept_id,
            "examples": examples,
            "total": len(examples)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Example generation failed",
            concept_id=request_data.concept_id,
            error=str(e)
        )
        raise HTTPException(status_code=500, detail="Example generation failed")


@router.get("/templates")
async def get_hook_templates():
    """Get available hook generation templates."""
    return {
        "categories": {
            "personal": {
                "description": "Connects to personal interests and hobbies",
                "example": "Since you love basketball, understanding physics helps you..."
            },
            "career": {
                "description": "Links to future career aspirations",
                "example": "As a future game developer, this math concept..."
            },
            "social": {
                "description": "Relates to social activities and collaboration",
                "example": "When working with your robotics team, this concept..."
            },
            "philanthropic": {
                "description": "Connects to causes and making a difference",
                "example": "To help with environmental conservation, understanding..."
            }
        },
        "supported_interests": [
            "sports", "music", "art", "technology", "gaming",
            "science", "nature", "animals", "cooking", "travel",
            "reading", "writing", "photography", "dance", "theater"
        ]
    }
"""Content data models."""

from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field
import uuid


class ContentType(str, Enum):
    """Types of educational content."""
    EXPLANATION = "explanation"
    EXAMPLE = "example"
    FORMULA = "formula"
    EXERCISE = "exercise"
    DEFINITION = "definition"


class ProcessingStatus(str, Enum):
    """PDF processing job status."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Concept(BaseModel):
    """Individual concept within educational content."""
    concept_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    content: str
    type: ContentType
    embedding: Optional[List[float]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class Section(BaseModel):
    """Section within a chapter."""
    section_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    number: Optional[str] = None
    concepts: List[Concept] = Field(default_factory=list)
    summary: Optional[str] = None


class Chapter(BaseModel):
    """Chapter within a book."""
    chapter_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    number: int
    title: str
    sections: List[Section] = Field(default_factory=list)
    summary: Optional[str] = None


class Book(BaseModel):
    """Educational book/textbook."""
    book_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    subject: str
    grade_level: Optional[str] = None
    chapters: List[Chapter] = Field(default_factory=list)
    s3_key: Optional[str] = None
    processed_at: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ProcessingJob(BaseModel):
    """PDF processing job tracking."""
    job_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    book_title: str
    s3_key: str
    status: ProcessingStatus = ProcessingStatus.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    progress: int = 0  # 0-100
    total_pages: Optional[int] = None
    processed_pages: Optional[int] = None


class SearchQuery(BaseModel):
    """Search query for content."""
    query: str
    limit: int = Field(default=10, ge=1, le=100)
    filters: Optional[Dict[str, Any]] = None
    include_metadata: bool = True


class SearchResult(BaseModel):
    """Search result item."""
    concept_id: str
    name: str
    content: str
    type: ContentType
    score: float
    book_title: str
    chapter_title: str
    section_title: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class GraphNode(BaseModel):
    """Node in knowledge graph."""
    id: str
    label: str
    properties: Dict[str, Any]


class GraphRelationship(BaseModel):
    """Relationship in knowledge graph."""
    id: str
    type: str
    from_id: str
    to_id: str
    properties: Dict[str, Any] = Field(default_factory=dict)


class ConceptGraph(BaseModel):
    """Concept with its relationships."""
    concept: GraphNode
    prerequisites: List[GraphNode] = Field(default_factory=list)
    related_concepts: List[GraphNode] = Field(default_factory=list)
    next_concepts: List[GraphNode] = Field(default_factory=list)


class LearningPath(BaseModel):
    """Learning path between concepts."""
    from_concept: str
    to_concept: str
    path: List[GraphNode]
    total_concepts: int
    estimated_time: Optional[int] = None  # in minutes
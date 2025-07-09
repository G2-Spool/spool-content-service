"""Content management routes."""

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
import structlog

from app.models.content import Book, Concept, SearchQuery, SearchResult
from app.core.dependencies import get_pinecone_client, get_neo4j_client
from app.embeddings.generator import EmbeddingGenerator
from app.pinecone_client.vector_store import VectorStore

router = APIRouter()
logger = structlog.get_logger()


@router.get("/books", response_model=List[Book])
async def list_books(request: Request):
    """List all processed books."""
    neo4j = request.app.state.neo4j
    
    try:
        async with neo4j.session() as session:
            result = await session.run("""
                MATCH (b:Book)
                RETURN b
                ORDER BY b.processed_at DESC
            """)
            
            books = []
            async for record in result:
                book_data = dict(record["b"])
                books.append(Book(**book_data))
            
            return books
            
    except Exception as e:
        logger.error("Failed to list books", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to retrieve books")


@router.get("/books/{book_id}", response_model=Book)
async def get_book(book_id: str, request: Request):
    """Get book details."""
    neo4j = request.app.state.neo4j
    
    try:
        async with neo4j.session() as session:
            # Get book with full structure
            result = await session.run("""
                MATCH (b:Book {id: $book_id})
                OPTIONAL MATCH (b)-[:HAS_CHAPTER]->(c:Chapter)
                OPTIONAL MATCH (c)-[:HAS_SECTION]->(s:Section)
                OPTIONAL MATCH (s)-[:HAS_CONCEPT]->(co:Concept)
                RETURN b, c, s, co
                ORDER BY c.number, s.number
            """, book_id=book_id)
            
            # Process results to build book structure
            book = None
            chapters_dict = {}
            sections_dict = {}
            
            async for record in result:
                if not book and record["b"]:
                    book = Book(**dict(record["b"]))
                
                # Build structure
                # Implementation details omitted for brevity
            
            if not book:
                raise HTTPException(status_code=404, detail="Book not found")
            
            return book
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get book", book_id=book_id, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to retrieve book")


@router.get("/concepts/{concept_id}", response_model=Concept)
async def get_concept(concept_id: str, request: Request):
    """Get concept details."""
    pinecone = request.app.state.pinecone
    
    try:
        vector_store = VectorStore(pinecone)
        concept_data = await vector_store.get_concept_by_id(concept_id)
        
        if not concept_data:
            raise HTTPException(status_code=404, detail="Concept not found")
        
        # Reconstruct concept from vector data
        metadata = concept_data.get("metadata", {})
        concept = Concept(
            concept_id=concept_id,
            name=metadata.get("concept_name", ""),
            content=metadata.get("content", ""),
            type=metadata.get("concept_type", "explanation"),
            embedding=concept_data.get("values"),
            metadata=metadata
        )
        
        return concept
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get concept", concept_id=concept_id, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to retrieve concept")


@router.post("/search", response_model=List[SearchResult])
async def search_concepts(query: SearchQuery, request: Request):
    """Search for concepts using semantic similarity."""
    pinecone = request.app.state.pinecone
    
    try:
        # Generate embedding for query
        embedding_gen = EmbeddingGenerator()
        query_embedding = await embedding_gen.generate_embedding(query.query)
        
        # Search in Pinecone
        vector_store = VectorStore(pinecone)
        results = await vector_store.search_similar(
            query_embedding=query_embedding,
            limit=query.limit,
            filters=query.filters
        )
        
        return results
        
    except Exception as e:
        logger.error("Search failed", query=query.query, error=str(e))
        raise HTTPException(status_code=500, detail="Search failed")
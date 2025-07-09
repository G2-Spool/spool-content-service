"""Pinecone vector storage operations."""

from typing import List, Dict, Any, Optional
import asyncio
from datetime import datetime
import structlog

from app.models.content import Book, Concept, SearchResult
from app.core.config import settings

logger = structlog.get_logger()


class VectorStore:
    """Manage vector storage in Pinecone."""
    
    def __init__(self, index):
        self.index = index
        self.dimension = settings.PINECONE_DIMENSION
        self.batch_size = 100
    
    async def store_book_vectors(self, book: Book) -> int:
        """Store all concept vectors from a book."""
        vectors = []
        stored_count = 0
        
        # Collect all concepts with embeddings
        for chapter in book.chapters:
            for section in chapter.sections:
                for concept in section.concepts:
                    if concept.embedding:
                        vector_data = self._create_vector_data(
                            concept, book, chapter, section
                        )
                        vectors.append(vector_data)
        
        # Upsert in batches
        for i in range(0, len(vectors), self.batch_size):
            batch = vectors[i:i + self.batch_size]
            
            try:
                # Pinecone upsert is synchronous, so run in executor
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    self.index.upsert,
                    batch
                )
                
                stored_count += len(batch)
                logger.info(
                    "Stored vector batch",
                    batch_size=len(batch),
                    total_stored=stored_count
                )
                
            except Exception as e:
                logger.error(
                    "Failed to store vector batch",
                    batch_index=i,
                    error=str(e)
                )
        
        logger.info(
            "Book vectors stored",
            book_id=book.book_id,
            title=book.title,
            vectors_stored=stored_count
        )
        
        return stored_count
    
    def _create_vector_data(
        self, 
        concept: Concept, 
        book: Book, 
        chapter: "Chapter", 
        section: "Section"
    ) -> Dict[str, Any]:
        """Create vector data for Pinecone."""
        return {
            "id": concept.concept_id,
            "values": concept.embedding,
            "metadata": {
                "concept_name": concept.name[:100],
                "concept_type": concept.type.value,
                "content": concept.content[:500],  # First 500 chars
                "book_id": book.book_id,
                "book_title": book.title,
                "subject": book.subject,
                "chapter_id": chapter.chapter_id,
                "chapter_number": chapter.number,
                "chapter_title": chapter.title,
                "section_id": section.section_id,
                "section_title": section.title,
                "indexed_at": datetime.utcnow().isoformat()
            }
        }
    
    async def search_similar(
        self,
        query_embedding: List[float],
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[SearchResult]:
        """Search for similar concepts."""
        try:
            # Build filter dict for Pinecone
            pinecone_filter = {}
            if filters:
                if "book_id" in filters:
                    pinecone_filter["book_id"] = filters["book_id"]
                if "subject" in filters:
                    pinecone_filter["subject"] = filters["subject"]
                if "concept_type" in filters:
                    pinecone_filter["concept_type"] = filters["concept_type"]
            
            # Perform search (synchronous, so use executor)
            results = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.index.query(
                    vector=query_embedding,
                    top_k=limit,
                    include_metadata=True,
                    filter=pinecone_filter if pinecone_filter else None
                )
            )
            
            # Convert to SearchResult objects
            search_results = []
            for match in results.matches:
                metadata = match.metadata
                result = SearchResult(
                    concept_id=match.id,
                    name=metadata.get("concept_name", ""),
                    content=metadata.get("content", ""),
                    type=metadata.get("concept_type", "explanation"),
                    score=match.score,
                    book_title=metadata.get("book_title", ""),
                    chapter_title=metadata.get("chapter_title", ""),
                    section_title=metadata.get("section_title", ""),
                    metadata=metadata
                )
                search_results.append(result)
            
            return search_results
            
        except Exception as e:
            logger.error("Vector search failed", error=str(e))
            raise
    
    async def get_concept_by_id(self, concept_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a specific concept by ID."""
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.index.fetch([concept_id])
            )
            
            if concept_id in result.vectors:
                return result.vectors[concept_id]
            return None
            
        except Exception as e:
            logger.error("Failed to fetch concept", concept_id=concept_id, error=str(e))
            return None
    
    async def delete_book_vectors(self, book_id: str) -> bool:
        """Delete all vectors for a book."""
        try:
            # Delete by metadata filter
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.index.delete(
                    filter={"book_id": book_id}
                )
            )
            
            logger.info("Book vectors deleted", book_id=book_id)
            return True
            
        except Exception as e:
            logger.error("Failed to delete book vectors", book_id=book_id, error=str(e))
            return False
    
    async def update_concept_metadata(
        self,
        concept_id: str,
        metadata_updates: Dict[str, Any]
    ) -> bool:
        """Update metadata for a concept."""
        try:
            # Fetch current vector
            current = await self.get_concept_by_id(concept_id)
            if not current:
                return False
            
            # Update metadata
            updated_metadata = current.metadata.copy()
            updated_metadata.update(metadata_updates)
            updated_metadata["updated_at"] = datetime.utcnow().isoformat()
            
            # Upsert with updated metadata
            await asyncio.get_event_loop().run_in_executor(
                None,
                self.index.upsert,
                [{
                    "id": concept_id,
                    "values": current.values,
                    "metadata": updated_metadata
                }]
            )
            
            return True
            
        except Exception as e:
            logger.error(
                "Failed to update concept metadata",
                concept_id=concept_id,
                error=str(e)
            )
            return False
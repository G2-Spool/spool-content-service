"""Generate embeddings for content using OpenAI."""

from typing import List, Dict, Any, Optional
import asyncio
from tenacity import retry, stop_after_attempt, wait_exponential
import openai
import tiktoken
import structlog

from app.core.config import settings
from app.models.content import Concept, Book

logger = structlog.get_logger()


class EmbeddingGenerator:
    """Generate embeddings for educational content."""
    
    def __init__(self):
        self.client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = settings.EMBEDDING_MODEL
        self.dimension = settings.EMBEDDING_DIMENSION
        self.batch_size = settings.EMBEDDING_BATCH_SIZE
        self.encoding = tiktoken.encoding_for_model("text-embedding-3-small")
        self.max_tokens = 8191  # Model limit
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    async def generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for a single text."""
        try:
            # Truncate if too long
            text = self._truncate_text(text)
            
            response = await self.client.embeddings.create(
                model=self.model,
                input=text,
                dimensions=self.dimension
            )
            
            return response.data[0].embedding
            
        except Exception as e:
            logger.error("Embedding generation failed", error=str(e))
            raise
    
    async def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts in batches."""
        embeddings = []
        
        # Process in batches
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i:i + self.batch_size]
            
            try:
                # Truncate texts if needed
                batch = [self._truncate_text(text) for text in batch]
                
                response = await self.client.embeddings.create(
                    model=self.model,
                    input=batch,
                    dimensions=self.dimension
                )
                
                batch_embeddings = [item.embedding for item in response.data]
                embeddings.extend(batch_embeddings)
                
                logger.info(
                    "Generated embeddings batch",
                    batch_size=len(batch),
                    total_processed=len(embeddings)
                )
                
                # Rate limiting
                await asyncio.sleep(0.5)
                
            except Exception as e:
                logger.error(
                    "Batch embedding generation failed",
                    batch_index=i,
                    error=str(e)
                )
                # Generate individually as fallback
                for text in batch:
                    try:
                        embedding = await self.generate_embedding(text)
                        embeddings.append(embedding)
                    except:
                        # Use zero vector as last resort
                        embeddings.append([0.0] * self.dimension)
        
        return embeddings
    
    async def process_book(self, book: Book) -> Book:
        """Generate embeddings for all concepts in a book."""
        total_concepts = 0
        processed_concepts = 0
        
        # Collect all concepts
        all_concepts = []
        for chapter in book.chapters:
            for section in chapter.sections:
                for concept in section.concepts:
                    all_concepts.append((chapter, section, concept))
                    total_concepts += 1
        
        # Prepare texts for embedding
        texts = []
        for chapter, section, concept in all_concepts:
            # Create rich text representation
            text = self._create_concept_text(concept, chapter.title, section.title)
            texts.append(text)
        
        # Generate embeddings
        logger.info(
            "Generating embeddings for book",
            title=book.title,
            total_concepts=total_concepts
        )
        
        embeddings = await self.generate_embeddings_batch(texts)
        
        # Assign embeddings back to concepts
        for i, (chapter, section, concept) in enumerate(all_concepts):
            if i < len(embeddings):
                concept.embedding = embeddings[i]
                processed_concepts += 1
        
        logger.info(
            "Embeddings generation completed",
            title=book.title,
            processed=processed_concepts,
            total=total_concepts
        )
        
        return book
    
    def _truncate_text(self, text: str) -> str:
        """Truncate text to fit within token limits."""
        tokens = self.encoding.encode(text)
        
        if len(tokens) <= self.max_tokens:
            return text
        
        # Truncate and decode
        truncated_tokens = tokens[:self.max_tokens]
        return self.encoding.decode(truncated_tokens)
    
    def _create_concept_text(self, concept: Concept, chapter_title: str, section_title: str) -> str:
        """Create enriched text representation of concept for embedding."""
        # Include context for better semantic search
        parts = [
            f"Chapter: {chapter_title}",
            f"Section: {section_title}",
            f"Type: {concept.type.value}",
            f"Content: {concept.content}"
        ]
        
        # Add metadata if available
        if concept.metadata:
            for key, value in concept.metadata.items():
                parts.append(f"{key}: {value}")
        
        return "\n".join(parts)
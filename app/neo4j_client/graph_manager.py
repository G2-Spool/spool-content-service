"""Neo4j graph operations for knowledge management."""

from typing import List, Dict, Any, Optional, Tuple
from neo4j import AsyncGraphDatabase
import structlog

from app.models.content import Book, Chapter, Section, Concept, ConceptGraph, GraphNode, LearningPath
from app.core.config import settings

logger = structlog.get_logger()


class GraphManager:
    """Manage knowledge graph in Neo4j."""
    
    def __init__(self, driver: AsyncGraphDatabase.driver):
        self.driver = driver
        self.database = settings.NEO4J_DATABASE
    
    async def create_book_graph(self, book: Book) -> None:
        """Create graph structure for a book."""
        async with self.driver.session(database=self.database) as session:
            try:
                # Create book node
                await session.execute_write(self._create_book_node, book)
                
                # Create hierarchical structure
                for chapter in book.chapters:
                    await session.execute_write(self._create_chapter_structure, book.book_id, chapter)
                
                # Create concept relationships
                await self._create_concept_relationships(session, book)
                
                # Create indexes
                await self._ensure_indexes(session)
                
                logger.info(
                    "Book graph created",
                    book_id=book.book_id,
                    title=book.title
                )
                
            except Exception as e:
                logger.error("Failed to create book graph", error=str(e))
                raise
    
    async def _create_book_node(self, tx, book: Book):
        """Create book node."""
        query = """
        MERGE (b:Book {id: $book_id})
        SET b.title = $title,
            b.subject = $subject,
            b.grade_level = $grade_level,
            b.processed_at = datetime($processed_at)
        """
        tx.run(
            query,
            book_id=book.book_id,
            title=book.title,
            subject=book.subject,
            grade_level=book.grade_level,
            processed_at=book.processed_at.isoformat() if book.processed_at else None
        )
    
    async def _create_chapter_structure(self, tx, book_id: str, chapter: Chapter):
        """Create chapter and its sections."""
        # Create chapter
        chapter_query = """
        MATCH (b:Book {id: $book_id})
        MERGE (c:Chapter {id: $chapter_id})
        SET c.number = $number,
            c.title = $title
        MERGE (b)-[:HAS_CHAPTER]->(c)
        """
        tx.run(
            chapter_query,
            book_id=book_id,
            chapter_id=chapter.chapter_id,
            number=chapter.number,
            title=chapter.title
        )
        
        # Create sections and concepts
        for section in chapter.sections:
            section_query = """
            MATCH (c:Chapter {id: $chapter_id})
            MERGE (s:Section {id: $section_id})
            SET s.title = $title,
                s.number = $number
            MERGE (c)-[:HAS_SECTION]->(s)
            """
            tx.run(
                section_query,
                chapter_id=chapter.chapter_id,
                section_id=section.section_id,
                title=section.title,
                number=section.number
            )
            
            # Create concepts
            for concept in section.concepts:
                concept_query = """
                MATCH (s:Section {id: $section_id})
                MERGE (co:Concept {id: $concept_id})
                SET co.name = $name,
                    co.type = $type,
                    co.content = $content
                MERGE (s)-[:HAS_CONCEPT]->(co)
                """
                tx.run(
                    concept_query,
                    section_id=section.section_id,
                    concept_id=concept.concept_id,
                    name=concept.name,
                    type=concept.type.value,
                    content=concept.content[:1000]  # Limit content size
                )
    
    async def _create_concept_relationships(self, session, book: Book):
        """Create relationships between concepts."""
        # This is a simplified version - in production, you'd use NLP to identify relationships
        concepts = []
        for chapter in book.chapters:
            for section in chapter.sections:
                concepts.extend(section.concepts)
        
        # Create prerequisite relationships based on order
        for i in range(len(concepts) - 1):
            await session.execute_write(
                self._create_prerequisite_relation,
                concepts[i].concept_id,
                concepts[i + 1].concept_id
            )
    
    async def _create_prerequisite_relation(self, tx, from_id: str, to_id: str):
        """Create prerequisite relationship."""
        query = """
        MATCH (c1:Concept {id: $from_id})
        MATCH (c2:Concept {id: $to_id})
        MERGE (c1)-[:PREREQUISITE]->(c2)
        """
        tx.run(query, from_id=from_id, to_id=to_id)
    
    async def _ensure_indexes(self, session):
        """Ensure necessary indexes exist."""
        indexes = [
            "CREATE INDEX IF NOT EXISTS FOR (b:Book) ON (b.id)",
            "CREATE INDEX IF NOT EXISTS FOR (c:Chapter) ON (c.id)",
            "CREATE INDEX IF NOT EXISTS FOR (s:Section) ON (s.id)",
            "CREATE INDEX IF NOT EXISTS FOR (co:Concept) ON (co.id)",
            "CREATE INDEX IF NOT EXISTS FOR (co:Concept) ON (co.name)"
        ]
        
        for index_query in indexes:
            await session.run(index_query)
    
    async def get_concept_graph(self, concept_id: str) -> Optional[ConceptGraph]:
        """Get concept with all its relationships."""
        async with self.driver.session(database=self.database) as session:
            try:
                result = await session.execute_read(
                    self._get_concept_with_relationships,
                    concept_id
                )
                
                if result:
                    return ConceptGraph(**result)
                return None
                
            except Exception as e:
                logger.error("Failed to get concept graph", error=str(e))
                raise
    
    async def _get_concept_with_relationships(self, tx, concept_id: str):
        """Query concept with relationships."""
        # Get concept
        concept_query = """
        MATCH (c:Concept {id: $concept_id})
        RETURN c
        """
        concept_result = tx.run(concept_query, concept_id=concept_id).single()
        
        if not concept_result:
            return None
        
        concept_node = GraphNode(
            id=concept_result["c"]["id"],
            label="Concept",
            properties=dict(concept_result["c"])
        )
        
        # Get prerequisites
        prereq_query = """
        MATCH (c:Concept {id: $concept_id})<-[:PREREQUISITE]-(p:Concept)
        RETURN p
        """
        prereq_results = tx.run(prereq_query, concept_id=concept_id)
        prerequisites = [
            GraphNode(
                id=record["p"]["id"],
                label="Concept",
                properties=dict(record["p"])
            )
            for record in prereq_results
        ]
        
        # Get related concepts
        related_query = """
        MATCH (c:Concept {id: $concept_id})-[:RELATED_TO]-(r:Concept)
        RETURN r
        """
        related_results = tx.run(related_query, concept_id=concept_id)
        related = [
            GraphNode(
                id=record["r"]["id"],
                label="Concept",
                properties=dict(record["r"])
            )
            for record in related_results
        ]
        
        # Get next concepts
        next_query = """
        MATCH (c:Concept {id: $concept_id})-[:PREREQUISITE]->(n:Concept)
        RETURN n
        """
        next_results = tx.run(next_query, concept_id=concept_id)
        next_concepts = [
            GraphNode(
                id=record["n"]["id"],
                label="Concept",
                properties=dict(record["n"])
            )
            for record in next_results
        ]
        
        return {
            "concept": concept_node,
            "prerequisites": prerequisites,
            "related_concepts": related,
            "next_concepts": next_concepts
        }
    
    async def find_learning_path(self, from_concept_id: str, to_concept_id: str) -> Optional[LearningPath]:
        """Find shortest learning path between two concepts."""
        async with self.driver.session(database=self.database) as session:
            try:
                result = await session.execute_read(
                    self._find_shortest_path,
                    from_concept_id,
                    to_concept_id
                )
                
                if result:
                    return LearningPath(**result)
                return None
                
            except Exception as e:
                logger.error("Failed to find learning path", error=str(e))
                raise
    
    async def _find_shortest_path(self, tx, from_id: str, to_id: str):
        """Find shortest path using prerequisite relationships."""
        query = """
        MATCH path = shortestPath(
            (from:Concept {id: $from_id})-[:PREREQUISITE*]->(to:Concept {id: $to_id})
        )
        RETURN from, to, nodes(path) as path_nodes, length(path) as path_length
        """
        
        result = tx.run(query, from_id=from_id, to_id=to_id).single()
        
        if result:
            path_nodes = [
                GraphNode(
                    id=node["id"],
                    label="Concept",
                    properties=dict(node)
                )
                for node in result["path_nodes"]
            ]
            
            return {
                "from_concept": from_id,
                "to_concept": to_id,
                "path": path_nodes,
                "total_concepts": len(path_nodes),
                "estimated_time": len(path_nodes) * 15  # 15 minutes per concept
            }
        
        return None
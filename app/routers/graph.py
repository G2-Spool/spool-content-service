"""Knowledge graph routes."""

from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Query
import structlog

from app.models.content import ConceptGraph, LearningPath
from app.neo4j_client.graph_manager import GraphManager

router = APIRouter()
logger = structlog.get_logger()


@router.get("/concept/{concept_id}", response_model=ConceptGraph)
async def get_concept_graph(concept_id: str, request: Request):
    """Get concept with all its relationships."""
    neo4j = request.app.state.neo4j
    
    try:
        graph_manager = GraphManager(neo4j)
        concept_graph = await graph_manager.get_concept_graph(concept_id)
        
        if not concept_graph:
            raise HTTPException(status_code=404, detail="Concept not found")
        
        return concept_graph
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get concept graph", concept_id=concept_id, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to retrieve concept graph")


@router.get("/prerequisites/{concept_id}")
async def get_prerequisites(concept_id: str, request: Request):
    """Get all prerequisites for a concept."""
    neo4j = request.app.state.neo4j
    
    try:
        async with neo4j.session() as session:
            result = await session.run("""
                MATCH (c:Concept {id: $concept_id})<-[:PREREQUISITE*]-(p:Concept)
                RETURN DISTINCT p
                ORDER BY p.name
            """, concept_id=concept_id)
            
            prerequisites = []
            async for record in result:
                prereq = dict(record["p"])
                prerequisites.append({
                    "concept_id": prereq["id"],
                    "name": prereq["name"],
                    "type": prereq.get("type", "explanation")
                })
            
            return {
                "concept_id": concept_id,
                "prerequisites": prerequisites,
                "total": len(prerequisites)
            }
            
    except Exception as e:
        logger.error("Failed to get prerequisites", concept_id=concept_id, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to retrieve prerequisites")


@router.get("/related/{concept_id}")
async def get_related_concepts(
    concept_id: str,
    request: Request,
    limit: int = Query(default=10, ge=1, le=50)
):
    """Get related concepts."""
    neo4j = request.app.state.neo4j
    
    try:
        async with neo4j.session() as session:
            # Get related concepts through various relationships
            result = await session.run("""
                MATCH (c:Concept {id: $concept_id})
                MATCH (c)-[r:RELATED_TO|PREREQUISITE|HAS_CONCEPT]-(related:Concept)
                WHERE related.id <> $concept_id
                RETURN DISTINCT related, type(r) as relationship
                LIMIT $limit
            """, concept_id=concept_id, limit=limit)
            
            related = []
            async for record in result:
                concept_data = dict(record["related"])
                related.append({
                    "concept_id": concept_data["id"],
                    "name": concept_data["name"],
                    "type": concept_data.get("type", "explanation"),
                    "relationship": record["relationship"]
                })
            
            return {
                "concept_id": concept_id,
                "related_concepts": related,
                "total": len(related)
            }
            
    except Exception as e:
        logger.error("Failed to get related concepts", concept_id=concept_id, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to retrieve related concepts")


@router.get("/path", response_model=Optional[LearningPath])
async def find_learning_path(
    request: Request,
    from_concept: str = Query(..., description="Starting concept ID"),
    to_concept: str = Query(..., description="Target concept ID")
):
    """Find learning path between two concepts."""
    neo4j = request.app.state.neo4j
    
    try:
        graph_manager = GraphManager(neo4j)
        path = await graph_manager.find_learning_path(from_concept, to_concept)
        
        if not path:
            return JSONResponse(
                status_code=404,
                content={
                    "message": "No learning path found between concepts",
                    "from_concept": from_concept,
                    "to_concept": to_concept
                }
            )
        
        return path
        
    except Exception as e:
        logger.error(
            "Failed to find learning path",
            from_concept=from_concept,
            to_concept=to_concept,
            error=str(e)
        )
        raise HTTPException(status_code=500, detail="Failed to find learning path")


@router.get("/statistics")
async def get_graph_statistics(request: Request):
    """Get knowledge graph statistics."""
    neo4j = request.app.state.neo4j
    
    try:
        async with neo4j.session() as session:
            # Get counts
            result = await session.run("""
                MATCH (b:Book) WITH count(b) as books
                MATCH (c:Chapter) WITH books, count(c) as chapters
                MATCH (s:Section) WITH books, chapters, count(s) as sections
                MATCH (co:Concept) WITH books, chapters, sections, count(co) as concepts
                MATCH ()-[r:PREREQUISITE]->() WITH books, chapters, sections, concepts, count(r) as prerequisites
                MATCH ()-[r:RELATED_TO]->() WITH books, chapters, sections, concepts, prerequisites, count(r) as related
                RETURN books, chapters, sections, concepts, prerequisites, related
            """)
            
            stats = await result.single()
            
            return {
                "books": stats["books"] or 0,
                "chapters": stats["chapters"] or 0,
                "sections": stats["sections"] or 0,
                "concepts": stats["concepts"] or 0,
                "relationships": {
                    "prerequisites": stats["prerequisites"] or 0,
                    "related": stats["related"] or 0
                }
            }
            
    except Exception as e:
        logger.error("Failed to get graph statistics", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to retrieve statistics")


from fastapi.responses import JSONResponse
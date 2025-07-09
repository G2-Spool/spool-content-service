"""Shared dependencies for Content Service."""

from typing import Optional
import pinecone
from neo4j import AsyncGraphDatabase
import structlog
import boto3
from aiocache import Cache
import redis

from app.core.config import settings

logger = structlog.get_logger()

# Global instances
_neo4j_driver: Optional[AsyncGraphDatabase.driver] = None
_pinecone_index = None
_s3_client = None
_redis_cache = None


async def get_neo4j_client():
    """Get Neo4j async driver instance."""
    global _neo4j_driver
    
    if _neo4j_driver is None:
        try:
            _neo4j_driver = AsyncGraphDatabase.driver(
                settings.NEO4J_URI,
                auth=(settings.NEO4J_USERNAME, settings.NEO4J_PASSWORD),
                max_connection_pool_size=50
            )
            await _neo4j_driver.verify_connectivity()
            logger.info("Neo4j connection established")
        except Exception as e:
            logger.error("Failed to connect to Neo4j", error=str(e))
            raise
    
    return _neo4j_driver


async def get_pinecone_client():
    """Get Pinecone index instance."""
    global _pinecone_index
    
    if _pinecone_index is None:
        try:
            # Initialize Pinecone
            pc = pinecone.Pinecone(
                api_key=settings.PINECONE_API_KEY,
                environment=settings.PINECONE_ENVIRONMENT
            )
            
            # Get or create index
            index_name = settings.PINECONE_INDEX_NAME
            
            if index_name not in pc.list_indexes().names():
                # Create index if it doesn't exist
                pc.create_index(
                    name=index_name,
                    dimension=settings.PINECONE_DIMENSION,
                    metric=settings.PINECONE_METRIC,
                    spec=pinecone.ServerlessSpec(
                        cloud="aws",
                        region=settings.PINECONE_ENVIRONMENT
                    )
                )
                logger.info(f"Created Pinecone index: {index_name}")
            
            _pinecone_index = pc.Index(index_name)
            logger.info("Pinecone connection established")
        except Exception as e:
            logger.error("Failed to connect to Pinecone", error=str(e))
            raise
    
    return _pinecone_index


def get_s3_client():
    """Get S3 client instance."""
    global _s3_client
    
    if _s3_client is None:
        session = boto3.Session(
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION
        )
        _s3_client = session.client("s3")
        logger.info("S3 client initialized")
    
    return _s3_client


async def get_redis_cache():
    """Get Redis cache instance."""
    global _redis_cache
    
    if _redis_cache is None:
        try:
            _redis_cache = Cache.from_url(settings.REDIS_URL)
            await _redis_cache.exists("test")  # Test connection
            logger.info("Redis cache connection established")
        except Exception as e:
            logger.warning(f"Redis cache not available: {e}")
            # Fallback to in-memory cache
            _redis_cache = Cache(Cache.MEMORY)
    
    return _redis_cache
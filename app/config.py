import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Service Configuration
    service_name: str = os.getenv("SERVICE_NAME", "content-service")
    environment: str = os.getenv("ENVIRONMENT", "development")
    
    # RDS PostgreSQL
    rds_host: str = os.getenv("RDS_HOST", "localhost")
    rds_port: int = int(os.getenv("RDS_PORT", "5432"))
    rds_database: str = os.getenv("RDS_DATABASE", "postgres")
    rds_username: str = os.getenv("RDS_USERNAME", "postgres")
    rds_password: str = os.getenv("RDS_PASSWORD", "spoolrds")
    
    # Neo4j
    neo4j_uri: str = os.getenv("NEO4J_URI", "neo4j+s://9d61bfe9.databases.neo4j.io")
    neo4j_username: str = os.getenv("NEO4J_USERNAME", "neo4j")
    neo4j_password: str = os.getenv("NEO4J_PASSWORD", "xx_MYGxTYU7TYeUQEEiqphxmRgLe9BetAAaJ3y-E5JU")
    neo4j_database: str = os.getenv("NEO4J_DATABASE", "neo4j")
    
    # Pinecone
    pinecone_api_key: str = os.getenv("PINECONE_API_KEY", "")
    pinecone_environment: str = os.getenv("PINECONE_ENVIRONMENT", "us-east-1-aws")
    pinecone_index_name: str = os.getenv("PINECONE_INDEX_NAME", "")
    
    # OpenAI (from your Pinecone parameter)
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    
    # Computed Properties
    @property
    def postgres_url(self) -> str:
        return f"postgresql+asyncpg://{self.rds_username}:{self.rds_password}@{self.rds_host}:{self.rds_port}/{self.rds_database}"
    
    @property
    def postgres_sync_url(self) -> str:
        return f"postgresql://{self.rds_username}:{self.rds_password}@{self.rds_host}:{self.rds_port}/{self.rds_database}"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
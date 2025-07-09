# Spool Content Service

Content processing, vector generation, and knowledge graph management service for the Spool platform.

**Status:** ✅ Deployed to CodeBuild

## Overview

The Content Service is responsible for:

- **PDF Processing**: Extract and structure educational content from textbooks
- **Vector Embeddings**: Generate embeddings for semantic search and similarity
- **Knowledge Graph**: Build and manage concept relationships in Neo4j
- **Content Generation**: Create personalized "hooks" based on student interests
- **Vector Storage**: Manage content vectors in Pinecone for fast retrieval

## Architecture

```
PDF Upload → Text Extraction → Chunking → Embedding → Storage
                    ↓                         ↓
              Structure Analysis      Knowledge Graph
                    ↓                         ↓
              Content Metadata          Relationships
```

## Quick Start

### Prerequisites
- Python 3.11+
- Docker
- Neo4j instance
- Pinecone account
- OpenAI API key

### Local Development

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set environment variables:
```bash
cp .env.example .env
# Edit .env with your values
```

3. Run locally:
```bash
uvicorn app.main:app --reload --port 8002
```

### Docker

```bash
# Build
docker build -t spool-content-service .

# Run
docker run -p 8002:8002 spool-content-service
```

## API Endpoints

### Health Check
```
GET /health
```

### PDF Processing
```
POST /api/content/upload
  - Upload PDF textbook
  - Returns: processing job ID

GET /api/content/status/{job_id}
  - Check processing status

GET /api/content/books
  - List all processed books
```

### Content Retrieval
```
GET /api/content/concepts/{concept_id}
  - Get concept details

POST /api/content/search
  - Semantic search for concepts
  - Body: { "query": "string", "limit": 10 }

GET /api/content/graph/concept/{concept_id}
  - Get concept with relationships
```

### Hook Generation
```
POST /api/content/hooks/generate
  - Generate personalized hooks
  - Body: {
      "concept_id": "string",
      "student_interests": ["array"],
      "categories": ["personal", "career", "social", "philanthropic"]
    }
```

### Knowledge Graph
```
GET /api/content/graph/path
  - Find learning path between concepts
  - Query params: from_concept, to_concept

GET /api/content/graph/prerequisites/{concept_id}
  - Get all prerequisites for a concept

GET /api/content/graph/related/{concept_id}
  - Get related concepts
```

## Configuration

### Environment Variables
- `OPENAI_API_KEY`: OpenAI API key for embeddings
- `PINECONE_API_KEY`: Pinecone API key
- `PINECONE_ENVIRONMENT`: Pinecone environment
- `PINECONE_INDEX_NAME`: Name of Pinecone index
- `NEO4J_URI`: Neo4j connection URI
- `NEO4J_USERNAME`: Neo4j username
- `NEO4J_PASSWORD`: Neo4j password
- `AWS_REGION`: AWS region for S3 storage
- `S3_BUCKET`: S3 bucket for PDF storage
- `EMBEDDING_MODEL`: OpenAI embedding model (default: text-embedding-3-small)
- `EMBEDDING_DIMENSION`: Embedding dimension (default: 1536)

## Data Models

### Content Structure
```python
{
  "book_id": "uuid",
  "title": "string",
  "chapters": [{
    "chapter_id": "uuid",
    "number": "int",
    "title": "string",
    "sections": [{
      "section_id": "uuid",
      "title": "string",
      "concepts": [{
        "concept_id": "uuid",
        "name": "string",
        "content": "string",
        "type": "explanation|example|formula|exercise|definition",
        "embedding": [1536 dimensions],
        "metadata": {}
      }]
    }]
  }]
}
```

### Knowledge Graph Schema
```cypher
// Nodes
(Book {id, title, subject})
(Chapter {id, number, title, book_id})
(Section {id, title, chapter_id})
(Concept {id, name, type, content})

// Relationships
(Book)-[:HAS_CHAPTER]->(Chapter)
(Chapter)-[:HAS_SECTION]->(Section)
(Section)-[:HAS_CONCEPT]->(Concept)
(Concept)-[:PREREQUISITE]->(Concept)
(Concept)-[:RELATED_TO]->(Concept)
```

### Vector Storage Schema
```python
{
  "id": "concept_id",
  "values": [1536 embedding values],
  "metadata": {
    "book_id": "uuid",
    "chapter_number": 1,
    "section_title": "string",
    "concept_name": "string",
    "concept_type": "string",
    "text": "first 500 chars..."
  }
}
```

## Processing Pipeline

### 1. PDF Upload & Storage
- Upload to S3 with metadata
- Create processing job
- Return job ID for tracking

### 2. Text Extraction
- Extract text using PyPDF2/pdfplumber
- Preserve structure (chapters, sections)
- Clean and normalize text

### 3. Content Chunking
- Identify chapter/section boundaries
- Extract individual concepts
- Classify content types

### 4. Embedding Generation
- Generate embeddings for each chunk
- Batch processing for efficiency
- Store with metadata

### 5. Knowledge Graph Construction
- Create nodes for structure
- Identify prerequisites from content
- Build relationship network

### 6. Vector Storage
- Upsert to Pinecone index
- Include searchable metadata
- Enable filtered queries

## Monitoring

### Metrics
- PDF processing time
- Embedding generation rate
- Graph query performance
- Storage utilization

### Logging
Structured JSON logging with:
- Processing job tracking
- Error details
- Performance metrics

## Development

### Testing
```bash
# Unit tests
pytest tests/unit

# Integration tests
pytest tests/integration

# All tests
pytest
```

### Code Quality
```bash
# Linting
ruff check app

# Type checking
mypy app

# Format code
black app
```

## Deployment

### AWS ECS
```bash
# Build and push to ECR
./scripts/build-and-push.sh

# Deploy to ECS
./scripts/deploy-ecs.sh
```

### Required AWS Resources
- S3 bucket for PDF storage
- ECS task with 2GB memory minimum
- Access to Neo4j and Pinecone

## Troubleshooting

### Common Issues

1. **PDF Processing Fails**
   - Check PDF is not encrypted
   - Verify file size limits
   - Check S3 permissions

2. **Embedding Generation Slow**
   - Batch requests to OpenAI
   - Check rate limits
   - Use caching for repeated content

3. **Neo4j Connection Issues**
   - Verify network connectivity
   - Check credentials
   - Ensure indexes are created

## License

Copyright © 2024 Spool. All rights reserved.
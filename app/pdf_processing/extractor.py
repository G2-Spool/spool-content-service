"""PDF text extraction and structuring."""

import re
from typing import List, Dict, Any, Optional, Tuple
import PyPDF2
import pdfplumber
from io import BytesIO
import structlog

from app.models.content import Book, Chapter, Section, Concept, ContentType

logger = structlog.get_logger()


class PDFExtractor:
    """Extract and structure content from PDF files."""
    
    def __init__(self):
        self.chapter_patterns = [
            r"^Chapter\s+(\d+)[:\s]+(.+)$",
            r"^CHAPTER\s+(\d+)[:\s]+(.+)$",
            r"^Unit\s+(\d+)[:\s]+(.+)$",
            r"^Module\s+(\d+)[:\s]+(.+)$",
            r"^(\d+)\.\s+(.+)$"  # Simple numbered chapters
        ]
        
        self.section_patterns = [
            r"^(\d+\.\d+)\s+(.+)$",
            r"^Section\s+(\d+\.\d+)[:\s]+(.+)$",
            r"^[A-Z]\.\s+(.+)$"
        ]
    
    async def extract_from_bytes(self, pdf_bytes: bytes, title: str) -> Book:
        """Extract content from PDF bytes."""
        try:
            # Try pdfplumber first for better text extraction
            content = await self._extract_with_pdfplumber(pdf_bytes)
            if not content:
                # Fallback to PyPDF2
                content = await self._extract_with_pypdf2(pdf_bytes)
            
            # Structure the content
            book = await self._structure_content(content, title)
            
            logger.info(
                "PDF extraction completed",
                title=title,
                chapters=len(book.chapters),
                total_concepts=sum(
                    len(section.concepts) 
                    for chapter in book.chapters 
                    for section in chapter.sections
                )
            )
            
            return book
            
        except Exception as e:
            logger.error("PDF extraction failed", error=str(e), title=title)
            raise
    
    async def _extract_with_pdfplumber(self, pdf_bytes: bytes) -> List[Dict[str, Any]]:
        """Extract text using pdfplumber."""
        pages = []
        
        try:
            with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
                for i, page in enumerate(pdf.pages):
                    text = page.extract_text()
                    if text:
                        pages.append({
                            "page_num": i + 1,
                            "text": text,
                            "tables": page.extract_tables()
                        })
            
            return pages
        except Exception as e:
            logger.warning(f"pdfplumber extraction failed: {e}")
            return []
    
    async def _extract_with_pypdf2(self, pdf_bytes: bytes) -> List[Dict[str, Any]]:
        """Extract text using PyPDF2 as fallback."""
        pages = []
        
        try:
            reader = PyPDF2.PdfReader(BytesIO(pdf_bytes))
            
            for i, page in enumerate(reader.pages):
                text = page.extract_text()
                if text:
                    pages.append({
                        "page_num": i + 1,
                        "text": text,
                        "tables": []
                    })
            
            return pages
        except Exception as e:
            logger.error(f"PyPDF2 extraction failed: {e}")
            raise
    
    async def _structure_content(self, pages: List[Dict[str, Any]], title: str) -> Book:
        """Structure extracted content into chapters and sections."""
        book = Book(title=title, subject=self._infer_subject(title))
        
        current_chapter = None
        current_section = None
        accumulated_text = []
        
        for page in pages:
            lines = page["text"].split('\n')
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # Check for chapter
                chapter_match = self._match_chapter(line)
                if chapter_match:
                    # Save accumulated text to previous section
                    if current_section and accumulated_text:
                        concepts = await self._extract_concepts(
                            '\n'.join(accumulated_text)
                        )
                        current_section.concepts.extend(concepts)
                        accumulated_text = []
                    
                    # Create new chapter
                    chapter_num, chapter_title = chapter_match
                    current_chapter = Chapter(
                        number=chapter_num,
                        title=chapter_title
                    )
                    book.chapters.append(current_chapter)
                    current_section = None
                    continue
                
                # Check for section
                section_match = self._match_section(line)
                if section_match and current_chapter:
                    # Save accumulated text to previous section
                    if current_section and accumulated_text:
                        concepts = await self._extract_concepts(
                            '\n'.join(accumulated_text)
                        )
                        current_section.concepts.extend(concepts)
                        accumulated_text = []
                    
                    # Create new section
                    section_num, section_title = section_match
                    current_section = Section(
                        number=section_num,
                        title=section_title
                    )
                    current_chapter.sections.append(current_section)
                    continue
                
                # Accumulate text
                accumulated_text.append(line)
        
        # Handle remaining text
        if current_section and accumulated_text:
            concepts = await self._extract_concepts('\n'.join(accumulated_text))
            current_section.concepts.extend(concepts)
        
        return book
    
    def _match_chapter(self, line: str) -> Optional[Tuple[int, str]]:
        """Match chapter patterns."""
        for pattern in self.chapter_patterns:
            match = re.match(pattern, line, re.IGNORECASE)
            if match:
                try:
                    return int(match.group(1)), match.group(2).strip()
                except:
                    pass
        return None
    
    def _match_section(self, line: str) -> Optional[Tuple[str, str]]:
        """Match section patterns."""
        for pattern in self.section_patterns:
            match = re.match(pattern, line, re.IGNORECASE)
            if match:
                if len(match.groups()) == 2:
                    return match.group(1), match.group(2).strip()
                else:
                    return "A", match.group(1).strip()
        return None
    
    async def _extract_concepts(self, text: str) -> List[Concept]:
        """Extract individual concepts from text."""
        concepts = []
        
        # Split into paragraphs
        paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
        
        for para in paragraphs:
            # Skip very short paragraphs
            if len(para) < 50:
                continue
            
            # Classify content type
            content_type = self._classify_content(para)
            
            # Extract concept name (first sentence or heading)
            sentences = para.split('. ')
            name = sentences[0][:100] if sentences else para[:100]
            
            concept = Concept(
                name=name,
                content=para,
                type=content_type
            )
            concepts.append(concept)
        
        return concepts
    
    def _classify_content(self, text: str) -> ContentType:
        """Classify the type of content."""
        text_lower = text.lower()
        
        if any(keyword in text_lower for keyword in ["example:", "for instance", "e.g.", "such as"]):
            return ContentType.EXAMPLE
        elif any(keyword in text_lower for keyword in ["=", "formula", "equation"]):
            return ContentType.FORMULA
        elif any(keyword in text_lower for keyword in ["exercise:", "problem:", "question:"]):
            return ContentType.EXERCISE
        elif any(keyword in text_lower for keyword in ["definition:", "is defined as", "means that"]):
            return ContentType.DEFINITION
        else:
            return ContentType.EXPLANATION
    
    def _infer_subject(self, title: str) -> str:
        """Infer subject from book title."""
        title_lower = title.lower()
        
        if any(word in title_lower for word in ["math", "algebra", "geometry", "calculus"]):
            return "Mathematics"
        elif any(word in title_lower for word in ["physics", "chemistry", "biology", "science"]):
            return "Science"
        elif any(word in title_lower for word in ["history", "geography", "social"]):
            return "Social Studies"
        elif any(word in title_lower for word in ["english", "literature", "language"]):
            return "English"
        else:
            return "General"
"""Generate personalized hooks for concepts based on student interests."""

from typing import List, Dict, Any, Optional
from datetime import datetime
import json
import structlog
from openai import AsyncOpenAI

from app.core.config import settings
from app.models.content import Concept

logger = structlog.get_logger()


class HookGenerator:
    """Generate personalized hooks and relevance content."""
    
    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = "gpt-4o"
    
    async def generate_hooks(
        self,
        concept: Concept,
        student_interests: List[str],
        categories: List[str]
    ) -> Dict[str, Any]:
        """Generate personalized hooks for a concept."""
        try:
            # Prepare the prompt
            prompt = self._create_hook_prompt(concept, student_interests, categories)
            
            # Generate hooks
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._get_system_prompt()},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                response_format={"type": "json_object"}
            )
            
            # Parse response
            hooks = json.loads(response.choices[0].message.content)
            
            # Add metadata
            hooks["concept_id"] = concept.concept_id
            hooks["generated_at"] = datetime.utcnow().isoformat()
            
            logger.info(
                "Generated hooks",
                concept_id=concept.concept_id,
                categories=categories
            )
            
            return hooks
            
        except Exception as e:
            logger.error(
                "Hook generation failed",
                concept_id=concept.concept_id,
                error=str(e)
            )
            raise
    
    def _get_system_prompt(self) -> str:
        """Get system prompt for hook generation."""
        return """You are an expert educational content creator specializing in making 
        academic concepts relevant and engaging for students. Your task is to create 
        personalized "hooks" that connect educational concepts to students' interests 
        and life goals.
        
        For each hook, you should:
        1. Make a clear connection between the concept and the student's interest
        2. Explain why this concept matters in their context
        3. Use age-appropriate language and examples
        4. Be inspiring and motivational
        5. Keep each hook concise (2-3 sentences)
        
        Return your response as a JSON object with the requested categories as keys."""
    
    def _create_hook_prompt(
        self,
        concept: Concept,
        student_interests: List[str],
        categories: List[str]
    ) -> str:
        """Create prompt for hook generation."""
        prompt = f"""Create personalized hooks for the following educational concept:
        
        Concept: {concept.name}
        Content: {concept.content[:500]}...
        Type: {concept.type.value}
        
        Student Interests: {', '.join(student_interests)}
        
        Generate hooks for these categories: {', '.join(categories)}
        
        For each category, create a hook that:
        - Connects the concept to relevant student interests
        - Explains why this concept matters in that context
        - Is engaging and age-appropriate
        
        Example format:
        {{
            "personal": "Since you love [interest], understanding [concept] will help you...",
            "career": "In your future career as [career interest], [concept] is essential because...",
            "social": "When working with others on [social interest], [concept] helps you...",
            "philanthropic": "To make a difference in [cause], knowing [concept] enables you..."
        }}
        """
        
        return prompt
    
    async def generate_examples(
        self,
        concept: Concept,
        student_interests: List[str],
        count: int = 3
    ) -> List[Dict[str, Any]]:
        """Generate personalized examples for a concept."""
        try:
            prompt = f"""Create {count} examples that explain this concept using the student's interests:
            
            Concept: {concept.name}
            Content: {concept.content[:500]}...
            Student Interests: {', '.join(student_interests)}
            
            Each example should:
            1. Use one or more of the student's interests as context
            2. Clearly demonstrate the concept
            3. Be engaging and relatable
            4. Progress from simple to more complex
            
            Return as a JSON array of objects with 'title', 'content', and 'difficulty' fields."""
            
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an educational content expert."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.8,
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            examples = result.get("examples", [])
            
            # Add metadata
            for example in examples:
                example["concept_id"] = concept.concept_id
                example["generated_at"] = datetime.utcnow().isoformat()
            
            return examples
            
        except Exception as e:
            logger.error(
                "Example generation failed",
                concept_id=concept.concept_id,
                error=str(e)
            )
            raise
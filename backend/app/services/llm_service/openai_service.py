# app/services/llm_service.py
import json
from typing import Any

import openai
from pydantic import BaseModel, Field


class AnalysisResult(BaseModel):
    is_valid: bool = Field(description="Whether the input content is relevant to the analysis requirements")
    confidence: float = Field(description="Judge the confidence level, between 0 and 1")
    reason: str | None = Field(description="If is_valid=false, explain the reason")
    analysis_type_matched: bool = Field(description="Whether analysis_type matches the content")
    
    # output for valid analysis
    result: dict[str, Any] | None = Field(default=None, description="分析结果")
    key_findings: list | None = Field(default=None)
    recommendations: list | None = Field(default=None)

class LLMService:
    def __init__(self):
        self.client = openai.AsyncOpenAI()
    
    async def analyze_with_self_check(
        self, 
        prompt: str,
        model: str = None
    ) -> dict[str, Any]:
        
        if model is None:
            from .config import LLMProvider, get_default_model
            model = get_default_model(LLMProvider.OPENAI)
        
        system_prompt = """
"""

        try:
            response = await self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,  # low temperature for stable output
                response_format={"type": "json_object"}
            )
            
            content = response.choices[0].message.content
            result = json.loads(content)
            
            # Check output
            if "is_valid" not in result:
                return {
                    "is_valid": False,
                    "confidence": 0.0,
                    "reason": "LLM returns a format exception, missing the is_valid field",
                    "raw_response": content
                }
            
            return result
            
        except json.JSONDecodeError:
            return {
                "is_valid": False,
                "confidence": 0.0,
                "reason": "LLM returns in a non-JSON format",
                "raw_response": content
            }
        except Exception as e:
            return {
                "is_valid": False,
                "confidence": 0.0,
                "reason": f"LLM call exception: {str(e)}"
            }
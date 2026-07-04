# app/services/llm_service/cohere_service.py
import cohere
import json
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
import os
from dotenv import load_dotenv


class AnalysisResult(BaseModel):
    is_valid: bool = Field(description="Whether the input content is relevant to the analysis requirements")
    confidence: float = Field(description="Judge the confidence level, between 0 and 1")
    reason: Optional[str] = Field(description="If is_valid=false, explain the reason")
    analysis_type_matched: bool = Field(description="Whether analysis_type matches the content")
    
    # output for valid analysis
    result: Optional[Dict[str, Any]] = Field(default=None, description="Analysis result")
    key_findings: Optional[list] = Field(default=None)
    recommendations: Optional[list] = Field(default=None)


class LLMService:
    def __init__(self):
        load_dotenv()
        api_key = os.getenv("COHERE_API_KEY")
        if not api_key:
            raise ValueError("COHERE_API_KEY environment variable not set")
        
        self.client = cohere.AsyncClientV2(api_key=api_key)
    
    async def analyze_with_self_check(
        self, 
        prompt: str,
        model: str = None
    ) -> Dict[str, Any]:
        """
        Analyze content using Cohere with self-validation.
        
        Args:
            prompt: The prompt/content to analyze
            analysis_type: Type of analysis being performed
            model: Cohere model to use (default: command-r-plus)
            
        Returns:
            Dictionary with analysis results including validation status
        """

        if model is None:
            from .config import get_default_model, LLMProvider
            model = get_default_model(LLMProvider.COHERE)
        
        system_prompt = f"""
You are an expert AI assistant performing analysis.
Analyze the provided content carefully and return a JSON response with the following structure:
{{
    "is_valid": boolean,
    "confidence": float (0-1),
    "reason": string (only if is_valid=false),
    "analysis_type_matched": boolean,
    "result": object (analysis results),
    "key_findings": list,
    "recommendations": list
}}

Always validate your own output to ensure it matches the required format.
"""

        try:
            response = await self.client.chat(
                model=model,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            content = response.message.content[0].text
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
    
    async def call_llm(self, prompt: str, model: str = "command-r-plus") -> str:
        """
        Make a general LLM call and return raw text response.
        
        Args:
            prompt: The prompt to send to the LLM
            model: Cohere model to use
            
        Returns:
            The LLM response as a string
        """
        try:
            response = await self.client.chat(
                model=model,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            return response.message.content[0].text
        except Exception as e:
            return f"Error: {str(e)}"
    
    async def call_llm_json(
        self, 
        prompt: str, 
        model: str = "command-r-plus"
    ) -> Optional[Dict[str, Any]]:
        """
        Make an LLM call expecting JSON response and parse it.
        
        Args:
            prompt: The prompt to send to the LLM (should instruct JSON output)
            model: Cohere model to use
            
        Returns:
            Parsed JSON response as a dictionary, or None if parsing fails
        """
        try:
            response = await self.client.chat(
                model=model,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            content = response.message.content[0].text
            data = json.loads(content)
            return data
        except json.JSONDecodeError as e:
            print(f"JSON parsing error: {e}")
            return None
        except Exception as e:
            print(f"Error calling LLM: {e}")
            return None

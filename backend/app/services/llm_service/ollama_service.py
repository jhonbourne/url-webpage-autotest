# app/services/llm_service/ollama_service.py
import json
from typing import Any

import httpx
from pydantic import BaseModel, Field


class AnalysisResult(BaseModel):
    is_valid: bool = Field(description="Whether the input content is relevant to the analysis requirements")
    confidence: float = Field(description="Judge the confidence level, between 0 and 1")
    reason: str | None = Field(description="If is_valid=false, explain the reason")
    analysis_type_matched: bool = Field(description="Whether analysis_type matches the content")
    
    # output for valid analysis
    result: dict[str, Any] | None = Field(default=None, description="Analysis result")
    key_findings: list | None = Field(default=None)
    recommendations: list | None = Field(default=None)


class LLMService:
    def __init__(self, base_url: str = "http://localhost:11434"):
        """
        Initialize Ollama LLM Service for local model execution.
        
        Args:
            base_url: Base URL for Ollama server (default: localhost:11434)
        """
        self.base_url = base_url
        self.client = httpx.AsyncClient(base_url=base_url)
    
    async def analyze_with_self_check(
        self, 
        prompt: str,
        model: str = None
    ) -> dict[str, Any]:
        """
        Analyze content using Ollama with self-validation.
        
        Args:
            prompt: The prompt/content to analyze
            analysis_type: Type of analysis being performed
            model: Ollama model to use (default: llama2)
            
        Returns:
            Dictionary with analysis results including validation status
        """

        if model is None:
            from .config import LLMProvider, get_default_model
            model = get_default_model(LLMProvider.OLLAMA)
        
        system_prompt = """
You are an expert AI assistant performing analysis.
Analyze the provided content carefully and return a JSON response with the following structure:
{
    "is_valid": boolean,
    "confidence": float (0-1),
    "reason": string (only if is_valid=false),
    "analysis_type_matched": boolean,
    "result": object (analysis results),
    "key_findings": list,
    "recommendations": list
}

Always validate your own output to ensure it matches the required format.
"""

        try:
            response = await self.client.post(
                "/api/chat",
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    "stream": False
                }
            )
            
            response.raise_for_status()
            result_data = response.json()
            content = result_data.get("message", {}).get("content", "")
            
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
        except httpx.ConnectError:
            return {
                "is_valid": False,
                "confidence": 0.0,
                "reason": f"Cannot connect to Ollama server at {self.base_url}"
            }
        except Exception as e:
            return {
                "is_valid": False,
                "confidence": 0.0,
                "reason": f"LLM call exception: {str(e)}"
            }
    
    async def call_llm(self, prompt: str, model: str = "llama2") -> str:
        """
        Make a general LLM call and return raw text response.
        
        Args:
            prompt: The prompt to send to the LLM
            model: Ollama model to use
            
        Returns:
            The LLM response as a string
        """
        try:
            response = await self.client.post(
                "/api/chat",
                json={
                    "model": model,
                    "messages": [
                        {"role": "user", "content": prompt}
                    ],
                    "stream": False
                }
            )
            
            response.raise_for_status()
            result_data = response.json()
            return result_data.get("message", {}).get("content", "")
        except Exception as e:
            return f"Error: {str(e)}"
    
    async def call_llm_json(
        self, 
        prompt: str, 
        model: str = "llama2"
    ) -> dict[str, Any] | None:
        """
        Make an LLM call expecting JSON response and parse it.
        
        Args:
            prompt: The prompt to send to the LLM (should instruct JSON output)
            model: Ollama model to use
            
        Returns:
            Parsed JSON response as a dictionary, or None if parsing fails
        """
        try:
            response = await self.client.post(
                "/api/chat",
                json={
                    "model": model,
                    "messages": [
                        {"role": "user", "content": prompt}
                    ],
                    "stream": False
                }
            )
            
            response.raise_for_status()
            result_data = response.json()
            content = result_data.get("message", {}).get("content", "")
            data = json.loads(content)
            return data
        except json.JSONDecodeError as e:
            print(f"JSON parsing error: {e}")
            return None
        except Exception as e:
            print(f"Error calling LLM: {e}")
            return None
    
    async def close(self):
        """Close the HTTP client connection"""
        await self.client.aclose()

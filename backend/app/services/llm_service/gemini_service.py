# app/services/llm_service/gemini_service.py
import google.generativeai as genai
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
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY environment variable not set")
        
        genai.configure(api_key=api_key)
        self.client = None  # Using module-level API for Gemini
    
    async def analyze_with_self_check(
        self, 
        prompt: str,
        model: str = None
    ) -> Dict[str, Any]:
        """
        Analyze content using Gemini with self-validation.
        
        Args:
            prompt: The prompt/content to analyze
            analysis_type: Type of analysis being performed
            model: Gemini model to use (default: gemini-2.0-flash)
            
        Returns:
            Dictionary with analysis results including validation status
        """
        
        if model is None:
            from .config import get_default_model, LLMProvider
            model = get_default_model(LLMProvider.GEMINI)
        
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
            gen_model = genai.GenerativeModel(
                model_name=model,
                system_instruction=system_prompt
            )
            
            response = gen_model.generate_content(prompt)
            content = response.text
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
    
    async def call_llm(self, prompt: str, model: str = "gemini-2.0-flash") -> str:
        """
        Make a general LLM call and return raw text response.
        
        Args:
            prompt: The prompt to send to the LLM
            model: Gemini model to use
            
        Returns:
            The LLM response as a string
        """
        try:
            gen_model = genai.GenerativeModel(model_name=model)
            response = gen_model.generate_content(prompt)
            return response.text
        except Exception as e:
            return f"Error: {str(e)}"
    
    async def call_llm_json(
        self, 
        prompt: str, 
        if model is None:
            from .config import get_default_model, LLMProvider
            model = get_default_model(LLMProvider.GEMINI)
    ) -> Optional[Dict[str, Any]]:
        """
        Make an LLM call expecting JSON response and parse it.
        
        Args:
            prompt: The prompt to send to the LLM (should instruct JSON output)
            model: Gemini model to use
            
        Returns:
            Parsed JSON response as a dictionary, or None if parsing fails
        """
        try:
            gen_model = genai.GenerativeModel(model_name=model)
            response = gen_model.generate_content(prompt)
            content = response.text
            data = json.loads(content)
            return data
        except json.JSONDecodeError as e:
            print(f"JSON parsing error: {e}")
            return None
        except Exception as e:
            print(f"Error calling LLM: {e}")
            return None

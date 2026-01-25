import os
import json
from typing import Dict, Any, Optional
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI


class LLMService:
    def __init__(self, model: str = "gpt-4-turbo", temperature: float = 0.2, max_tokens: int = 2000):
        load_dotenv()  # Load from .env
        
        # Check API key
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set")
        
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.llm = ChatOpenAI(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens
        )
    
    async def call_llm(self, prompt: str) -> str:
        """
        Make a general LLM call and return raw text response.
        
        Args:
            prompt: The prompt to send to the LLM
            
        Returns:
            The LLM response as a string
        """
        try:
            response = await self.llm.ainvoke(prompt)
            return response.content
        except Exception as e:
            print(f"Error calling LLM: {e}")
            return ""
    
    async def call_llm_json(self, prompt: str) -> Optional[Dict[str, Any]]:
        """
        Make an LLM call expecting JSON response and parse it.
        
        Args:
            prompt: The prompt to send to the LLM (should instruct JSON output)
            
        Returns:
            Parsed JSON response as a dictionary, or None if parsing fails
        """
        try:
            response = await self.llm.ainvoke(prompt)
            content = response.content
            
            # Parse JSON response
            data = json.loads(content)
            return data
            
        except json.JSONDecodeError as e:
            print(f"JSON parsing error: {e}")
            return None
        except Exception as e:
            print(f"Error calling LLM: {e}")
            return None
    
    def set_temperature(self, temperature: float) -> None:
        """
        Update temperature for LLM responses.
        Lower values (0.0-0.3): More deterministic
        Higher values (0.7-1.0): More creative/diverse
        """
        self.temperature = temperature
        self.llm = ChatOpenAI(
            model=self.model,
            temperature=temperature,
            max_tokens=self.max_tokens
        )
    
    def set_max_tokens(self, max_tokens: int) -> None:
        """Update maximum tokens for LLM responses"""
        self.max_tokens = max_tokens
        self.llm = ChatOpenAI(
            model=self.model,
            temperature=self.temperature,
            max_tokens=max_tokens
        )

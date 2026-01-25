"""LLM Service Module

This module provides general-purpose LLM functionality for various analysis tasks.
Specific domain services (e.g., case analysis) are in separate modules.
"""
from .langchain_service import LLMService

__all__ = ["LLMService"]

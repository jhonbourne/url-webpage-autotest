# app/models/schemas.py
from typing import TypedDict, Optional, Dict, Any, List
from enum import Enum
from pydantic import BaseModel, Field

class WorkflowStatus(str, Enum):
    PENDING = "pending"
    FETCHING = "fetching"
    PARSING = "parsing"
    VALIDATING = "validating"
    ANALYZING = "analyzing"
    FORMATTING = "formatting"
    COMPLETED = "completed"
    FAILED = "failed"

class TestCase(BaseModel):
    """Model for individual test case"""
    case_id: int = Field(description="Unique identifier for the test case")
    description: str = Field(description="Natural language description of the test case")
    can_test: bool = Field(description="Whether automated test code can be written for this case")
    reason: str = Field(description="Explanation of why the test can or cannot be automated")
    tags: List[str] = Field(default_factory=list, description="Tags for categorizing the test case (e.g., 'element_click', 'form_input', 'navigation')")

class TestCaseAnalysisResult(BaseModel):
    """Model for test case analysis output"""
    total_cases: int = Field(description="Total number of test cases extracted")
    testable_cases: int = Field(description="Number of test cases that can be automated")
    test_cases: List[TestCase] = Field(description="List of analyzed test cases with testability information")
    analysis_summary: str = Field(description="Summary of the analysis")

class GeneratedCode(BaseModel):
    """Model for generated test code for a single test case"""
    case_id: int = Field(description="ID of the test case this code was generated for")
    case_description: str = Field(description="Description of the test case")
    framework: str = Field(description="Testing framework used (e.g., 'selenium', 'appium', 'playwright')")
    code: str = Field(description="Generated test code")
    imports: List[str] = Field(default_factory=list, description="Required imports for this code")
    setup_needed: bool = Field(default=False, description="Whether setup/teardown methods are needed")
    dependencies: List[str] = Field(default_factory=list, description="External dependencies required")

class CodeGenerationResult(BaseModel):
    """Model for code generation output"""
    total_generated: int = Field(description="Total number of test codes generated")
    generated_codes: List[GeneratedCode] = Field(description="List of generated test codes")
    generation_summary: str = Field(description="Summary of the code generation")
    primary_framework: str = Field(description="Primary testing framework used")
    all_imports: List[str] = Field(default_factory=list, description="All unique imports across all generated codes")

class AnalysisState(TypedDict):
    # Input parameters
    url: str
    analysis_type: str
    custom_prompt: Optional[str]
    options: Dict[str, Any]
    
    # outputs in the process
    raw_html: Optional[str]
    structured_dom: Optional[Dict[str, Any]]
    test_cases: Optional[TestCaseAnalysisResult]
    generated_code: Optional[Any]  # CodeGenerationResult
    
    # state control
    status: WorkflowStatus
    current_step: str
    error_message: Optional[str]
    error_code: Optional[str]
    
    # metadata
    execution_log: List[Dict[str, Any]]
    start_time: Optional[str]
    end_time: Optional[str]
    analysis_result: Optional[Dict[str, Any]]
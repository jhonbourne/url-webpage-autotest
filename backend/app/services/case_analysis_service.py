"""Case analysis service for test case extraction and testability analysis"""
from typing import Any

from llm_service.langchain_service import LLMService

from app.models.schemas import TestCase, TestCaseAnalysisResult


class CaseAnalysisService:
    """Analyzing test cases and determining automation feasibility"""
    
    def __init__(self, model: str = "gpt-4-turbo"):
        self.llm_service = LLMService(model=model)
    
    async def extract_and_analyze_test_cases(
        self,
        case_prompt: str,
        structured_dom: dict[str, Any],
        url: str
    ) -> TestCaseAnalysisResult:
        """
        Extract test cases from natural language prompt and analyze their testability
        based on the website's DOM structure.
        
        Args:
            case_prompt: Natural language description of test cases
            structured_dom: Structured DOM data extracted from the webpage
            url: URL of the webpage being tested
            
        Returns:
            TestCaseAnalysisResult containing analyzed test cases with testability info
        """
        
        # Extract test cases from the prompt
        extraction_prompt = self._build_extraction_prompt(case_prompt)
        extracted_cases = await self.llm_service.call_llm_json(extraction_prompt)
        
        if not extracted_cases or "test_cases" not in extracted_cases:
            extracted_cases = {"test_cases": []}
        
        test_cases_list = extracted_cases.get("test_cases", [])
        
        # Raise exception if no test cases were extracted
        if not test_cases_list:
            raise ValueError("No test cases could be extracted from the provided prompt. Please provide a more detailed test case description.")
        
        # Analyze each case against the DOM structure
        analyzed_cases = await self._analyze_case_testability(
            test_cases_list,
            structured_dom,
            url
        )
        
        # Create analysis result
        testable_count = sum(1 for case in analyzed_cases if case.can_test)
        
        result = TestCaseAnalysisResult(
            total_cases=len(analyzed_cases),
            testable_cases=testable_count,
            test_cases=analyzed_cases,
            analysis_summary=self._generate_summary(analyzed_cases)
        )
        
        return result
    
    def _build_extraction_prompt(self, case_prompt: str) -> str:
        """Build prompt for extracting test cases from natural language"""
        
        extraction_template = """You are an expert QA engineer. Analyze the following test case description and extract individual test cases.

Test Case Description:
{case_prompt}

Extract each test case as a separate item. For each test case, identify:
1. What action needs to be performed (e.g., click, input text, navigate)
2. What element is involved (e.g., button, input field, link)
3. What the expected behavior or outcome is

Ignore any non-test-related information.

Return the extracted test cases as a JSON object with this exact structure:
{{
    "test_cases": [
        {{
            "description": "Clear description of the test case",
            "action": "The action to perform (e.g., 'click', 'input_text', 'navigate') or the check implemented for features",
            "target": "Description of the target element"
        }},
        ...
    ]
}}

Only return valid JSON. Do not include any explanations or markdown formatting."""
        
        return extraction_template.format(case_prompt=case_prompt)
    
    def _build_testability_prompt(
        self,
        case_description: str,
        action: str,
        target: str,
        dom_summary: str,
        url: str
    ) -> str:
        """Build prompt for analyzing if a test case is automatable"""
        
        testability_template = """You are an expert automation test engineer. Analyze whether the following test case can be automated based on the website's DOM structure.

Website URL: {url}

Test Case:
- Description: {case_description}
- Action: {action}
- Target Element: {target}

Website DOM Summary:
{dom_summary}

Analyze this test case and determine:
1. Can this test case be automated with the given DOM?
2. What elements in the DOM would be needed?
3. If it cannot be automated, what is missing?

Return ONLY a JSON object with this exact structure:
{{
    "can_test": true or false,
    "reason": "Detailed explanation of why this can or cannot be automated"
}}

Do not include any other text or markdown formatting."""
        
        return testability_template.format(
            url=url,
            case_description=case_description,
            action=action,
            target=target,
            dom_summary=dom_summary
        )
    
    async def _analyze_case_testability(
        self,
        extracted_cases: list,
        structured_dom: Any, # Dict[str, Any](extracted) or str(HTML)
        url: str
    ) -> list[TestCase]:
        """Analyze testability of each extracted case"""
        
        analyzed_cases = []
        # dom_summary = self._summarize_dom(structured_dom)
        dom_summary = structured_dom  # Use raw structured DOM for better context
        
        for idx, case in enumerate(extracted_cases):
            try:
                case_description = case.get("description", "")
                action = case.get("action", "")
                target = case.get("target", "")
                
                # Build testability analysis prompt
                testability_prompt = self._build_testability_prompt(
                    case_description,
                    action,
                    target,
                    dom_summary,
                    url
                )
                
                # Get LLM response
                analysis = await self.llm_service.call_llm_json(testability_prompt)
                can_test = analysis.get("can_test", False) if analysis else False
                reason = analysis.get("reason", "Unable to determine") if analysis else "Failed to analyze"
                
                # Create TestCase object
                test_case = TestCase(
                    case_id=idx + 1,
                    description=case_description,
                    can_test=can_test,
                    reason=reason,
                    tags=self._extract_tags(action)
                )
                
                analyzed_cases.append(test_case)
                
            except Exception as e:
                print(f"Error analyzing case {idx}: {e}")
                test_case = TestCase(
                    case_id=idx + 1,
                    description=case.get("description", ""),
                    can_test=False,
                    reason=f"Error during analysis: {str(e)}",
                    tags=[]
                )
                analyzed_cases.append(test_case)
        
        return analyzed_cases
    
    def _extract_tags(self, action: str) -> list:
        """Extract tags from the action type"""
        tags = []
        
        action_lower = action.lower()
        
        if "click" in action_lower:
            tags.append("element_click")
        if "input" in action_lower or "text" in action_lower or "type" in action_lower:
            tags.append("form_input")
        if "navigate" in action_lower or "go" in action_lower or "visit" in action_lower:
            tags.append("navigation")
        if "submit" in action_lower:
            tags.append("form_submit")
        if "check" in action_lower or "verify" in action_lower or "assert" in action_lower:
            tags.append("assertion")
        if "scroll" in action_lower:
            tags.append("scroll")
        if "hover" in action_lower or "mouse" in action_lower:
            tags.append("mouse_interaction")
        
        # Default tag if no specific action matched
        if not tags:
            tags.append("custom_action")
        
        return tags
    
    def _generate_summary(self, analyzed_cases: list) -> str:
        """Generate a summary of the analysis results"""
        
        if not analyzed_cases:
            return "No test cases were analyzed."
        
        total = len(analyzed_cases)
        testable = sum(1 for case in analyzed_cases if case.can_test)
        non_testable = total - testable
        
        summary = (
            f"Analysis of {total} test cases completed. "
            f"{testable} case(s) can be automated, "
            f"{non_testable} case(s) cannot be automated with current DOM structure."
        )
        
        return summary

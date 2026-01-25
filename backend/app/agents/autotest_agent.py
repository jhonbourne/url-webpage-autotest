from langgraph.graph import StateGraph, END
from typing import TypedDict, List, Dict, Any, Optional, Literal
from datetime import datetime

from app.services.dom_service import DOMService
from app.services.case_analysis_service import CaseAnalysisService
from app.services.code_generation_service import CodeGenerationService
from app.services.code_execution_service import CodeExecutionService
from app.models.schemas import AnalysisState, WorkflowStatus

class AutoTestAgent:
    def __init__(self):
        self.dom_service = DOMService()
        self.case_analysis_service = CaseAnalysisService()
        self.code_generation_service = CodeGenerationService(primary_framework="selenium")
        self.code_execution_service = CodeExecutionService(timeout=60)
        self.graph = self._build_graph()

        self.dom_attr_keywords = ["class", "id", "href", "src"]
    
    def _build_graph(self):
        """Define workflow"""
        workflow = StateGraph(AnalysisState)
        
        workflow.add_node("fetch_dom", self._fetch_dom)
        workflow.add_node("structure_dom", self._structure_dom)
        workflow.add_node("case_analysis", self._case_analysis)
        workflow.add_node("generate_code", self._generate_code)
        workflow.add_node("check_results", self._check_result)
        workflow.add_node("handle_error", self._handle_error_node)
        
        workflow.set_entry_point("fetch_dom")
        workflow.add_conditional_edges(
            "fetch_dom",
            self._check_node_result,
            {
                "continue": "structure_dom",
                "error": "handle_error"
            }
        )
        workflow.add_edge("structure_dom", "case_analysis")
        workflow.add_conditional_edges(
            "case_analysis",
            self._check_node_result,
            {
                "continue": "generate_code",
                "error": "handle_error"
            }
        )
        workflow.add_conditional_edges(
            "generate_code",
            self._check_node_result,
            {
                "continue": "check_results",
                "error": "handle_error"
            }
        )
        workflow.add_edge("check_results", END)
        workflow.add_edge("handle_error", END)
        
        return workflow.compile()
    
    async def _fetch_dom(self, state: AnalysisState):
        url = state["url"]
        try:
            html = await self.dom_service.get_page_html(
                url,
                wait_for_selector=state.get("options", {}).get("wait_for_selector"),
                timeout=state["options"].get("timeout", 30000)
            )

            if not html or len(html.strip()) < 100:
                    return self._set_error(state, "EMPTY_RESPONSE", "The obtained HTML content is either empty or too short")
            return {**state, "raw_html": html,
                    "status": WorkflowStatus.PARSING,
                    "current_step": "parse DOM structure"}
        except Exception as e:
            error_msg = str(e).lower()
            if "timeout" in error_msg:
                return self._set_error(state, "FETCH_TIMEOUT", f"Webpage acquisition timeout: {url}")
            elif "certificate" in error_msg or "ssl" in error_msg:
                return self._set_error(state, "SSL_ERROR", "The SSL certificate verification failed")
            elif "name or service not known" in error_msg or "getaddrinfo" in error_msg:
                return self._set_error(state, "DNS_ERROR", f"The domain name cannot be resolved: {url}")
            else:
                return self._set_error(state, "FETCH_FAILED", f"Failed to obtain the web page: {str(e)}")
    
    def _structure_dom(self, state: AnalysisState):
        """Extract the structure of elements with specified keywords"""
        structured = self.dom_service.extract_structure(
            state["raw_html"],
            include_text=True,
            include_attributes=self.dom_attr_keywords
        )
        return {**state, "structured_dom": structured,
                "status": WorkflowStatus.ANALYZING,
                "current_step": "analyze test cases"}
    
    # TODO: utilize DOM dict
    async def _case_analysis(self, state: AnalysisState):
        """
        Analyze test cases from the case_prompt using LLM.
        Returns structured test case analysis with testability information
        """
        try:
            case_prompt = state.get("case_prompt")
            structured_dom = state.get("raw_html")
            url = state.get("url")
            
            if not case_prompt:
                return self._set_error(
                    state, 
                    "NO_TEST_CASES", 
                    "No test case prompt provided"
                )
            
            if not structured_dom:
                return self._set_error(
                    state,
                    "NO_DOM_DATA",
                    "DOM structure not available for test case analysis"
                )
            
            # Use LLM service to extract and analyze test cases
            test_cases_analysis = await self.case_analysis_service.extract_and_analyze_test_cases(
                case_prompt=case_prompt,
                structured_dom=structured_dom,
                url=url
            )
            
            # Log the analysis results
            execution_log = state.get("execution_log", [])
            execution_log.append({
                "timestamp": datetime.now().isoformat(),
                "step": "case_analysis",
                "total_cases": test_cases_analysis.total_cases,
                "testable_cases": test_cases_analysis.testable_cases,
                "message": test_cases_analysis.analysis_summary
            })
            
            return {
                **state,
                "test_cases": test_cases_analysis,
                "status": WorkflowStatus.FORMATTING,
                "current_step": "generate test code",
                "execution_log": execution_log
            }
            
        except Exception as e:
            error_msg = str(e).lower()
            if "no test cases" in error_msg:
                return self._set_error(
                    state,
                    "NO_TEST_CASES_EXTRACTED",
                    f"Failed to extract test cases: {str(e)}"
                )
            elif "timeout" in error_msg:
                return self._set_error(
                    state,
                    "ANALYSIS_TIMEOUT",
                    "Test case analysis timed out"
                )
            elif "api" in error_msg or "openai" in error_msg:
                return self._set_error(
                    state,
                    "LLM_ERROR",
                    f"LLM service error during case analysis: {str(e)}"
                )
            else:
                return self._set_error(
                    state,
                    "CASE_ANALYSIS_FAILED",
                    f"Failed to analyze test cases: {str(e)}"
                )
    
    async def _generate_code(self, state: AnalysisState):
        """
        Generate test automation code for each testable case.
        """
        try:
            test_cases_analysis = state.get("test_cases")
            structured_dom = state.get("raw_html")
            url = state.get("url")
            
            if not test_cases_analysis:
                return self._set_error(
                    state,
                    "NO_TEST_CASES_ANALYSIS",
                    "Test case analysis result not available"
                )
            
            if not structured_dom:
                return self._set_error(
                    state,
                    "NO_DOM_DATA",
                    "DOM structure not available for code generation"
                )
            
            # Extract testable cases
            testable_cases = [
                case for case in test_cases_analysis.test_cases
                if case.can_test
            ]
            
            if not testable_cases:
                return self._set_error(
                    state,
                    "NO_TESTABLE_CASES",
                    "No testable cases found to generate code for"
                )
            
            # Generate test code using the code generation service
            code_generation_result = await self.code_generation_service.generate_test_code(
                testable_cases=testable_cases,
                structured_dom=structured_dom,
                url=url
            )
            
            # Log the code generation results
            execution_log = state.get("execution_log", [])
            execution_log.append({
                "timestamp": datetime.now().isoformat(),
                "step": "generate_code",
                "total_generated": code_generation_result.total_generated,
                "primary_framework": code_generation_result.primary_framework,
                "message": code_generation_result.generation_summary
            })
            
            # Store generated code for execution
            generated_code_dict = {
                "total_generated": code_generation_result.total_generated,
                "generated_codes": [
                    {
                        "case_id": code.case_id,
                        "case_description": code.case_description,
                        "framework": code.framework,
                        "code": code.code,
                        "imports": code.imports,
                        "setup_needed": code.setup_needed,
                        "dependencies": code.dependencies
                    }
                    for code in code_generation_result.generated_codes
                ],
                "generation_summary": code_generation_result.generation_summary,
                "primary_framework": code_generation_result.primary_framework,
                "all_imports": code_generation_result.all_imports
            }
            
            return {
                **state,
                "generated_code": generated_code_dict,
                "status": WorkflowStatus.FORMATTING,
                "current_step": "execute test code",
                "execution_log": execution_log
            }
            
        except Exception as e:
            error_msg = str(e).lower()
            if "no testable" in error_msg:
                return self._set_error(
                    state,
                    "NO_TESTABLE_CASES",
                    f"Failed to find testable cases: {str(e)}"
                )
            elif "timeout" in error_msg:
                return self._set_error(
                    state,
                    "CODE_GENERATION_TIMEOUT",
                    "Code generation timed out"
                )
            elif "api" in error_msg or "openai" in error_msg:
                return self._set_error(
                    state,
                    "LLM_ERROR",
                    f"LLM service error during code generation: {str(e)}"
                )
            else:
                return self._set_error(
                    state,
                    "CODE_GENERATION_FAILED",
                    f"Failed to generate test code: {str(e)}"
                )
    
    async def _check_result(self, state: AnalysisState):
        """
        Execute generated test code and verify results.
        
        This node:
        1. Retrieves generated test codes
        2. Executes each test code using CodeExecutionService
        3. Captures pass/fail status
        4. Generates formatted test report
        5. Returns results to user
        """
        try:
            generated_code_dict = state.get("generated_code")
            
            if not generated_code_dict:
                return self._set_error(
                    state,
                    "NO_GENERATED_CODE",
                    "No generated code available for execution"
                )
            
            generated_codes = generated_code_dict.get("generated_codes", [])
            if not generated_codes:
                return self._set_error(
                    state,
                    "EMPTY_GENERATED_CODE",
                    "Generated code list is empty"
                )
            
            # Execute all generated codes
            execution_result = await self.code_execution_service.execute_generated_codes(
                generated_codes
            )
            
            # Get test results list
            test_results = self.code_execution_service.get_test_results_list(
                execution_result["raw_results"]
            )
            
            # Log execution
            execution_log = state.get("execution_log", [])
            execution_log.append({
                "timestamp": datetime.now().isoformat(),
                "step": "check_results",
                "total_executed": execution_result["summary"]["total"],
                "passed": execution_result["summary"]["passed"],
                "failed": execution_result["summary"]["failed"],
                "message": f"Test execution completed - {execution_result['summary']['passed']}/{execution_result['summary']['total']} passed"
            })
            
            # Build analysis result
            analysis_result = {
                "status": "success",
                "test_execution": {
                    "summary": execution_result["summary"],
                    "results": test_results,
                    "formatted_report": execution_result["formatted_results"]
                },
                "generated_code_summary": {
                    "total_generated": generated_code_dict.get("total_generated", 0),
                    "primary_framework": generated_code_dict.get("primary_framework", "unknown")
                }
            }
            
            return {
                **state,
                "status": WorkflowStatus.COMPLETED,
                "current_step": "completed",
                "execution_log": execution_log,
                "analysis_result": analysis_result,
                "end_time": datetime.now().isoformat()
            }
            
        except Exception as e:
            error_msg = str(e).lower()
            if "timeout" in error_msg:
                return self._set_error(
                    state,
                    "EXECUTION_TIMEOUT",
                    "Test execution exceeded timeout"
                )
            else:
                return self._set_error(
                    state,
                    "EXECUTION_FAILED",
                    f"Test execution failed: {str(e)}"
                )
            
    def _handle_error_node(self, state: AnalysisState) -> AnalysisState:
        error_response = {
            "status": "error",
            "error": {
                "code": state["error_code"],
                "message": state["error_message"],
                "failed_step": state["current_step"]
            },
            "logs": state["execution_log"],
            "partial_data": {
                "url": state["url"],
                "raw_html_size": len(state["raw_html"]) if state["raw_html"] else 0,
                "dom_extracted": state["structured_dom"] is not None
            }
        }
        
        return {
            **state,
            "analysis_result": error_response,
            "status": WorkflowStatus.FAILED,
            "end_time": datetime.now().isoformat()
        }
    
    def _check_node_result(self, state: AnalysisState) -> Literal["continue", "error"]:
        if state["status"] == WorkflowStatus.FAILED:
            return "error"
        
        # Check crucial values for each step
        current_step = state["current_step"]
        
        if current_step == "parse DOM structure":
            if not state.get("raw_html"):
                return "error"
        
        elif current_step == "analyze test cases":
            if not state.get("structured_dom"):
                return "error"
        
        elif current_step == "generate test code":
            if not state.get("test_cases"):
                return "error"
        
        elif current_step == "execute test code":
            if not state.get("generated_code"):
                return "error"
        
        # elif current_step == "completed":
        #     if not state.get("analysis_result"):
        #         return "error"
        
        return "continue"
    
    async def analyze(self, url: str, case_prompt: Optional[str] = None, **options):
        """Main entry point when router switched to start workflow"""
        initial_state: AnalysisState = {
            "url": url,
            "case_prompt": case_prompt,
            "options": options,
            "raw_html": None,
            "structured_dom": None,
            "test_cases": None,
            "generated_code": None,
            "analysis_result": None,
            "status": WorkflowStatus.PENDING,
            "current_step": "fetch",
            "error_message": None,
            "error_code": None,
            "execution_log": [],
            "start_time": datetime.now().isoformat(),
            "end_time": None
        }
        
        result = await self.graph.ainvoke(initial_state)
        return result["analysis_result"]
    
    
    def _set_error(self, state: AnalysisState, code: str, message: str) -> AnalysisState:
        return {
            **state,
            "status": WorkflowStatus.FAILED,
            "error_code": code,
            "error_message": message
        }
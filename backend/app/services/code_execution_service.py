from typing import Dict, List, Any, Optional
from datetime import datetime
from app.agents.utils.subprocess_code_execute import execute_single_code, CodeExecutionResult


class CodeExecutionService:
    """Service for executing test codes and collecting results"""
    
    def __init__(self, timeout: int = 60):
        """
        timeout: Execution timeout per test in seconds
        """
        self.timeout = timeout
    
    async def execute_generated_codes(
        self,
        generated_codes: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Execute all generated test codes.
        
        Args:
            generated_codes: List of code objects from code generation node
                Each code object contains: case_id, code, imports, framework, etc.
                
        Returns:
            Dictionary with execution results and formatted output
        """
        execution_results = []
        start_time = datetime.now()
        
        # Execute each generated code
        for code_obj in generated_codes:
            result = self._execute_single_code_obj(code_obj)
            execution_results.append(result)
        
        end_time = datetime.now()
        total_time = (end_time - start_time).total_seconds()
        
        # Format results
        formatted_results = self._format_results(execution_results, total_time)
        
        return {
            "raw_results": execution_results,
            "formatted_results": formatted_results,
            "summary": self._create_summary(execution_results, total_time)
        }
    
    def _execute_single_code_obj(self, code_obj: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a single code object and return formatted result"""
        
        case_id = code_obj.get("case_id", 0)
        code = code_obj.get("code", "")
        imports = code_obj.get("imports", [])
        framework = code_obj.get("framework", "unknown")
        description = code_obj.get("case_description", "")
        
        # Execute the code
        exec_result = execute_single_code(
            code=code,
            case_id=case_id,
            timeout=self.timeout,
            imports=imports
        )
        
        # Format result
        return {
            "case_id": case_id,
            "description": description,
            "framework": framework,
            "status": exec_result.status,
            "execution_time": exec_result.execution_time,
            "stdout": exec_result.stdout[:500] if exec_result.stdout else "",
            "stderr": exec_result.stderr[:500] if exec_result.stderr else "",
            "passed": exec_result.status == "passed"
        }
    
    def _format_results(self, results: List[Dict[str, Any]], total_time: float) -> str:
        """
        Create formatted result string for user display.
        
        Args:
            results: List of execution results
            total_time: Total execution time
            
        Returns:
            Formatted result string
        """
        lines = []
        lines.append("\n" + "=" * 80)
        lines.append("TEST EXECUTION RESULTS")
        lines.append("=" * 80 + "\n")
        
        passed_count = sum(1 for r in results if r["passed"])
        failed_count = len(results) - passed_count
        success_rate = (passed_count / len(results) * 100) if results else 0
        
        # Summary line
        lines.append(f"Total Tests: {len(results)}")
        lines.append(f"Passed: {passed_count} ✓")
        lines.append(f"Failed: {failed_count} ✗")
        lines.append(f"Success Rate: {success_rate:.1f}%")
        lines.append(f"Total Duration: {total_time:.2f}s\n")
        
        # Individual results
        lines.append("-" * 80)
        for result in results:
            status_icon = "✓" if result["passed"] else "✗"
            lines.append(f"{status_icon} Case {result['case_id']}: {result['description']}")
            lines.append(f"  Framework: {result['framework']} | Time: {result['execution_time']:.2f}s | Status: {result['status'].upper()}")
            
            if not result["passed"] and result["stderr"]:
                error_preview = result["stderr"][:100]
                lines.append(f"  Error: {error_preview}")
            
            lines.append("")
        
        lines.append("-" * 80)
        lines.append("=" * 80 + "\n")
        
        return "\n".join(lines)
    
    def _create_summary(self, results: List[Dict[str, Any]], total_time: float) -> Dict[str, Any]:
        passed = sum(1 for r in results if r["passed"])
        failed = len(results) - passed
        
        status_counts = {}
        for r in results:
            status = r["status"]
            status_counts[status] = status_counts.get(status, 0) + 1
        
        return {
            "total": len(results),
            "passed": passed,
            "failed": failed,
            "success_rate": (passed / len(results) * 100) if results else 0,
            "duration": total_time,
            "status_breakdown": status_counts
        }
    
    def get_test_results_list(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Get clean list of test results for programmatic access.
        
        Args:
            results: Raw execution results
            
        Returns:
            Clean list suitable for API response
        """
        return [
            {
                "id": r["case_id"],
                "description": r["description"],
                "framework": r["framework"],
                "status": r["status"],
                "passed": r["passed"],
                "time_seconds": round(r["execution_time"], 2),
                "error": r["stderr"] if not r["passed"] else None
            }
            for r in results
        ]

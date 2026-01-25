import subprocess
import tempfile
import os
import sys
import time
from typing import Dict, Any, Optional


class CodeExecutionResult:
    def __init__(
        self,
        case_id: int,
        code: str,
        status: str,
        stdout: str,
        stderr: str,
        execution_time: float
    ):
        self.case_id = case_id
        self.code = code
        self.status = status  # "passed", "failed", "error", "timeout"
        self.stdout = stdout
        self.stderr = stderr
        self.execution_time = execution_time


def execute_single_code(
    code: str,
    case_id: int = 0,
    timeout: int = 60,
    imports: Optional[list] = None
) -> CodeExecutionResult:
    """
    Args:
        code: Python code to execute
        case_id: Test case identifier
        timeout: Execution timeout in seconds
        imports: List of import statements to prepend
        
    Returns:
        CodeExecutionResult with status and output
    """
    temp_script_path = None
    
    try:
        # Prepare full script with imports
        full_code = ""
        if imports:
            full_code += "\n".join(imports) + "\n"
        full_code += code
        
        # Write to temporary file
        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.py',
            delete=False,
            encoding='utf-8'
        ) as temp_file:
            temp_file.write(full_code)
            temp_script_path = temp_file.name
        
        # Execute the code
        start_time = time.time()
        result = subprocess.run(
            [sys.executable, temp_script_path],
            capture_output=True,
            text=True,
            timeout=timeout
        )
        execution_time = time.time() - start_time
        
        # Determine status
        status = _determine_status(result.returncode, result.stdout, result.stderr)
        
        return CodeExecutionResult(
            case_id=case_id,
            code=code,
            status=status,
            stdout=result.stdout,
            stderr=result.stderr,
            execution_time=execution_time
        )
        
    except subprocess.TimeoutExpired:
        execution_time = time.time() - start_time
        return CodeExecutionResult(
            case_id=case_id,
            code=code,
            status="timeout",
            stdout="",
            stderr=f"Test execution timed out after {timeout}s",
            execution_time=execution_time
        )
    except Exception as e:
        return CodeExecutionResult(
            case_id=case_id,
            code=code,
            status="error",
            stdout="",
            stderr=f"Error executing script: {str(e)}",
            execution_time=0
        )
    finally:
        # Clean up temp file
        if temp_script_path and os.path.exists(temp_script_path):
            try:
                os.unlink(temp_script_path)
            except OSError:
                pass


def _determine_status(returncode: int, stdout: str, stderr: str) -> str:
    """
    Determine test status from execution result.
    
    Args:
        returncode: Process return code
        stdout: Standard output
        stderr: Standard error
        
    Returns:
        Status: "passed", "failed", or "error"
    """
    stdout_lower = stdout.lower()
    stderr_lower = stderr.lower()
    
    # Check for explicit pass/fail markers in output
    if "test passed" in stdout_lower or "passed" in stdout_lower:
        if returncode == 0:
            return "passed"
    
    if "test failed" in stdout_lower or "test failed" in stderr_lower:
        return "failed"
    
    if "error" in stderr_lower or "exception" in stderr_lower:
        return "error"
    
    # Use return code as fallback
    if returncode == 0:
        return "passed"
    else:
        return "failed"
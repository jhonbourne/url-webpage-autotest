from typing import Any

from llm_service.langchain_service import LLMService

from app.models.schemas import CodeGenerationResult, GeneratedCode, TestCase


class CodeGenerationService:
    """Generate test automation code for analyzed test cases"""
    
    def __init__(self, model: str = "gpt-4-turbo", primary_framework: str = "selenium"):
        """
        primary_framework: Primary testing framework (selenium, appium, or playwright)
        """
        self.llm_service = LLMService(model=model)
        self.primary_framework = primary_framework.lower()
        self.supported_frameworks = ["selenium", "appium", "playwright"]
        
        if self.primary_framework not in self.supported_frameworks:
            self.primary_framework = "selenium"
    
    async def generate_test_code(
        self,
        testable_cases: list[TestCase],
        structured_dom: dict[str, Any],
        url: str
    ) -> CodeGenerationResult:
        """
        Generate test automation code for all testable cases.
        
        Args:
            testable_cases: List of test cases that can be automated (can_test=True)
            structured_dom: Structured DOM data from the webpage
            url: URL of the webpage being tested
            
        Returns:
            CodeGenerationResult containing generated test code for each case
        """
        
        if not testable_cases:
            raise ValueError("No testable cases provided for code generation.")
        
        # Filter to only testable cases
        testable = [case for case in testable_cases if case.can_test]
        
        if not testable:
            raise ValueError("No testable cases found among the provided test cases.")
        
        generated_codes = []
        all_imports = set()
        
        # Generate code for each testable case
        for test_case in testable:
            try:
                generated_code = await self._generate_code_for_case(
                    test_case,
                    structured_dom,
                    url
                )
                generated_codes.append(generated_code)
                
                # Collect unique imports
                all_imports.update(generated_code.imports)
                
            except Exception as e:
                # Log error but continue with other cases
                print(f"Error generating code for case {test_case.case_id}: {e}")
                continue
        
        if not generated_codes:
            raise ValueError("Failed to generate code for all testable cases.")
        
        # Create result
        result = CodeGenerationResult(
            total_generated=len(generated_codes),
            generated_codes=generated_codes,
            generation_summary=self._generate_summary(generated_codes),
            primary_framework=self.primary_framework,
            all_imports=list(all_imports)
        )
        
        return result
    
    async def _generate_code_for_case(
        self,
        test_case: TestCase,
        structured_dom: dict[str, Any],
        url: str
    ) -> GeneratedCode:
        """
        Generate test code for a single test case using LLM.
        
        Args:
            test_case: The test case to generate code for
            structured_dom: Structured DOM data
            url: URL being tested
            
        Returns:
            GeneratedCode object with the generated code
        """
        
        # Build the prompt for code generation
        prompt = self._build_code_generation_prompt(
            test_case,
            structured_dom,
            url
        )
        
        # Call LLM to generate code
        code_response = await self.llm_service.call_llm_json(prompt)
        
        if not code_response or "code" not in code_response:
            raise ValueError(f"Failed to generate valid code for case {test_case.case_id}")
        
        # Extract framework selection
        framework = code_response.get("framework", self.primary_framework).lower()
        if framework not in self.supported_frameworks:
            framework = self.primary_framework
        
        # Create GeneratedCode object
        generated_code = GeneratedCode(
            case_id=test_case.case_id,
            case_description=test_case.description,
            framework=framework,
            code=code_response.get("code", ""),
            imports=code_response.get("imports", []),
            setup_needed=code_response.get("setup_needed", False),
            dependencies=code_response.get("dependencies", [])
        )
        
        return generated_code
    
    def _build_code_generation_prompt(
        self,
        test_case: TestCase,
        structured_dom: dict[str, Any],
        url: str
    ) -> str:
        
        # dom_summary = DOMService.summarize_dom(structured_dom)
        dom_summary = structured_dom  # Use raw structured DOM for better context
        
        # Build framework priority string based on primary_framework
        framework_priority = self._build_framework_priority_string()
        
        prompt = f"""You are an expert test automation engineer. Generate Python test automation code for the following test case.

{framework_priority}

**Website URL:** {url}

**Test Case ID:** {test_case.case_id}
**Test Case Description:** {test_case.description}
**Test Case Tags:** {', '.join(test_case.tags)}

**Website DOM Structure:**
{dom_summary}

**Requirements:**
1. Generate complete, executable Python test code
2. Include all necessary imports
3. Handle element waits and timeouts gracefully
4. Use proper assertion statements
5. Include try-except blocks where appropriate
6. Make the code modular and maintainable
7. Ensure the code is not harmful when executed

**Output Format (JSON):**
Return a JSON object with the following structure:
{{
    "framework": "selenium|appium|playwright",
    "code": "complete test code as a single string",
    "imports": ["list of required imports"],
    "setup_needed": "boolean indicating if additional test setup (like database initialization or service mocking) is required before running this test",
    "dependencies": ["list of external dependencies like 'selenium', 'appium-python-client', etc."]
}}

**Code Guidelines:**
- For Selenium: Use WebDriverWait, By selectors, ActionChains for complex interactions
- For Appium: Use MobileElement, desired_capabilities for device setup
- For Playwright: Use browser context, page objects, and assertions
- Always handle stale element exceptions and retries
- Include meaningful assertions to verify test outcomes
- Use descriptive variable and method names

Generate the code now:"""
        
        return prompt
    
    def _build_framework_priority_string(self) -> str:
        """Build dynamic framework priority instruction based on primary_framework"""
        
        if self.primary_framework == "appium":
            return "PRIORITIZE using Appium for mobile/app testing. Use Selenium WebDriver for web testing. Only use Playwright if explicitly required."
        elif self.primary_framework == "playwright":
            return "PRIORITIZE using Playwright for modern web testing. Use Selenium WebDriver for broader browser compatibility. Only use Appium if mobile testing is explicitly required."
        else:  # selenium (default)
            return "PRIORITIZE using Selenium WebDriver when possible. If the test case requires mobile testing, use Appium. Only use Playwright if explicitly required or if Selenium cannot handle the scenario."
    
    def _describe_element(self, element: dict[str, Any]) -> str:
        """Create a readable description of a DOM element"""
        
        parts = []
        
        if "tag" in element:
            parts.append(f"<{element['tag']}>")
        
        if "id" in element:
            parts.append(f"id='{element['id']}'")
        
        if "class" in element:
            classes = element["class"]
            if isinstance(classes, list):
                classes = " ".join(classes)
            parts.append(f"class='{classes}'")
        
        if "text" in element and element["text"]:
            text_preview = element["text"][:50]  # First 50 chars
            parts.append(f"text='{text_preview}'")
        
        if "href" in element:
            parts.append(f"href='{element['href']}'")
        
        if "name" in element:
            parts.append(f"name='{element['name']}'")
        
        if "type" in element:
            parts.append(f"type='{element['type']}'")
        
        return " ".join(parts)
    
    def _generate_summary(self, generated_codes: list[GeneratedCode]) -> str:
        
        if not generated_codes:
            return "No test code was generated."
        
        framework_counts = {}
        for code in generated_codes:
            framework_counts[code.framework] = framework_counts.get(code.framework, 0) + 1
        
        framework_str = ", ".join(f"{count} in {fw}" for fw, count in framework_counts.items())
        
        summary = (
            f"Successfully generated {len(generated_codes)} test code(s). "
            f"Distribution: {framework_str}. "
            f"All code is ready for execution."
        )
        
        return summary

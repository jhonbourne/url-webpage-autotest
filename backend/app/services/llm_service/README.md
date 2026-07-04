# LLM Service Module

Comprehensive LLM service implementations for multiple AI model providers. This module provides a flexible, extensible architecture for agents to select and use the best LLM model for their tasks.

## Supported Providers

### 1. OpenAI (`openai_service.py`)
- **Models**: GPT-4 Turbo, GPT-4, GPT-3.5 Turbo
- **Default Model**: `gpt-4-turbo-preview`
- **Setup**: Requires `OPENAI_API_KEY` environment variable
- **SDK**: Official OpenAI Python SDK
- **Best For**: Code generation, complex reasoning, general-purpose tasks

### 2. Claude (`claude_service.py`)
- **Models**: Claude 3 Opus, Claude 3 Sonnet, Claude 3 Haiku
- **Default Model**: `claude-3-opus-20240229`
- **Setup**: Requires `ANTHROPIC_API_KEY` environment variable
- **SDK**: Anthropic Python SDK
- **Best For**: Code analysis, detailed content review, long-form analysis

### 3. Gemini (`gemini_service.py`)
- **Models**: Gemini 2.0 Flash, Gemini Pro
- **Default Model**: `gemini-2.0-flash`
- **Setup**: Requires `GOOGLE_API_KEY` environment variable
- **SDK**: Google Generative AI Python SDK
- **Best For**: Web content analysis, fast responses, multimodal tasks

### 4. Cohere (`cohere_service.py`)
- **Models**: Command R Plus, Command R, Command
- **Default Model**: `command-r-plus`
- **Setup**: Requires `COHERE_API_KEY` environment variable
- **SDK**: Cohere Python SDK
- **Best For**: Text summarization, classification, cost-effective solutions

### 5. Ollama (`ollama_service.py`)
- **Models**: Llama 2, Mistral, Neural Chat, and more
- **Default Model**: `llama2`
- **Setup**: Requires local Ollama server running (default: `http://localhost:11434`)
- **SDK**: HTTP REST API
- **Best For**: Local/offline execution, privacy-sensitive tasks, cost-free operation

## Installation

Install required dependencies based on which providers you'll use:

```bash
# All providers
pip install openai anthropic google-generativeai cohere httpx python-dotenv pydantic

# Or install individually:
pip install openai              # For OpenAI
pip install anthropic          # For Claude
pip install google-generativeai # For Gemini
pip install cohere             # For Cohere
# Ollama uses httpx which is included above
```

## Environment Setup

Create a `.env` file in your project root with API keys:

```env
# OpenAI
OPENAI_API_KEY=your_openai_api_key

# Anthropic (Claude)
ANTHROPIC_API_KEY=your_anthropic_api_key

# Google (Gemini)
GOOGLE_API_KEY=your_google_api_key

# Cohere
COHERE_API_KEY=your_cohere_api_key

# Ollama (optional, defaults to localhost:11434)
OLLAMA_BASE_URL=http://localhost:11434
```

## Usage

### Basic Usage - Using LLMSelector

```python
from app.services.llm_service.llm_selector import LLMSelector, LLMProvider

selector = LLMSelector()

# Get service for OpenAI
openai_service = selector.get_service(LLMProvider.OPENAI)

# Get service for Claude (string format)
claude_service = selector.get_service("claude")

# Get service for Ollama with custom URL
ollama_service = selector.get_service(LLMProvider.OLLAMA, base_url="http://192.168.1.100:11434")

# Get default model name for a provider
model_name = selector.get_model_name(LLMProvider.GEMINI)  # Returns "gemini-2.0-flash"

# Select best provider for a task
best_provider = selector.select_best_provider_for_task("code_analysis")
service = selector.get_service(best_provider)

# List all available providers
providers = selector.list_providers()
print(providers)  # {'openai': 'gpt-4-turbo-preview', 'claude': 'claude-3-opus-20240229', ...}
```

### Direct Service Usage

```python
from app.services.llm_service.claude_service import LLMService

# Initialize service
service = LLMService()

# Analyze content with self-check
result = await service.analyze_with_self_check(
    prompt="Analyze this code for performance issues...",
    analysis_type="code_analysis",
    model="claude-3-opus-20240229"
)

# Make simple LLM call
response = await service.call_llm(
    prompt="Explain what this function does",
    model="claude-3-opus-20240229"
)

# Call LLM expecting JSON response
json_response = await service.call_llm_json(
    prompt='Return a JSON object with this data: {"key": "value"}',
    model="claude-3-opus-20240229"
)
```

## Key Features

### AnalysisResult Model
All services return structured results:

```python
{
    "is_valid": bool,                    # Whether input is valid
    "confidence": float,                 # Confidence score (0-1)
    "reason": str,                       # Explanation if invalid
    "analysis_type_matched": bool,       # Whether type matches content
    "result": dict,                      # Actual analysis results
    "key_findings": list,                # Key findings from analysis
    "recommendations": list              # Recommendations
}
```

### Error Handling
All services include comprehensive error handling:
- JSON parsing errors
- API connection failures
- Format validation
- Graceful degradation

### Async Support
All methods are async-compatible for concurrent operations:

```python
import asyncio

async def analyze_multiple():
    services = {
        "openai": LLMSelector.get_service(LLMProvider.OPENAI),
        "claude": LLMSelector.get_service(LLMProvider.CLAUDE),
        "gemini": LLMSelector.get_service(LLMProvider.GEMINI),
    }
    
    prompts = ["prompt1", "prompt2", "prompt3"]
    
    # Run all in parallel
    tasks = [
        services["openai"].call_llm(prompts[0]),
        services["claude"].call_llm(prompts[1]),
        services["gemini"].call_llm(prompts[2]),
    ]
    
    results = await asyncio.gather(*tasks)
    return results
```

## Task-Based Provider Selection

The selector automatically recommends the best provider for different tasks:

| Task Type | Recommended Provider | Reason |
|-----------|---------------------|--------|
| `code_analysis` | Claude | Excellent code understanding |
| `code_generation` | OpenAI | Superior generation quality |
| `summarization` | Cohere | Optimized for text summarization |
| `content_review` | Claude | Detailed content analysis |
| `web_analysis` | Gemini | Good at web content understanding |
| `fast_response` | Gemini | Fastest token generation |
| `cost_effective` | Ollama | Free local execution |

Usage:
```python
task = "code_analysis"
best_provider = LLMSelector.select_best_provider_for_task(task)
service = LLMSelector.get_service(best_provider)
```

## Integration with Agents

Agents can dynamically select the best LLM provider:

```python
from app.services.llm_service.llm_selector import LLMSelector

class MyAgent:
    def __init__(self, task_type: str = "general"):
        self.task_type = task_type
        self.provider = LLMSelector.select_best_provider_for_task(task_type)
        self.llm = LLMSelector.get_service(self.provider)
    
    async def execute(self, prompt: str):
        result = await self.llm.analyze_with_self_check(
            prompt=prompt,
            analysis_type=self.task_type
        )
        return result
```

## Advanced Configuration

### Custom Model Selection
```python
# Override default model
service = LLMSelector.get_service(LLMProvider.OPENAI)
result = await service.analyze_with_self_check(
    prompt="...",
    analysis_type="code_analysis",
    model="gpt-4"  # Use GPT-4 instead of default
)
```

### Ollama Local Server
To use local Ollama models:

1. Download and install Ollama: https://ollama.ai
2. Pull a model: `ollama pull llama2`
3. Start Ollama server: `ollama serve`
4. Use in code:
```python
service = LLMSelector.get_service(
    LLMProvider.OLLAMA,
    base_url="http://localhost:11434"
)
```

## Adding New Providers

To add a new LLM provider:

1. Create a new service file (e.g., `new_provider_service.py`)
2. Implement the `LLMService` class with these methods:
   - `analyze_with_self_check()`
   - `call_llm()`
   - `call_llm_json()`
3. Add provider to `LLMProvider` enum in `llm_selector.py`
4. Add initialization logic to `LLMSelector.get_service()`
5. Add default model to `DEFAULT_MODELS` dict
6. Update task recommendations if applicable

## Troubleshooting

### API Key Issues
```python
# Error: "API_KEY environment variable not set"
# Solution: Ensure .env file exists with proper API keys
from dotenv import load_dotenv
load_dotenv()  # Manually load if needed
```

### Connection Errors (Ollama)
```python
# Error: "Cannot connect to Ollama server"
# Solutions:
# 1. Ensure Ollama is running: ollama serve
# 2. Check URL is correct
# 3. For remote: ollama serve --bind 0.0.0.0:11434
```

### JSON Parsing Errors
```python
# Error: "LLM returns in a non-JSON format"
# Solution: Ensure prompt instructs model to return valid JSON
# Include in prompt: "Return ONLY valid JSON, no markdown"
```

## Contributing

When adding new LLM providers or features:
1. Follow the same structure as existing services
2. Include comprehensive docstrings
3. Add error handling for API-specific failures
4. Update this README with provider details
5. Add example usage in docstrings

## License

Same as parent project

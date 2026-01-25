from flask import Blueprint, request, Response
from typing import Optional, Dict, Any
from pydantic import BaseModel, HttpUrl
import asyncio
import json
from app.agents.autotest_agent import AutoTestAgent

agent = AutoTestAgent()

bp = Blueprint('url_test', __name__)

# # Non-streaming version
# @bp.route('/test-webpage',response_model=dict)
# async def test_url():
#     json_msg = request.get_json()
#     request_data = TestRequest(**json_msg)
#     try:
#         result = await agent.analyze(
#             url=str(request_data.url),
#             case_prompt=request_data.prompt,
#             options=request_data.options or {}
#         )
#         return {"status": "success", "data": result}
#     except Exception as e:
#         return {"status": "error", "message": str(e)}, 500

class TestRequest(BaseModel):
    url: HttpUrl
    prompt: Optional[str] = None
    options: Optional[Dict[str, Any]] = None

def _emit_event(event_type: str, data: Any = None) -> str:
    """Create a JSON event string for streaming."""
    event = {
        "type": event_type,
        "data": data
    }
    return json.dumps(event) + "\n"

def _stream_generator():
    """Generator function for streaming events."""
    try:
        json_msg = request.get_json()
        
        try:
            request_data = TestRequest(**json_msg)
        except Exception as e:
            # Emit validation error immediately
            yield _emit_event("error", {
                "message": f"Invalid request: {str(e)}",
                "type": "ValidationError"
            })
            return
        
        # Emit start event
        yield _emit_event("started", {
            "url": str(request_data.url),
            "prompt": request_data.prompt
        })
        
        # Run the async analyze in a new event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(
                agent.analyze(
                    url=str(request_data.url),
                    case_prompt=request_data.prompt,
                    options=request_data.options or {}
                )
            )
            
            # Emit final result in standard format
            final_response = {"status": "success", "data": result}
            yield _emit_event("completed", final_response)
            
        finally:
            loop.close()
            
    except Exception as e:
        # Emit error in standard format
        final_response = {"status": "error", "message": str(e)}
        yield _emit_event("error", final_response)

@bp.route('/test-webpage', methods=['POST'])
def test_url():
    return Response(
        _stream_generator(),
        mimetype='application/x-ndjson',
        headers={'Content-Type': 'application/x-ndjson; charset=utf-8'}
    )
    

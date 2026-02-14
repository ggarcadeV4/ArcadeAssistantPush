from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import sys
from pathlib import Path
import importlib.util
import os

router = APIRouter()

class ChatRequest(BaseModel):
    prompt: str
    model: str = "claude-3-sonnet-20240229"

@router.post("/chat")
async def chat_with_claude(request: ChatRequest):
    """Send chat message to Claude API"""

    try:
        # Offline-by-default semantics: require API key presence
        api_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY")
        if not api_key:
            return JSONResponse(status_code=501, content={
                "code": "NOT_CONFIGURED",
                "message": "Claude not configured"
            })
        # Import the Claude client service
        claude_client_path = Path(__file__).parent.parent.parent / "services" / "+ai" / "claude_client.py"

        spec = importlib.util.spec_from_file_location("claude_client", claude_client_path)
        claude_client = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(claude_client)

        # Call the Claude service
        response = claude_client.call_claude(request.prompt, request.model)

        return JSONResponse(content={
            "status": "success",
            "response": response,
            "model": request.model
        })

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": f"Failed to process Claude request: {str(e)}"
            }
        )

@router.get("/test")
async def test_claude_connection():
    """Test Claude API connection"""

    try:
        api_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY")
        if not api_key:
            return JSONResponse(status_code=501, content={
                "code": "NOT_CONFIGURED",
                "message": "Claude not configured"
            })
        # Import the Claude client service
        claude_client_path = Path(__file__).parent.parent.parent / "services" / "+ai" / "claude_client.py"

        spec = importlib.util.spec_from_file_location("claude_client", claude_client_path)
        claude_client = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(claude_client)

        # Test the connection
        result = claude_client.test_claude_connection()

        return JSONResponse(content=result)

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": f"Failed to test Claude connection: {str(e)}"
            }
        )

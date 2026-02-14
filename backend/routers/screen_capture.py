from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
import sys
from pathlib import Path
import importlib.util

router = APIRouter()

@router.post("/capture")
async def capture_screen(request: Request):
    """Capture full screen and return filepath"""

    try:
        # Import and call the screen capture function
        screen_capture_path = Path(__file__).parent.parent.parent / "services" / "+visual-core" / "screen_capture.py"

        # Load the module dynamically
        spec = importlib.util.spec_from_file_location("screen_capture", screen_capture_path)
        screen_capture = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(screen_capture)

        # Call the capture function
        filepath = screen_capture.capture_full_screen()

        if filepath:
            return JSONResponse(content={
                "status": "success",
                "filepath": filepath,
                "message": "Screen captured successfully"
            })
        else:
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message": "Screen capture failed"
                }
            )

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": f"Failed to capture screen: {str(e)}"
            }
        )
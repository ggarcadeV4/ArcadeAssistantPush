#!/usr/bin/env python3
"""
Minimal backend server for testing controller detection
"""

import os
import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_dir))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Import only the console router
from backend.routers.console import router as console_router

app = FastAPI(
    title="Arcade Assistant - Minimal API",
    description="Minimal API for testing controller detection",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include console router
app.include_router(console_router, prefix="/api/local/console", tags=["console"])

@app.get("/health")
async def health():
    return {"status": "ok"}

if __name__ == "__main__":
    print("Starting minimal backend on 0.0.0.0:8000...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
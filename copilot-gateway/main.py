#!/usr/bin/env python3
"""
Copilot OpenAI Gateway - OpenAI-compatible interface for GitHub Copilot API.

Uses `gh auth token` to authenticate with GitHub Copilot.
Proxies requests to api.githubcopilot.com with proper headers.

Usage:
    python main.py
    # or
    uvicorn main:app --host 0.0.0.0 --port 8001
"""

import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

# --- Configuration ---
PROXY_API_KEY = os.getenv("PROXY_API_KEY", "changeme_proxy_secret")
COPILOT_API_BASE = "https://api.githubcopilot.com"
PORT = int(os.getenv("PORT", "8001"))

# Token cache
_gh_token_cache: Optional[str] = None
_gh_token_expires: Optional[datetime] = None


def get_gh_token() -> str:
    """Get GitHub token using `gh auth token` command."""
    global _gh_token_cache, _gh_token_expires
    
    # Cache token for 5 minutes
    now = datetime.now(timezone.utc)
    if _gh_token_cache and _gh_token_expires and now < _gh_token_expires:
        return _gh_token_cache
    
    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode != 0:
            raise RuntimeError(f"gh auth token failed: {result.stderr}")
        
        token = result.stdout.strip()
        if not token:
            raise RuntimeError("Empty token from gh auth token")
        
        _gh_token_cache = token
        _gh_token_expires = datetime.now(timezone.utc).replace(
            minute=datetime.now(timezone.utc).minute + 5
        )
        return token
    except FileNotFoundError:
        raise RuntimeError("gh CLI not found. Install with: brew install gh")
    except subprocess.TimeoutExpired:
        raise RuntimeError("gh auth token timed out")


# --- Security ---
api_key_header = APIKeyHeader(name="Authorization", auto_error=False)


async def verify_api_key(auth_header: str = Depends(api_key_header)) -> bool:
    """Verify API key in Authorization header."""
    if not auth_header or auth_header != f"Bearer {PROXY_API_KEY}":
        raise HTTPException(status_code=401, detail="Invalid or missing API Key")
    return True


# --- FastAPI App ---
app = FastAPI(
    title="Copilot OpenAI Gateway",
    description="OpenAI-compatible interface for GitHub Copilot API",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    print(f"[REQUEST] {request.method} {request.url.path}")
    try:
        response = await call_next(request)
        print(f"[RESPONSE] {request.url.path} -> {response.status_code}")
        return response
    except Exception as e:
        print(f"[ERROR] {request.url.path} -> {e}")
        raise


# --- Models ---
class Message(BaseModel):
    role: str
    content: str
    
    class Config:
        extra = "allow"  # Allow extra fields


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list
    stream: bool = False
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    
    class Config:
        extra = "allow"  # Allow extra fields from Droid


# --- Routes ---
@app.get("/")
async def root():
    return {"status": "ok", "message": "Copilot OpenAI Gateway is running"}


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@app.get("/v1/models", dependencies=[Depends(verify_api_key)])
async def get_models():
    """Proxy models list from Copilot API."""
    try:
        gh_token = get_gh_token()
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{COPILOT_API_BASE}/models",
                headers={"Authorization": f"Bearer {gh_token}"}
            )
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=response.text
                )
            
            # Transform to OpenAI format
            data = response.json()
            models = data.get("data", [])
            
            # Get base models from Copilot
            base_models = [
                {
                    "id": m["id"],
                    "object": "model",
                    "owned_by": m.get("vendor", "github-copilot"),
                    "permission": []
                }
                for m in models
                if m.get("model_picker_enabled", False)
            ]
            
            # Add our custom model aliases that Droid expects
            custom_models = [
                {"id": "copilot-opus-45", "object": "model", "owned_by": "github-copilot", "permission": []},
                {"id": "copilot-opus-4.5", "object": "model", "owned_by": "github-copilot", "permission": []},
                {"id": "copilot-sonnet-4.5", "object": "model", "owned_by": "github-copilot", "permission": []},
                {"id": "copilot-haiku-4.5", "object": "model", "owned_by": "github-copilot", "permission": []},
                {"id": "claude-opus-4-5", "object": "model", "owned_by": "github-copilot", "permission": []},
                {"id": "claude-sonnet-4-5", "object": "model", "owned_by": "github-copilot", "permission": []},
            ]
            
            return {
                "object": "list",
                "data": custom_models + base_models
            }
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/v1/chat/completions", dependencies=[Depends(verify_api_key)])
async def chat_completions(request: Request):
    """Proxy chat completions to Copilot API."""
    try:
        gh_token = get_gh_token()
        
        # Get raw request body
        raw_body = await request.json()
        print(f"[DEBUG] Incoming request: {json.dumps(raw_body, default=str)[:500]}")
        
        model = raw_body.get("model", "")
        stream = raw_body.get("stream", False)
        
        # Model mapping for custom names
        MODEL_MAP = {
            "copilot-opus-4.5": "claude-opus-4.5",
            "copilot-opus-45": "claude-opus-4.5",
            "copilot-sonnet-4.5": "claude-sonnet-4.5",
            "copilot-haiku-4.5": "claude-haiku-4.5",
            "claude-opus-4-5": "claude-opus-4.5",
            "claude-sonnet-4-5": "claude-sonnet-4.5",
        }
        actual_model = MODEL_MAP.get(model, model)
        
        # Build request payload - pass through all fields
        payload = {
            "model": actual_model,
            "messages": raw_body.get("messages", []),
            "stream": stream,
        }
        
        # Pass through optional fields if present
        for key in ["max_tokens", "temperature", "top_p", "stop", "n", "presence_penalty", 
                    "frequency_penalty", "logit_bias", "user", "tools", "tool_choice"]:
            if key in raw_body:
                payload[key] = raw_body[key]
        
        headers = {
            "Authorization": f"Bearer {gh_token}",
            "Content-Type": "application/json",
        }
        
        print(f"[DEBUG] Sending to Copilot API: model={actual_model}, stream={stream}")
        
        if stream:
            return StreamingResponse(
                stream_copilot_response(payload, headers),
                media_type="text/event-stream"
            )
        else:
            async with httpx.AsyncClient(timeout=120) as client:
                response = await client.post(
                    f"{COPILOT_API_BASE}/chat/completions",
                    headers=headers,
                    json=payload
                )
                
                if response.status_code != 200:
                    # Check for forbidden (model not enabled)
                    if response.status_code == 403 or "forbidden" in response.text.lower():
                        raise HTTPException(
                            status_code=403,
                            detail=f"Model '{model}' is not enabled or requires policy acceptance. "
                                   f"Check Copilot settings at https://github.com/settings/copilot"
                        )
                    print(f"[DEBUG] Copilot API error: {response.status_code} - {response.text[:500]}")
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=response.text
                    )
                
                return response.json()
                
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


async def stream_copilot_response(payload: dict, headers: dict):
    """Stream response from Copilot API."""
    print(f"[DEBUG] Starting stream for model={payload.get('model')}")
    async with httpx.AsyncClient(timeout=300) as client:
        async with client.stream(
            "POST",
            f"{COPILOT_API_BASE}/chat/completions",
            headers=headers,
            json=payload
        ) as response:
            print(f"[DEBUG] Stream response status: {response.status_code}")
            if response.status_code != 200:
                error_text = await response.aread()
                print(f"[DEBUG] Stream error: {error_text.decode()[:500]}")
                yield f"data: {json.dumps({'error': {'message': error_text.decode(), 'status': response.status_code}})}\n\n"
                return
            
            async for line in response.aiter_lines():
                if line:
                    # Add "object": "chat.completion.chunk" to match OpenAI format
                    if line.startswith("data: ") and not line.startswith("data: [DONE]"):
                        try:
                            data = json.loads(line[6:])  # Skip "data: " prefix
                            if "object" not in data:
                                data["object"] = "chat.completion.chunk"
                            yield f"data: {json.dumps(data)}\n\n"
                        except json.JSONDecodeError:
                            yield f"{line}\n\n"
                    else:
                        yield f"{line}\n\n"
            
            yield "data: [DONE]\n\n"


# --- Entry Point ---
if __name__ == "__main__":
    import uvicorn
    
    # Check gh CLI is available
    try:
        token = get_gh_token()
        print(f"✓ GitHub CLI authenticated")
    except RuntimeError as e:
        print(f"✗ Error: {e}")
        print("\nTo authenticate, run:")
        print("  gh auth login")
        print("  gh auth refresh --scopes copilot")
        sys.exit(1)
    
    print(f"Starting Copilot Gateway on port {PORT}...")
    uvicorn.run(app, host="0.0.0.0", port=PORT)

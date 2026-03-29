"""
LLM Speed Compare — FastAPI backend.
Proxies streaming chat completions from two OpenAI-compatible providers via SSE.
All configuration is loaded from environment variables.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.requests import Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from openai import AsyncOpenAI

load_dotenv(Path(__file__).parent / ".env")

# ---------------------------------------------------------------------------
# Provider config — loaded once at startup
# ---------------------------------------------------------------------------
PROVIDERS = {
    "a": {
        "base_url": os.environ["PROVIDER_A_BASE_URL"],
        "api_key": os.environ["PROVIDER_A_API_KEY"],
        "model": os.environ["PROVIDER_A_MODEL"],
        "label": os.environ["PROVIDER_A_LABEL"],
    },
    "b": {
        "base_url": os.environ["PROVIDER_B_BASE_URL"],
        "api_key": os.environ["PROVIDER_B_API_KEY"],
        "model": os.environ["PROVIDER_B_MODEL"],
        "label": os.environ["PROVIDER_B_LABEL"],
    },
}

# Pre-build async OpenAI clients (one per provider)
CLIENTS = {
    key: AsyncOpenAI(
        base_url=cfg["base_url"].rstrip("/") if cfg["base_url"].rstrip("/").endswith("/v1") else cfg["base_url"].rstrip("/") + "/v1",
        api_key=cfg["api_key"],
    )
    for key, cfg in PROVIDERS.items()
}

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="LLM Speed Compare")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def warmup():
    """Send a tiny request to Provider A to warm up the model in the TEE."""
    try:
        stream = await CLIENTS["a"].chat.completions.create(
            model=PROVIDERS["a"]["model"],
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=1,
            stream=True,
        )
        async for _ in stream:
            pass
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Shared streaming helper — identical logic for both providers
# ---------------------------------------------------------------------------
async def _stream_provider(provider_key: str, prompt: str):
    """Yield SSE-formatted lines from the given provider."""
    client = CLIENTS[provider_key]
    model = PROVIDERS[provider_key]["model"]

    stream = await client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        stream=True,
    )

    async for chunk in stream:
        delta = chunk.choices[0].delta if chunk.choices else None
        content = delta.content if delta else None
        if content is not None:
            yield f"data: {content}\n\n"

    yield "data: [DONE]\n\n"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.post("/stream/a")
async def stream_a(request: Request):
    body = await request.json()
    return StreamingResponse(
        _stream_provider("a", body["prompt"]),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/stream/b")
async def stream_b(request: Request):
    body = await request.json()
    return StreamingResponse(
        _stream_provider("b", body["prompt"]),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


FRONTEND_DIR = Path(__file__).parent / "frontend"


@app.get("/")
async def root():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/config")
async def config():
    return JSONResponse({
        "label_a": PROVIDERS["a"]["label"],
        "label_b": PROVIDERS["b"]["label"],
        "model_a": PROVIDERS["a"]["model"],
        "model_b": PROVIDERS["b"]["model"],
    })

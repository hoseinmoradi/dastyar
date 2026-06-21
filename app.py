from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from openai import OpenAI
from typing import Optional
import os
import time

from logging_config import (
    app_logger,
    new_request_id,
    current_request_id,
    log_llm_request,
    log_llm_response,
    log_llm_error,
)

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
# Smaller model = much faster on CPU-only machines.
# OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma2:9b")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")

# Generation tuning (override via environment variables).
# Capping output length is one of the biggest latency wins on CPU.
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "512"))
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.3"))
# Keep the model resident in RAM so we avoid reload cost between requests.
# Accepts an Ollama duration string ("30m", "1h") or "-1" to keep forever.
KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "30m")
REQUEST_TIMEOUT = float(os.getenv("LLM_REQUEST_TIMEOUT", "120"))

# Ollama exposes an OpenAI-compatible API; api_key is required by the client
# but unused by the local server.
client = OpenAI(
    api_key="ollama",
    base_url=OLLAMA_BASE_URL,
    timeout=REQUEST_TIMEOUT,
)


# =========================
# FastAPI
# =========================

app = FastAPI(
    title="Internal Agent Service",
    version="1.0.0"
)


# =========================
# Request Logging Middleware
# =========================

@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    rid = new_request_id()
    start = time.perf_counter()

    app_logger.info(
        "request_start %s %s",
        request.method,
        request.url.path,
        extra={"payload": {
            "event": "request_start",
            "method": request.method,
            "path": request.url.path,
            "client": request.client.host if request.client else None,
        }},
    )

    try:
        response = await call_next(request)
    except Exception as exc:
        latency_ms = (time.perf_counter() - start) * 1000
        app_logger.error(
            "request_error %s %s latency=%.0fms error=%s",
            request.method,
            request.url.path,
            latency_ms,
            exc,
            extra={"payload": {
                "event": "request_error",
                "method": request.method,
                "path": request.url.path,
                "latency_ms": round(latency_ms, 2),
                "error_type": type(exc).__name__,
                "error": str(exc),
            }},
            exc_info=True,
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "request_id": rid},
        )

    latency_ms = (time.perf_counter() - start) * 1000
    response.headers["X-Request-ID"] = rid
    app_logger.info(
        "request_end %s %s status=%s latency=%.0fms",
        request.method,
        request.url.path,
        response.status_code,
        latency_ms,
        extra={"payload": {
            "event": "request_end",
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "latency_ms": round(latency_ms, 2),
        }},
    )
    return response


# =========================
# Agent Prompts
# =========================

# Shared instruction forced into every agent so the model never replies in
# another language, regardless of the language of the incoming message.
PERSIAN_RULE = (
    "\nIMPORTANT: You MUST always respond in Persian (Farsi) only, "
    "no matter what language the user writes in. "
    "Do not use English or any other language in your answer. "
    "Do not add emojis unless the user uses them first.\n"
)

AGENTS = {
    "general": """
You are a helpful internal company assistant.
Answer professionally.
""" + PERSIAN_RULE,

    "hr": """
You are an HR assistant.
Answer questions related to employees, leave policies and company rules.
""" + PERSIAN_RULE,

    "crm": """
You are a CRM assistant.
Help users with customer information.
""" + PERSIAN_RULE,

    "finance": """
You are a finance assistant.
Help users with accounting and financial questions.
""" + PERSIAN_RULE,
}

# =========================
# Request Models
# =========================

class ChatRequest(BaseModel):
    message: str
    agent_name: str = "general"
    system_prompt: Optional[str] = None


class ChatResponse(BaseModel):
    response: str


# =========================
# Prompt Resolver
# =========================

def get_system_prompt(
    agent_name: str,
    custom_prompt: Optional[str]
):

    if custom_prompt:
        return custom_prompt

    if agent_name in AGENTS:
        return AGENTS[agent_name]

    raise HTTPException(
        status_code=404,
        detail=f"Agent '{agent_name}' not found"
    )


# =========================
# LLM Call
# =========================

def ask_llm(
    user_message: str,
    system_prompt: str,
    agent_name: str = "general"
):

    log_llm_request(
        agent_name=agent_name,
        model=OLLAMA_MODEL,
        system_prompt=system_prompt,
        user_message=user_message,
    )

    start = time.perf_counter()
    try:
        completion = client.chat.completions.create(
            model=OLLAMA_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": user_message
                }
            ],
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
            extra_body={"keep_alive": KEEP_ALIVE},
        )
    except Exception as exc:
        latency_ms = (time.perf_counter() - start) * 1000
        log_llm_error(
            agent_name=agent_name,
            model=OLLAMA_MODEL,
            latency_ms=latency_ms,
            error=exc,
        )
        raise HTTPException(
            status_code=502,
            detail=f"LLM call failed: {exc}",
        )

    latency_ms = (time.perf_counter() - start) * 1000
    response_text = completion.choices[0].message.content

    usage = None
    if getattr(completion, "usage", None) is not None:
        usage = {
            "prompt_tokens": completion.usage.prompt_tokens,
            "completion_tokens": completion.usage.completion_tokens,
            "total_tokens": completion.usage.total_tokens,
        }

    log_llm_response(
        agent_name=agent_name,
        model=OLLAMA_MODEL,
        response_text=response_text,
        latency_ms=latency_ms,
        usage=usage,
    )

    return response_text


# =========================
# Agent Orchestrator
# =========================

def run_agent(
    user_message: str,
    agent_name: str,
    custom_prompt: Optional[str]
):

    system_prompt = get_system_prompt(
        agent_name,
        custom_prompt
    )

    return ask_llm(
        user_message,
        system_prompt,
        agent_name=agent_name,
    )


# =========================
# Endpoints
# =========================

@app.get("/")
def health():

    return {
        "status": "ok",
        "service": "internal-agent"
    }


@app.post(
    "/chat",
    response_model=ChatResponse
)
def chat(req: ChatRequest):

    result = run_agent(
        user_message=req.message,
        agent_name=req.agent_name,
        custom_prompt=req.system_prompt
    )

    return ChatResponse(
        response=result
    )


@app.post("/chat/stream")
def chat_stream(req: ChatRequest):
    """Stream the response token-by-token to reduce perceived latency."""

    system_prompt = get_system_prompt(req.agent_name, req.system_prompt)

    log_llm_request(
        agent_name=req.agent_name,
        model=OLLAMA_MODEL,
        system_prompt=system_prompt,
        user_message=req.message,
    )

    def token_generator():
        start = time.perf_counter()
        collected = []
        try:
            stream = client.chat.completions.create(
                model=OLLAMA_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": req.message},
                ],
                temperature=TEMPERATURE,
                max_tokens=MAX_TOKENS,
                stream=True,
                extra_body={"keep_alive": KEEP_ALIVE},
            )
            for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    collected.append(delta)
                    yield delta
        except Exception as exc:
            latency_ms = (time.perf_counter() - start) * 1000
            log_llm_error(
                agent_name=req.agent_name,
                model=OLLAMA_MODEL,
                latency_ms=latency_ms,
                error=exc,
            )
            yield f"\n[error] {exc}"
            return

        latency_ms = (time.perf_counter() - start) * 1000
        log_llm_response(
            agent_name=req.agent_name,
            model=OLLAMA_MODEL,
            response_text="".join(collected),
            latency_ms=latency_ms,
        )

    return StreamingResponse(
        token_generator(),
        media_type="text/plain; charset=utf-8",
    )


# =========================
# Startup warm-up
# =========================

@app.on_event("startup")
def warm_up_model():
    """Preload the model into memory so the first real request is fast."""
    try:
        start = time.perf_counter()
        client.chat.completions.create(
            model=OLLAMA_MODEL,
            messages=[{"role": "user", "content": "سلام"}],
            max_tokens=1,
            extra_body={"keep_alive": KEEP_ALIVE},
        )
        elapsed = (time.perf_counter() - start) * 1000
        app_logger.info(
            "model_warmup_done model=%s elapsed=%.0fms",
            OLLAMA_MODEL,
            elapsed,
            extra={"payload": {
                "event": "model_warmup",
                "model": OLLAMA_MODEL,
                "elapsed_ms": round(elapsed, 2),
            }},
        )
    except Exception as exc:
        app_logger.error(
            "model_warmup_failed model=%s error=%s",
            OLLAMA_MODEL,
            exc,
            extra={"payload": {
                "event": "model_warmup_failed",
                "model": OLLAMA_MODEL,
                "error": str(exc),
            }},
        )
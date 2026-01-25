import os
import logging
from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi_clerk_auth import ClerkConfig, ClerkHTTPBearer, HTTPAuthorizationCredentials
from openai import AsyncOpenAI
from typing import Optional

# Import models and agents
from .agent.models import Visit, SendEmailRequest, Base64File, ChatRequest
from .agent import summary_agent, email_agent, chat_agent, memory_agent
from .agent.utils import get_logger

# Initialize Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    force=True
)
# Silence noisy libraries
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

logger = get_logger("api")

app = FastAPI()

# Add CORS middleware (allows frontend to call backend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

clerk_config = ClerkConfig(jwks_url=os.getenv("CLERK_JWKS_URL"))
clerk_guard = ClerkHTTPBearer(clerk_config)

# Initialize AsyncOpenAI client
# Note: In a production app, you might want to create this per request or as a dependency
# to handle different API keys if needed, but here we use env var.
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

@app.post("/api/consultation")
async def consultation_summary(
    visit: Visit,
    creds: HTTPAuthorizationCredentials = Depends(clerk_guard),
):
    user_id = creds.decoded["sub"]  # Available for tracking/auditing

    # Summary Pipeline
    stream_generator = summary_agent.run_summary_pipeline(visit, client)

    return StreamingResponse(stream_generator, media_type="text/event-stream")


@app.post("/api/chat")
async def chat_endpoint(
    request: ChatRequest,
    creds: HTTPAuthorizationCredentials = Depends(clerk_guard),
):
    stream_generator = chat_agent.run_chat_agent(
        history=request.messages,
        patient_name=request.patient_name or "",
        current_summary=request.current_summary or "",
        client=client
    )
    return StreamingResponse(stream_generator, media_type="text/event-stream")


@app.post("/api/send-email")
async def send_email_endpoint(
    payload: SendEmailRequest,
    creds: HTTPAuthorizationCredentials = Depends(clerk_guard),
):
    # Email Agent
    return await email_agent.run_email_agent(payload, client)


@app.get("/api/patients")
async def get_patients(creds: HTTPAuthorizationCredentials = Depends(clerk_guard)):
    """Returns a list of all unique patient names in the memory store."""
    return memory_agent.list_known_patients()


@app.get("/health")
def health_check():
    """Health check endpoint for AWS App Runner"""
    return {"status": "healthy"}

# Serve static files (our Next.js export) - MUST BE LAST!
static_path = Path("static")
if static_path.exists():
    # Serve index.html for the root path
    @app.get("/")
    async def serve_root():
        return FileResponse(static_path / "index.html")
    
    # Mount static files for all other routes
    app.mount("/", StaticFiles(directory="static", html=True), name="static")

import os
import json
import logging
import jwt
import datetime
from jwt import PyJWKClient
from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi_clerk_auth import ClerkConfig, ClerkHTTPBearer, HTTPAuthorizationCredentials
from openai import AsyncOpenAI
from typing import Optional
from clerk_backend_api import Clerk
import hashlib

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

class _AccessLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        return "/api/subscription" not in message

logging.getLogger("uvicorn.access").addFilter(_AccessLogFilter())

app = FastAPI()

# Add CORS middleware (allows frontend to call backend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Clerk authentication setup
jwks_url = os.getenv("CLERK_JWKS_URL")
if not jwks_url:
    logger.error("CLERK_JWKS_URL is not set in environment variables!")
else:
    logger.info(f"CLERK_JWKS_URL found: {jwks_url.split('/')[0]}... (masked)")

# Initialize PyJWKClient for manual verification
jwks_client = PyJWKClient(jwks_url) if jwks_url else None
clerk_config = ClerkConfig(jwks_url=jwks_url)

class CustomClerkHTTPBearer(ClerkHTTPBearer):
    async def __call__(self, request: Request):
        auth = request.headers.get("Authorization")
        if not auth or not auth.startswith("Bearer "):
            # Fallback to default behavior (which usually raises 403)
            # or just raise explicitly
            raise HTTPException(status_code=403, detail="Not authenticated")

        token = auth.split(" ")[1]
        
        try:
            if not jwks_client:
                raise Exception("JWKS client not initialized")

            signing_key = jwks_client.get_signing_key_from_jwt(token)
            
            # Manual verification with leeway and relaxed audience check
            data = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                leeway=120,
                options={"verify_aud": False} # Relax audience check
            )
            
            # Create the credentials object expected by the endpoint
            creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
            creds.decoded = data # Attach decoded payload manually
            return creds

        except Exception as e:
            logger.error(f"Manual Token Verification Failed: {e}")
            # Try to debug log the token content if possible
            try:
                decoded_debug = jwt.decode(token, options={"verify_signature": False})
                exp_ts = decoded_debug.get("exp", 0)
                iat_ts = decoded_debug.get("iat", 0)
                now_ts = datetime.datetime.now(datetime.timezone.utc).timestamp()
                logger.info(f"Debug Token: exp={exp_ts}, iat={iat_ts}, now={now_ts}, skew={iat_ts - now_ts:.2f}s")
            except:
                pass
            
            raise HTTPException(status_code=403, detail=f"Token verification failed: {str(e)}")

clerk_guard = CustomClerkHTTPBearer(clerk_config)

# Initialize AsyncOpenAI client
# Note: In a production app, you might want to create this per request or as a dependency
# to handle different API keys if needed, but here we use env var.
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

@app.post("/api/consultation")
async def consultation_summary(
    visit: Visit,
    request: Request,
    creds: HTTPAuthorizationCredentials = Depends(clerk_guard),
):
    user_id = creds.decoded["sub"]  # Available for tracking/auditing

    # Summary Pipeline
    stream_generator = summary_agent.run_summary_pipeline_resumable(visit, client, request)

    return StreamingResponse(
        stream_generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
)


@app.get("/api/consultation")
async def consultation_stream(
    job_id: str,
    request: Request,
    creds: HTTPAuthorizationCredentials = Depends(clerk_guard),
):
    job = await summary_agent.get_summary_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Summary job not found.")

    async def _stream():
        yield f"event: job\ndata: {json.dumps({'job_id': job_id})}\n\n"
        async for chunk in summary_agent.stream_summary_job(job_id, request=request):
            yield chunk

    return StreamingResponse(_stream(), media_type="text/event-stream")


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
    return StreamingResponse(
        stream_generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


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

@app.get("/api/subscription")
async def subscription(creds= Depends(clerk_guard)):
    decoded = getattr(creds, "decoded", {}) or {}
    user_id = decoded.get("user_id", '')
    print(f"Decoded: {decoded}")

    if not user_id:
        decoded["plan"] = "free_trial"
        return decoded

    with Clerk(
        bearer_auth=os.getenv('CLERK_SECRET_KEY'),
    ) as clerk:

        res = clerk.users.get_billing_subscription(user_id=user_id).json()
        if isinstance(res, str):
            res = json.loads(res)
            plan = res["subscription_items"][0]["plan"]["name"]
            print(plan)
            decoded["plan"] = plan.lower().replace(" ", "_")
        else:
            decoded["plan"] = "free_trial"


    return decoded


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

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
from dotenv import load_dotenv
from typing import Optional, List, Dict
import json
import uuid
from datetime import datetime
import boto3
from botocore.exceptions import ClientError
from openai import OpenAI
from context import prompt

# Load environment variables
load_dotenv()

app = FastAPI()

# Configure CORS
origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# Initialize Bedrock client
bedrock_client = boto3.client(
    service_name="bedrock-runtime", 
    region_name=os.getenv("DEFAULT_AWS_REGION", "us-east-1")
)

# Bedrock model selection
# Available models:
# - amazon.nova-micro-v1:0  (fastest, cheapest)
# - amazon.nova-lite-v1:0   (balanced - default)
# - amazon.nova-pro-v1:0    (most capable, higher cost)
# Remember the Heads up: you might need to add us. or eu. prefix to the below model id
BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")

# AI provider selection
AI_PROVIDER = os.getenv("AI_PROVIDER", "bedrock").strip().lower()

# Grok model configuration
GROK_MODEL_ID = os.getenv("GROK_MODEL_ID", "grok-4-1-fast")
GROK_API_URL = os.getenv("GROK_API_URL", "https://api.x.ai/v1")
GROK_API_KEY = os.getenv("GROK_API_KEY", "").strip()
grok_client = OpenAI(api_key=GROK_API_KEY, base_url=GROK_API_URL) if GROK_API_KEY else None

# Memory storage configuration
USE_S3 = os.getenv("USE_S3", "false").lower() == "true"
S3_BUCKET = os.getenv("S3_BUCKET", "")
MEMORY_DIR = os.getenv("MEMORY_DIR", "../memory")

# Initialize S3 client if needed
if USE_S3:
    s3_client = boto3.client("s3")


# Request/Response models
class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    session_id: str


class Message(BaseModel):
    role: str
    content: str
    timestamp: str


# Memory management functions
def get_memory_path(session_id: str) -> str:
    return f"{session_id}.json"


def load_conversation(session_id: str) -> List[Dict]:
    """Load conversation history from storage"""
    if USE_S3:
        try:
            response = s3_client.get_object(Bucket=S3_BUCKET, Key=get_memory_path(session_id))
            return json.loads(response["Body"].read().decode("utf-8"))
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                return []
            raise
    else:
        # Local file storage
        file_path = os.path.join(MEMORY_DIR, get_memory_path(session_id))
        if os.path.exists(file_path):
            with open(file_path, "r") as f:
                return json.load(f)
        return []


def save_conversation(session_id: str, messages: List[Dict]):
    """Save conversation history to storage"""
    if USE_S3:
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=get_memory_path(session_id),
            Body=json.dumps(messages, indent=2),
            ContentType="application/json",
        )
    else:
        # Local file storage
        os.makedirs(MEMORY_DIR, exist_ok=True)
        file_path = os.path.join(MEMORY_DIR, get_memory_path(session_id))
        with open(file_path, "w") as f:
            json.dump(messages, f, indent=2)


def build_turns(conversation: List[Dict], user_message: str) -> List[Dict[str, str]]:
    user_text = str(user_message).strip()
    if not user_text:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    turns: List[Dict[str, str]] = []
    for msg in conversation[-20:]:
        role = msg.get("role") if isinstance(msg, dict) else None
        if role not in {"user", "assistant"}:
            continue

        text = str(msg.get("content", "")).strip()
        if not text:
            continue

        if turns and turns[-1]["role"] == role:
            turns[-1]["content"] += f"\n\n{text}"
        else:
            turns.append({"role": role, "content": text})

    if turns and turns[-1]["role"] == "user":
        turns[-1]["content"] += f"\n\n{user_text}"
    else:
        turns.append({"role": "user", "content": user_text})

    return turns


def call_bedrock(conversation: List[Dict], user_message: str) -> str:
    """Call AWS Bedrock with conversation history"""
    turns = build_turns(conversation, user_message)
    messages = [{"role": t["role"], "content": [{"text": t["content"]}]} for t in turns]

    def model_candidates(model_id: str) -> List[str]:
        model_id = model_id.strip()
        if not model_id:
            return []

        candidates = [model_id]

        # Try cross-region inference profile IDs if caller provided a base model ID.
        if "." not in model_id.split("/")[0]:
            region = os.getenv("DEFAULT_AWS_REGION", "us-east-1")
            if region.startswith("us-"):
                prefixes = ["us", "eu", "apac"]
            elif region.startswith("eu-"):
                prefixes = ["eu", "us", "apac"]
            else:
                prefixes = ["apac", "us", "eu"]
            candidates.extend([f"{prefix}.{model_id}" for prefix in prefixes])

        # Preserve order and uniqueness.
        return list(dict.fromkeys(candidates))

    candidates = model_candidates(BEDROCK_MODEL_ID)
    if not candidates:
        raise HTTPException(status_code=500, detail="BEDROCK_MODEL_ID is not configured")

    for model_id in candidates:
        try:
            response = bedrock_client.converse(
                modelId=model_id,
                system=[{"text": prompt()}],
                messages=messages,
                inferenceConfig={
                    "maxTokens": 2000,
                    "temperature": 0.7,
                    "topP": 0.9
                }
            )
            return response["output"]["message"]["content"][0]["text"]
        except ClientError as e:
            error = e.response.get("Error", {})
            error_code = error.get("Code", "")
            error_message = error.get("Message", str(e))

            if error_code == "ValidationException":
                # Retry with alternate model IDs when Bedrock blocks this ID.
                if "operation not allowed" in error_message.lower():
                    print(f"Bedrock rejected modelId '{model_id}': {error_message}")
                    continue
                print(f"Bedrock validation error for '{model_id}': {error_message}")
                raise HTTPException(status_code=400, detail=f"Bedrock validation error: {error_message}")

            if error_code == "AccessDeniedException":
                print(f"Bedrock access denied for '{model_id}': {error_message}")
                raise HTTPException(status_code=403, detail=f"Access denied to Bedrock model: {error_message}")

            print(f"Bedrock error for '{model_id}': {error_message}")
            raise HTTPException(status_code=500, detail=f"Bedrock error: {error_message}")

    raise HTTPException(
        status_code=400,
        detail=(
            "Bedrock returned 'Operation not allowed' for all model IDs tried: "
            f"{', '.join(candidates)}. "
            "Enable model access for the selected model in this region or set BEDROCK_MODEL_ID "
            "to an allowed model/inference-profile ID."
        ),
    )


def call_grok(conversation: List[Dict], user_message: str) -> str:
    """Call xAI Grok with conversation history"""
    if not grok_client:
        raise HTTPException(status_code=500, detail="GROK_API_KEY is not configured")

    turns = build_turns(conversation, user_message)
    messages = [{"role": "system", "content": prompt()}] + turns

    try:
        response = grok_client.chat.completions.create(
            model=GROK_MODEL_ID,
            messages=messages,
            temperature=0.7,
            max_tokens=2000,
        )
        content = response.choices[0].message.content
        if isinstance(content, str) and content.strip():
            return content
        raise HTTPException(status_code=502, detail="Empty response from Grok")
    except HTTPException:
        raise
    except Exception as e:
        print(f"Grok error: {e}")
        raise HTTPException(status_code=500, detail=f"Grok error: {str(e)}")


@app.get("/")
async def root():
    active_model = GROK_MODEL_ID if AI_PROVIDER == "grok" else BEDROCK_MODEL_ID
    return {
        "message": "AI Digital Twin API",
        "memory_enabled": True,
        "storage": "S3" if USE_S3 else "local",
        "ai_provider": AI_PROVIDER,
        "ai_model": active_model
    }


@app.get("/health")
async def health_check():
    active_model = GROK_MODEL_ID if AI_PROVIDER == "grok" else BEDROCK_MODEL_ID
    return {
        "status": "healthy", 
        "use_s3": USE_S3,
        "ai_provider": AI_PROVIDER,
        "ai_model": active_model
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        # Generate session ID if not provided
        session_id = request.session_id or str(uuid.uuid4())

        # Load conversation history
        conversation = load_conversation(session_id)

        # Call selected AI provider
        if AI_PROVIDER == "grok":
            assistant_response = call_grok(conversation, request.message)
        elif AI_PROVIDER == "bedrock":
            assistant_response = call_bedrock(conversation, request.message)
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Unsupported AI_PROVIDER '{AI_PROVIDER}'. Use 'bedrock' or 'grok'.",
            )

        # Update conversation history
        conversation.append(
            {"role": "user", "content": request.message, "timestamp": datetime.now().isoformat()}
        )
        conversation.append(
            {
                "role": "assistant",
                "content": assistant_response,
                "timestamp": datetime.now().isoformat(),
            }
        )

        # Save conversation
        save_conversation(session_id, conversation)

        return ChatResponse(response=assistant_response, session_id=session_id)

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in chat endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/conversation/{session_id}")
async def get_conversation(session_id: str):
    """Retrieve conversation history"""
    try:
        conversation = load_conversation(session_id)
        return {"session_id": session_id, "messages": conversation}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)

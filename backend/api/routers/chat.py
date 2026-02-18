from fastapi import APIRouter, Query

from api.schemas import ChatRequest

router = APIRouter()


@router.get("/quota")
async def get_quota(user_id: str = Query(...)):
    from server import get_quota as get_quota_handler

    return await get_quota_handler(user_id=user_id)


@router.post("/chat")
async def chat(request: ChatRequest):
    from server import chat as chat_handler

    return await chat_handler(request)


@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str, user_id: str = Query(...)):
    from server import get_job_status as get_job_status_handler

    return await get_job_status_handler(job_id=job_id, user_id=user_id)


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str, user_id: str = Query(...)):
    from server import cancel_job as cancel_job_handler

    return await cancel_job_handler(job_id=job_id, user_id=user_id)


@router.get("/conversation/{session_id}")
async def get_conversation(session_id: str, user_id: str = Query(...)):
    from server import get_conversation as get_conversation_handler

    return await get_conversation_handler(session_id=session_id, user_id=user_id)


@router.get("/conversations")
async def get_conversations(user_id: str = Query(...), limit: int = Query(5, ge=1, le=50)):
    from server import get_conversations as get_conversations_handler

    return await get_conversations_handler(user_id=user_id, limit=limit)

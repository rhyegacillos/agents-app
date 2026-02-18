from fastapi import APIRouter, Query

router = APIRouter()


@router.get("/memory/candidates")
async def get_memory_candidates(user_id: str = Query(...)):
    from server import get_memory_candidates as handler

    return await handler(user_id=user_id)


@router.get("/memory")
async def get_memory(user_id: str = Query(...)):
    from server import get_memory as handler

    return await handler(user_id=user_id)


@router.post("/memory/candidates/{candidate_id}/approve")
async def approve_memory_candidate(candidate_id: str, user_id: str = Query(...)):
    from server import approve_memory_candidate as handler

    return await handler(candidate_id=candidate_id, user_id=user_id)


@router.post("/memory/candidates/{candidate_id}/reject")
async def reject_memory_candidate(candidate_id: str, user_id: str = Query(...)):
    from server import reject_memory_candidate as handler

    return await handler(candidate_id=candidate_id, user_id=user_id)


@router.post("/memory/candidates/clear")
async def clear_memory_candidates(user_id: str = Query(...)):
    from server import clear_memory_candidates as handler

    return await handler(user_id=user_id)


@router.post("/memory/approved/{memory_id}/delete")
async def delete_approved_memory(memory_id: str, user_id: str = Query(...)):
    from server import delete_approved_memory as handler

    return await handler(memory_id=memory_id, user_id=user_id)

from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def root():
    from server import root as root_handler

    return await root_handler()


@router.get("/health")
async def health_check():
    from server import health_check as health_handler

    return await health_handler()

from fastapi import APIRouter, File, UploadFile

from api.schemas import UploadPresignRequest

router = APIRouter()


@router.get("/downloads/{filename}")
async def download_file(filename: str):
    from server import download_file as handler

    return await handler(filename=filename)


@router.post("/uploads")
async def upload_file(file: UploadFile = File(...)):
    from server import upload_file as handler

    return await handler(file=file)


@router.post("/uploads/presign")
async def presign_upload(req: UploadPresignRequest):
    from server import presign_upload as handler

    return await handler(req)

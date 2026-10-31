from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse

from app.api.v1.schemas.order_schemas import ComplaintIn
from app.core import ratelimit
from app.core.deps import current_user
from app.core.exceptions import AppError
from app.services import complaint_service as svc, storage_service

router = APIRouter(prefix="/complaints", tags=["complaints"])


@router.post("", status_code=201)
async def create(body: ComplaintIn, user: dict = Depends(current_user)):
    return await svc.create(user["_id"], body.category, body.description, body.order_id)


@router.get("")
async def mine(user: dict = Depends(current_user)):
    return await svc.list_for_user(user["_id"])


@router.get("/{cid}")
async def one(cid: str, user: dict = Depends(current_user)):
    return await svc.get(cid, user["_id"])


@router.post("/attachments", status_code=201)
async def upload(file: UploadFile = File(...), user: dict = Depends(current_user)):
    ratelimit.check(f"upload:{user['_id']}", 6)
    data = await file.read(storage_service.MAX_BYTES + 1)
    return await storage_service.save_image(user["_id"], data)


@router.get("/attachments/{att_id}/file")
async def attachment_file(att_id: str, user: dict = Depends(current_user)):
    att = await storage_service.get_attachment(att_id, None if user["role"] == "admin" else user["_id"])
    if att["backend"] != "local":
        raise AppError("This image is hosted externally.", status_code=404)
    return FileResponse(storage_service.local_path(att_id), media_type="image/jpeg",
                        headers={"Cache-Control": "private, max-age=3600"})

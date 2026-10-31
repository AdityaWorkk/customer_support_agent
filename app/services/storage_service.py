"""Image uploads for defect reports. Validates by actually decoding the image, strips
EXIF/GPS by re-encoding, and stores on Cloudinary (persistent) or local disk (dev only:
Render's free disk is wiped on every deploy and spin-down)."""
import hashlib
import io
import time
from pathlib import Path

import httpx
from PIL import Image, UnidentifiedImageError

from app.core.config import settings
from app.core.database import db
from app.core.deps import now
from app.core.exceptions import AppError, NotFoundError
from app.core.security import random_id

MAX_BYTES = 5 * 1024 * 1024
ALLOWED = {"JPEG", "PNG", "WEBP"}
LOCAL_DIR = Path("uploads")


def _clean(data: bytes) -> bytes:
    if len(data) > MAX_BYTES:
        raise AppError("Image is larger than 5 MB.", code="file_too_large", status_code=413)
    try:
        img = Image.open(io.BytesIO(data))
        if img.format not in ALLOWED:
            raise AppError("Only JPEG, PNG or WebP images are accepted.", code="bad_image")
        img.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise AppError("That file isn't a valid image.", code="bad_image")
    img = img.convert("RGB")
    img.thumbnail((2000, 2000))
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=85)  # re-encode drops EXIF and embedded payloads
    return out.getvalue()


async def save_image(user_id: str, data: bytes) -> dict:
    jpeg = _clean(data)
    att_id = random_id("att_")
    if settings.STORAGE_BACKEND == "cloudinary":
        url = await _cloudinary(jpeg, att_id)
    else:
        LOCAL_DIR.mkdir(exist_ok=True)
        (LOCAL_DIR / f"{att_id}.jpg").write_bytes(jpeg)
        url = f"/api/v1/complaints/attachments/{att_id}/file"
    doc = {"_id": att_id, "user_id": user_id, "url": url, "backend": settings.STORAGE_BACKEND,
           "size": len(jpeg), "created_at": now()}
    await db().attachments.insert_one(doc)
    return {"id": att_id, "url": url}


async def _cloudinary(jpeg: bytes, att_id: str) -> str:
    ts = str(int(time.time()))
    to_sign = f"folder=support&public_id={att_id}&timestamp={ts}{settings.CLOUDINARY_API_SECRET}"
    sig = hashlib.sha1(to_sign.encode()).hexdigest()
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(f"https://api.cloudinary.com/v1_1/{settings.CLOUDINARY_CLOUD_NAME}/image/upload",
                         data={"api_key": settings.CLOUDINARY_API_KEY, "timestamp": ts, "folder": "support",
                               "public_id": att_id, "signature": sig},
                         files={"file": ("image.jpg", jpeg, "image/jpeg")})
    if r.status_code != 200:
        raise AppError("Image storage is unavailable. Try again shortly.", code="storage_error", status_code=502)
    return r.json()["secure_url"]


async def get_attachment(att_id: str, user_id: str | None = None) -> dict:
    q = {"_id": att_id}
    if user_id:
        q["user_id"] = user_id
    doc = await db().attachments.find_one(q)
    if not doc:
        raise NotFoundError("Attachment not found.")
    return doc


def local_path(att_id: str) -> Path:
    return LOCAL_DIR / f"{att_id}.jpg"

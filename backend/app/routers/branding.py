"""Company branding — the optional logo shown across the web UI in place of
the built-in Chronos mark. Set once at install via BRANDING_LOGO_PATH; served
publicly (the login screen needs it before anyone authenticates) and never
gated by the password-change or licence middlewares."""
import mimetypes
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from app.config import settings

router = APIRouter(tags=["branding"])


@router.get("/branding/logo")
def get_branding_logo():
    path_str = settings.branding_logo_path
    if not path_str:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No company logo configured")
    path = Path(path_str)
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company logo file not found")
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    # no-store: the client can drop a new logo at the same path at any time.
    return FileResponse(path, media_type=media_type, headers={"Cache-Control": "no-store"})

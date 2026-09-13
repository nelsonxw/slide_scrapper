"""
Slide Management & Firebase Storage API Routes.
Provides endpoints for listing stored slide cards, previewing slides, and batch deleting slides from Firebase Storage.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.config import settings
from app.firebase.storage import FirebaseStorageService, StoredSlideCard

router = APIRouter(prefix="/api/slides", tags=["Slides"])


class DeleteSlidesRequest(BaseModel):
    slide_ids: list[str] = Field(..., description="List of slide IDs / storage paths to delete")


class DeleteSlidesResponse(BaseModel):
    deleted_count: int
    success: bool
    errors: list[str] = []


@router.get("", response_model=list[dict[str, Any]])
def list_slides(search: str | None = None):
    """
    Retrieves all individual slide files stored in Firebase Storage.
    """
    storage = FirebaseStorageService.get_instance()
    cards = storage.list_slides()

    if search:
        s_lower = search.lower()
        cards = [
            c for c in cards
            if s_lower in c.title.lower()
            or s_lower in c.original_presentation_name.lower()
            or s_lower in c.slide_filename.lower()
        ]

    return [
        {
            "id": c.id,
            "slide_filename": c.slide_filename,
            "preview_filename": c.preview_filename,
            "storage_pptx_path": c.storage_pptx_path,
            "storage_preview_path": c.storage_preview_path,
            "pptx_url": c.pptx_url,
            "preview_url": c.preview_url,
            "title": c.title,
            "original_presentation_name": c.original_presentation_name,
            "original_source_url": c.original_source_url,
            "slide_index": c.slide_index,
            "total_slides": c.total_slides,
            "file_size": c.file_size,
            "uploaded_at": c.uploaded_at,
        }
        for c in cards
    ]


@router.delete("", response_model=DeleteSlidesResponse)
def delete_slides(request: DeleteSlidesRequest):
    """
    Deletes the selected slide files from Firebase Storage.
    """
    if not request.slide_ids:
        return DeleteSlidesResponse(deleted_count=0, success=True, errors=[])

    storage = FirebaseStorageService.get_instance()
    res = storage.delete_slides(request.slide_ids)
    return DeleteSlidesResponse(**res)


@router.get("/storage-status")
def get_storage_status():
    """
    Returns Firebase Storage connection and configuration status.
    """
    storage = FirebaseStorageService.get_instance()
    return storage.get_status()


@router.get("/download/local/{filename}")
def download_local_slide(filename: str):
    """
    Serves local PPTX file when running in local fallback mode.
    """
    file_path = settings.data_dir / "split_slides" / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Slide file not found")
    return FileResponse(
        str(file_path),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        filename=filename,
    )


@router.get("/preview/local/{filename}")
def preview_local_slide(filename: str):
    """
    Serves local preview PNG image.
    """
    file_path = settings.data_dir / "previews" / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Preview image not found")
    return FileResponse(
        str(file_path),
        media_type="image/png",
    )

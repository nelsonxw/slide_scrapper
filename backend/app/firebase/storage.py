"""
Firebase Storage Manager for gs://slide-preview.firebasestorage.app.
Handles authentication, uploading individual slide PPTX files and preview images,
listing stored slides, and deleting selected files from Firebase Storage.
"""
from __future__ import annotations

import datetime
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import firebase_admin
from firebase_admin import credentials, storage
from google.cloud.storage.blob import Blob
import urllib3

from app.config import settings


FIREBASE_UPLOAD_TIMEOUT_SECONDS = 60


@dataclass
class StoredSlideCard:
    id: str
    slide_filename: str
    preview_filename: str
    storage_pptx_path: str
    storage_preview_path: str
    pptx_url: str
    preview_url: str
    title: str
    original_presentation_name: str
    original_source_url: str
    slide_index: int
    total_slides: int
    file_size: int
    uploaded_at: str


class FirebaseStorageService:
    _instance: FirebaseStorageService | None = None

    def __init__(self):
        self.bucket_name = settings.storage_bucket.replace("gs://", "").strip("/")
        self.app: firebase_admin.App | None = None
        self.bucket: Any = None
        self.is_connected = False
        self.connection_error: str | None = None
        self._init_firebase()

    @classmethod
    def get_instance(cls) -> FirebaseStorageService:
        if cls._instance is None:
            cls._instance = FirebaseStorageService()
        return cls._instance

    def _init_firebase(self):
        try:
            cred_path = settings.resolve_credentials_path()
            if cred_path:
                cred = credentials.Certificate(str(cred_path))
            else:
                # Try application default or unauthenticated/mock fallback
                try:
                    cred = credentials.ApplicationDefault()
                except Exception:
                    cred = None

            if not firebase_admin._apps:
                if cred:
                    self.app = firebase_admin.initialize_app(
                        cred,
                        {"storageBucket": self.bucket_name},
                    )
                else:
                    self.app = firebase_admin.initialize_app(
                        options={"storageBucket": self.bucket_name}
                    )
            else:
                self.app = firebase_admin.get_app()

            self.bucket = storage.bucket(self.bucket_name, app=self.app)
            self._configure_client_ssl()
            self.is_connected = True
            self.connection_error = None
        except Exception as e:
            self.is_connected = False
            self.connection_error = str(e)
            print(f"Warning: Firebase Storage init notice ({self.bucket_name}): {e}")

    def _configure_client_ssl(self):
        """Configures SSL verification on the Google Cloud Storage client sessions."""
        if not self.bucket or not hasattr(self.bucket, 'client'):
            return

        client = self.bucket.client
        verify_value = settings.firebase_ca_bundle if settings.firebase_ca_bundle else settings.firebase_verify_ssl

        if not settings.firebase_verify_ssl:
            urllib3.disable_warnings()

        if hasattr(client, '_http') and client._http:
            client._http.verify = verify_value

        if hasattr(client, '_connection') and hasattr(client._connection, 'http') and client._connection.http:
            client._connection.http.verify = verify_value

    def get_status(self) -> dict[str, Any]:
        return {
            "bucket_name": self.bucket_name,
            "is_connected": self.is_connected,
            "credentials_found": bool(settings.resolve_credentials_path()),
            "credentials_path": str(settings.resolve_credentials_path() or settings.credentials_path),
            "firebase_verify_ssl": settings.firebase_verify_ssl,
            "firebase_ca_bundle": settings.firebase_ca_bundle,
            "error": self.connection_error,
        }

    def upload_slide_file(
        self,
        local_pptx_path: Path | str,
        local_preview_path: Path | str,
        original_source_url: str,
        original_presentation_name: str,
        slide_title: str,
        slide_index: int,
        total_slides: int,
    ) -> StoredSlideCard:
        """
        Uploads an individual slide PPTX file and its preview image to Firebase Storage.
        """
        local_pptx = Path(local_pptx_path).resolve()
        local_preview = Path(local_preview_path).resolve()

        slide_filename = local_pptx.name
        preview_filename = local_preview.name

        storage_pptx_path = f"slides/{slide_filename}"
        storage_preview_path = f"previews/{preview_filename}"
        timestamp_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        metadata = {
            "title": slide_title,
            "original_presentation_name": original_presentation_name,
            "original_source_url": original_source_url,
            "slide_index": str(slide_index),
            "total_slides": str(total_slides),
            "uploaded_at": timestamp_iso,
        }

        if self.is_connected and self.bucket:
            # Upload PPTX blob
            pptx_blob = self.bucket.blob(storage_pptx_path)
            pptx_blob.metadata = metadata
            pptx_blob.upload_from_filename(
                str(local_pptx),
                content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                timeout=FIREBASE_UPLOAD_TIMEOUT_SECONDS,
            )
            try:
                pptx_blob.make_public()
            except Exception:
                pass

            # Upload Preview PNG blob
            preview_blob = self.bucket.blob(storage_preview_path)
            preview_blob.metadata = metadata
            preview_blob.upload_from_filename(
                str(local_preview),
                content_type="image/png",
                timeout=FIREBASE_UPLOAD_TIMEOUT_SECONDS,
            )
            try:
                preview_blob.make_public()
            except Exception:
                pass

            pptx_url = self._get_blob_url(pptx_blob, storage_pptx_path)
            preview_url = self._get_blob_url(preview_blob, storage_preview_path)
            if preview_blob.size is None or preview_blob.size == 0:
                preview_url = f"/api/slides/preview/local/{preview_filename}"
        else:
            # Local fallback mode when Firebase credentials are not yet configured
            pptx_url = f"/api/slides/download/local/{slide_filename}"
            preview_url = f"/api/slides/preview/local/{preview_filename}"

        card = StoredSlideCard(
            id=storage_pptx_path,
            slide_filename=slide_filename,
            preview_filename=preview_filename,
            storage_pptx_path=storage_pptx_path,
            storage_preview_path=storage_preview_path,
            pptx_url=pptx_url,
            preview_url=preview_url,
            title=slide_title,
            original_presentation_name=original_presentation_name,
            original_source_url=original_source_url,
            slide_index=slide_index,
            total_slides=total_slides,
            file_size=local_pptx.stat().st_size if local_pptx.exists() else 0,
            uploaded_at=timestamp_iso,
        )

        # Save card index locally for fast retrieval & offline sync
        self._save_local_card_index(card)
        return card

    def list_slides(self) -> list[StoredSlideCard]:
        """
        Lists all slide records from Firebase Storage and local registry.
        """
        slides_map: dict[str, StoredSlideCard] = {}

        # 1. Read from local storage index
        local_cards = self._read_local_card_index()
        for c in local_cards:
            slides_map[c.storage_pptx_path] = c

        # 2. Sync from Firebase Storage if connected
        if self.is_connected and self.bucket:
            try:
                blobs: Iterable[Blob] = self.bucket.list_blobs(prefix="slides/")
                for blob in blobs:
                    if not blob.name.endswith(".pptx"):
                        continue
                    storage_path = blob.name
                    filename = storage_path.split("/")[-1]
                    preview_path = f"previews/{filename.replace('.pptx', '.png')}"
                    
                    meta = blob.metadata or {}
                    preview_blob = self.bucket.blob(preview_path)

                    pptx_url = self._get_blob_url(blob, storage_path)
                    preview_url = self._get_blob_url(preview_blob, preview_path)
                    if preview_blob.size is None or preview_blob.size == 0:
                        preview_url = f"/api/slides/preview/local/{filename.replace('.pptx', '.png')}"

                    slide_idx = int(meta.get("slide_index", 0)) if meta.get("slide_index") else 0
                    tot_slides = int(meta.get("total_slides", 1)) if meta.get("total_slides") else 1

                    card = StoredSlideCard(
                        id=storage_path,
                        slide_filename=filename,
                        preview_filename=filename.replace(".pptx", ".png"),
                        storage_pptx_path=storage_path,
                        storage_preview_path=preview_path,
                        pptx_url=pptx_url,
                        preview_url=preview_url,
                        title=meta.get("title", filename.replace(".pptx", "").replace("_", " ").title()),
                        original_presentation_name=meta.get("original_presentation_name", "Presentation"),
                        original_source_url=meta.get("original_source_url", ""),
                        slide_index=slide_idx,
                        total_slides=tot_slides,
                        file_size=blob.size or 0,
                        uploaded_at=meta.get("uploaded_at", blob.time_created.isoformat() if blob.time_created else ""),
                    )
                    slides_map[storage_path] = card
            except Exception as e:
                print(f"Error querying Firebase Storage: {e}")

        # Return sorted by upload date descending
        result = list(slides_map.values())
        result.sort(key=lambda s: s.uploaded_at or "", reverse=True)
        return result

    def delete_slides(self, slide_ids: list[str]) -> dict[str, Any]:
        """
        Deletes selected slide PPTX files and their preview images from Firebase Storage and local index.
        """
        deleted_count = 0
        errors: list[str] = []

        local_cards = self._read_local_card_index()
        remaining_cards = []

        for card in local_cards:
            if card.id in slide_ids or card.storage_pptx_path in slide_ids:
                # Delete from Firebase if connected
                if self.is_connected and self.bucket:
                    try:
                        pptx_blob = self.bucket.blob(card.storage_pptx_path)
                        if pptx_blob.exists():
                            pptx_blob.delete()
                    except Exception as e:
                        errors.append(f"Failed deleting {card.storage_pptx_path}: {e}")

                    try:
                        preview_blob = self.bucket.blob(card.storage_preview_path)
                        if preview_blob.exists():
                            preview_blob.delete()
                    except Exception as e:
                        pass

                # Delete local files if they exist
                local_pptx = settings.data_dir / "slides" / card.slide_filename
                if local_pptx.exists():
                    local_pptx.unlink(missing_ok=True)
                local_preview = settings.data_dir / "previews" / card.preview_filename
                if local_preview.exists():
                    local_preview.unlink(missing_ok=True)

                deleted_count += 1
            else:
                remaining_cards.append(card)

        # If connected, also check for any storage paths passed that were not in local index
        if self.is_connected and self.bucket:
            for sid in slide_ids:
                if sid.startswith("slides/"):
                    try:
                        b = self.bucket.blob(sid)
                        if b.exists():
                            b.delete()
                            deleted_count += 1
                        prev_b = self.bucket.blob(sid.replace("slides/", "previews/").replace(".pptx", ".png"))
                        if prev_b.exists():
                            prev_b.delete()
                    except Exception as e:
                        errors.append(f"Delete error for {sid}: {e}")

        self._write_local_card_index(remaining_cards)

        return {
            "deleted_count": deleted_count,
            "success": len(errors) == 0,
            "errors": errors,
        }

    def _get_blob_url(self, blob: Blob | None, path: str) -> str:
        """Returns an authenticated backend URL for a stored Firebase object."""
        if path.startswith("previews/"):
            return f"/api/slides/preview/storage/{path}"
        return f"/api/slides/download/storage/{path}"

    def _get_index_file(self) -> Path:
        return settings.data_dir / "slides_index.json"

    def _read_local_card_index(self) -> list[StoredSlideCard]:
        idx_file = self._get_index_file()
        if not idx_file.exists():
            return []
        try:
            cards = [StoredSlideCard(**item) for item in json.loads(idx_file.read_text(encoding="utf-8"))]
            if self.is_connected:
                for card in cards:
                    card.pptx_url = self._get_blob_url(None, card.storage_pptx_path)
                    card.preview_url = self._get_blob_url(None, card.storage_preview_path)
            return cards
        except Exception:
            return []

    def _write_local_card_index(self, cards: list[StoredSlideCard]) -> None:
        idx_file = self._get_index_file()
        try:
            raw = [asdict(c) for c in cards]
            idx_file.write_text(json.dumps(raw, indent=2), encoding="utf-8")
        except Exception as e:
            print(f"Error saving index: {e}")

    def _save_local_card_index(self, card: StoredSlideCard) -> None:
        cards = self._read_local_card_index()
        # Update or append
        updated = [c for c in cards if c.id != card.id]
        updated.insert(0, card)
        self._write_local_card_index(updated)

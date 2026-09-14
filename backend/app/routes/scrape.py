"""
Scrape API Routes and Background Task Manager.
Handles starting scrape tasks, streaming progress logs, splitting slides, and uploading to Firebase.
"""
from __future__ import annotations

import asyncio
import datetime
import threading
import uuid
from pathlib import Path
from typing import Any
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from app.config import settings
from app.firebase.storage import FirebaseStorageService, StoredSlideCard
from app.ppt.splitter import split_presentation_by_slide
from app.scraper.crawler import DiscoveredPowerPoint, SiteScraper

router = APIRouter(prefix="/api/scrape", tags=["Scraper"])


class StartScrapeRequest(BaseModel):
    url: str = Field(..., description="Target website URL to scrape")
    max_pages: int = Field(default=25, ge=1, le=100, description="Max sub-pages to crawl")
    max_depth: int = Field(default=2, ge=0, le=5, description="Max crawl depth (0 = target page only)")
    cookies: str | None = Field(default=None, description="Optional raw session cookies string")
    google_token: str | None = Field(default=None, description="Optional Google OAuth/ID token")
    user_email: str | None = Field(default=None, description="Optional signed-in user email")


class ScrapeTaskStatus(BaseModel):
    task_id: str
    target_url: str
    status: str  # "queued", "running", "completed", "failed", "cancelled"
    current_step: str
    discovered_files_count: int
    total_slides_created: int
    uploaded_slides_count: int
    logs: list[str]
    created_at: str
    updated_at: str
    error: str | None = None
    saved_slides: list[dict[str, Any]] = []


# In-memory registry of tasks
tasks: dict[str, dict[str, Any]] = {}
active_threads: dict[str, threading.Event] = {}


def _run_scrape_pipeline(
    task_id: str,
    target_url: str,
    max_pages: int,
    max_depth: int,
    stop_event: threading.Event,
    cookies: str | None = None,
    google_token: str | None = None,
    user_email: str | None = None,
):
    task = tasks[task_id]
    task["status"] = "running"
    task["current_step"] = "Initializing crawler..."
    task["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

    def log(msg: str):
        task["logs"].append(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}")
        task["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        # Keep last 200 logs
        if len(task["logs"]) > 200:
            task["logs"] = task["logs"][-200:]

    storage_service = FirebaseStorageService.get_instance()

    try:
        log(f"Starting discovery on {target_url} (depth <= {max_depth}, max_pages <= {max_pages})")
        if user_email:
            log(f"Authenticated as Google User: {user_email}")
        if cookies:
            log("Session cookies configured for authenticated requests.")
        task["current_step"] = "Crawling site & searching for download buttons..."

        scraper = SiteScraper(
            target_url=target_url,
            max_crawl_pages=max_pages,
            max_depth=max_depth,
            cookies=cookies,
            google_token=google_token,
            user_email=user_email,
        )

        discovered_ppts: list[DiscoveredPowerPoint] = []

        def on_found(item: DiscoveredPowerPoint):
            discovered_ppts.append(item)
            task["discovered_files_count"] = len(discovered_ppts)
            log(f"Found PowerPoint presentation #{len(discovered_ppts)}: '{item.title}' ({len(item.content_bytes) // 1024} KB)")

        scraper.crawl_and_extract(
            on_log=log,
            on_found=on_found,
            should_stop=lambda: stop_event.is_set(),
        )

        if stop_event.is_set():
            task["status"] = "cancelled"
            task["current_step"] = "Scraping cancelled by user."
            log("Task was cancelled.")
            return

        if not discovered_ppts:
            task["status"] = "completed"
            task["current_step"] = "Finished: No PowerPoint files found."
            log("No PowerPoint download buttons or files discovered on the target site.")
            return

        log(f"Discovery phase completed. Processing {len(discovered_ppts)} PowerPoint presentations for slide extraction...")
        task["current_step"] = "Splitting presentations by slide..."

        total_slides = 0
        uploaded_slides = 0
        saved_cards = []

        for idx, ppt in enumerate(discovered_ppts, start=1):
            if stop_event.is_set():
                break

            log(f"Processing presentation {idx}/{len(discovered_ppts)}: '{ppt.title}'...")

            # Split presentation into individual slides
            split_dir = settings.data_dir / "split_slides"
            split_dir.mkdir(parents=True, exist_ok=True)

            try:
                slide_results = split_presentation_by_slide(
                    pptx_source=ppt.content_bytes,
                    presentation_name=ppt.title,
                    output_dir=settings.data_dir,
                )
                log(f"Extracted {len(slide_results)} individual slides from '{ppt.title}'.")
                total_slides += len(slide_results)
                task["total_slides_created"] = total_slides

                # Upload each slide to Firebase Storage
                task["current_step"] = f"Uploading slides for '{ppt.title}' to Firebase Storage..."
                for slide in slide_results:
                    if stop_event.is_set():
                        break

                    log(f"Uploading slide {slide.slide_index + 1}/{slide.total_slides}: {slide.slide_filename} to Firebase Storage (gs://{settings.storage_bucket})...")
                    card = storage_service.upload_slide_file(
                        local_pptx_path=slide.pptx_file_path,
                        local_preview_path=slide.preview_image_path,
                        original_source_url=ppt.download_url,
                        original_presentation_name=ppt.title,
                        slide_title=slide.title,
                        slide_index=slide.slide_index,
                        total_slides=slide.total_slides,
                    )
                    uploaded_slides += 1
                    task["uploaded_slides_count"] = uploaded_slides
                    saved_cards.append({
                        "id": card.id,
                        "title": card.title,
                        "slide_filename": card.slide_filename,
                        "preview_url": card.preview_url,
                        "pptx_url": card.pptx_url,
                    })

            except Exception as split_err:
                log(f"Error splitting '{ppt.title}': {split_err}")

        task["saved_slides"] = saved_cards
        if stop_event.is_set():
            task["status"] = "cancelled"
            task["current_step"] = "Task cancelled by user."
            log("Task cancelled during slide processing.")
        else:
            task["status"] = "completed"
            task["current_step"] = f"Completed successfully! {uploaded_slides} slides saved to Firebase Storage."
            log(f"All processing complete! Saved {uploaded_slides} individual slide files to Firebase Storage.")

    except Exception as e:
        task["status"] = "failed"
        task["error"] = str(e)
        task["current_step"] = f"Failed with error: {e}"
        log(f"Critical error during task: {e}")
    finally:
        task["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        if task_id in active_threads:
            del active_threads[task_id]


@router.post("/start", response_model=ScrapeTaskStatus)
def start_scrape_task(request: StartScrapeRequest):
    if not request.url or not request.url.strip():
        raise HTTPException(status_code=400, detail="Target URL cannot be empty")

    task_id = str(uuid.uuid4())
    stop_event = threading.Event()
    active_threads[task_id] = stop_event

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    task_record = {
        "task_id": task_id,
        "target_url": request.url.strip(),
        "status": "queued",
        "current_step": "Task queued...",
        "discovered_files_count": 0,
        "total_slides_created": 0,
        "uploaded_slides_count": 0,
        "logs": [f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Task created for {request.url}"],
        "created_at": now,
        "updated_at": now,
        "error": None,
        "saved_slides": [],
    }
    tasks[task_id] = task_record

    # Start thread
    thread = threading.Thread(
        target=_run_scrape_pipeline,
        args=(
            task_id,
            request.url.strip(),
            request.max_pages,
            request.max_depth,
            stop_event,
            request.cookies,
            request.google_token,
            request.user_email,
        ),
        daemon=True,
    )
    thread.start()

    return ScrapeTaskStatus(**task_record)


@router.get("/status/{task_id}", response_model=ScrapeTaskStatus)
def get_scrape_task_status(task_id: str):
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    return ScrapeTaskStatus(**tasks[task_id])


@router.post("/cancel/{task_id}")
def cancel_scrape_task(task_id: str):
    if task_id in active_threads:
        active_threads[task_id].set()
        if task_id in tasks:
            tasks[task_id]["status"] = "cancelling"
            tasks[task_id]["current_step"] = "Cancelling task..."
        return {"message": "Cancellation requested"}
    if task_id in tasks:
        tasks[task_id]["status"] = "cancelled"
        return {"message": "Task marked cancelled"}
    raise HTTPException(status_code=404, detail="Task not found")


class OpenBrowserLoginRequest(BaseModel):
    url: str = Field(default="https://slidemodel.com/account/login/", description="Website URL to log in to")


@router.post("/open-browser-login")
def open_browser_login(req: OpenBrowserLoginRequest):
    """
    Opens a browser for manual login and automatically extracts cookies after login.
    Returns the extracted cookies for use in automated scraping.
    """
    import queue

    result_queue = queue.Queue()

    def _run_browser():
        from app.scraper.browser_driver import BrowserDownloader
        downloader = BrowserDownloader(headless=False)
        cookies = downloader.extract_cookies_after_login()
        result_queue.put(cookies)

    # Run in thread
    thread = threading.Thread(target=_run_browser, daemon=True)
    thread.start()

    # Wait for result with timeout
    try:
        cookies = result_queue.get(timeout=300)  # 5 minutes timeout
        return {"status": "success", "cookies": cookies, "message": "Cookies extracted successfully. They have been automatically filled in the Session Cookies field."}
    except queue.Empty:
        return {"status": "timeout", "message": "Login timeout. Please try again."}

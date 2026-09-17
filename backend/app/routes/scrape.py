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
    max_pages: int = Field(default=25, ge=1, le=1000, description="Max sub-pages to crawl")
    max_depth: int = Field(default=2, ge=0, le=5, description="Max crawl depth (0 = target page only)")


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
scrape_history_lock = threading.Lock()
scrape_history: set[str] = set()


def _normalize_scrape_url(url: str) -> str:
    return url.strip().split("#", 1)[0].rstrip("/").lower()


def _mark_scrape_history(url: str) -> None:
    with scrape_history_lock:
        scrape_history.add(_normalize_scrape_url(url))


def _was_scraped(url: str) -> bool:
    with scrape_history_lock:
        return _normalize_scrape_url(url) in scrape_history


def _run_scrape_pipeline(
    task_id: str,
    target_url: str,
    max_pages: int,
    max_depth: int,
    stop_event: threading.Event,
):
    task = tasks[task_id]
    task["status"] = "running"
    task["current_step"] = "Initializing crawler..."
    task["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

    def log(msg: str):
        task["logs"].append(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}")
        task["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        # Keep last 1000 logs
        if len(task["logs"]) > 1000:
            task["logs"] = task["logs"][-1000:]

    storage_service = FirebaseStorageService.get_instance()
    browser_session = None
    browser_session_was_open = False

    try:
        log(f"Starting discovery on {target_url} (depth <= {max_depth}, max_pages <= {max_pages})")
        from app.scraper.browser_driver import BrowserDownloader

        browser_session = BrowserDownloader()
        browser_session_was_open = browser_session.is_browser_open()
        if browser_session_was_open:
            log("Dedicated Chrome is open; using live authenticated CDP session.")
        try:
            if browser_session_was_open:
                session_cookies = browser_session.get_live_session_cookies()
                live_storage = browser_session.get_live_session_storage()
                log(f"Loaded {len(session_cookies)} cookies from the live Chrome CDP session (values hidden).")
                log(
                    "Loaded live browser storage: "
                    f"localStorage={len(live_storage.get('local', {}))}, "
                    f"sessionStorage={len(live_storage.get('session', {}))}."
                )
            else:
                session_cookies = []
                log("Dedicated Chrome is not open; no authenticated session available.")
        except Exception as session_error:
            session_cookies = []
            log(f"Live session is unavailable; continuing without authentication: {session_error}")
        has_authentication_cookies = browser_session.has_authentication_cookies(session_cookies)
        log(
            f"Authentication={str(has_authentication_cookies).lower()} "
            f"(entries={len(session_cookies)}; values hidden)."
        )
        if has_authentication_cookies:
            log(f"Using live browser session for authenticated requests ({len(session_cookies)} cookie entries loaded; values hidden).")
        else:
            log("Authentication=false before crawling; no recognized authentication cookies were available.")
        task["current_step"] = "Crawling site & searching for download buttons..."

        scraper = SiteScraper(
            target_url=target_url,
            max_crawl_pages=max_pages,
            max_depth=max_depth,
            cookies=session_cookies or None,
            browser_driver=browser_session,
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
            _mark_scrape_history(target_url)
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
                    try:
                        card = storage_service.upload_slide_file(
                            local_pptx_path=slide.pptx_file_path,
                            local_preview_path=slide.preview_image_path,
                            original_source_url=ppt.download_url,
                            original_presentation_name=ppt.title,
                            slide_title=slide.title,
                            slide_index=slide.slide_index,
                            total_slides=slide.total_slides,
                        )
                    except Exception as upload_error:
                        log(f"Firebase upload failed for {slide.slide_filename}: {upload_error}")
                        raise RuntimeError(f"Firebase upload failed for {slide.slide_filename}") from upload_error
                    uploaded_slides += 1
                    task["uploaded_slides_count"] = uploaded_slides
                    saved_cards.append({
                        "id": card.id,
                        "title": card.title,
                        "slide_filename": card.slide_filename,
                        "preview_url": card.preview_url,
                        "pptx_url": card.pptx_url,
                    })

            except Exception as processing_error:
                log(f"Error processing '{ppt.title}': {processing_error}")
                raise

        task["saved_slides"] = saved_cards
        if stop_event.is_set():
            task["status"] = "cancelled"
            task["current_step"] = "Task cancelled by user."
            log("Task cancelled during slide processing.")
        else:
            _mark_scrape_history(target_url)
            task["status"] = "completed"
            task["current_step"] = f"Completed successfully! {uploaded_slides} slides saved to Firebase Storage."
            log(f"All processing complete! Saved {uploaded_slides} individual slide files to Firebase Storage.")

    except Exception as e:
        task["status"] = "failed"
        task["error"] = str(e)
        task["current_step"] = f"Failed with error: {e}"
        log(f"Critical error during task: {e}")
    finally:
        if browser_session_was_open and browser_session is not None and browser_session.is_browser_open():
            log("Closing the dedicated Chrome session after scraping completed.")
            browser_session.close_browser_session()
        task["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        if task_id in active_threads:
            del active_threads[task_id]


@router.post("/start", response_model=ScrapeTaskStatus)
def start_scrape_task(request: StartScrapeRequest):
    if not request.url or not request.url.strip():
        raise HTTPException(status_code=400, detail="Target URL cannot be empty")

    target_url = request.url.strip()
    task_id = str(uuid.uuid4())
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    if _was_scraped(target_url):
        task_record = {
            "task_id": task_id,
            "target_url": target_url,
            "status": "completed",
            "current_step": "Skipped: this target was already scraped.",
            "discovered_files_count": 0,
            "total_slides_created": 0,
            "uploaded_slides_count": 0,
            "logs": [
                f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Skipped previously scraped target: {target_url}"
            ],
            "created_at": now,
            "updated_at": now,
            "error": None,
            "saved_slides": [],
        }
        tasks[task_id] = task_record
        return ScrapeTaskStatus(**task_record)
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
    url: str = Field(..., description="Target URL to open in the dedicated Chrome session")


session_state = {
    "status": "not_connected",
    "site": None,
    "message": "No saved browser session.",
    "debug_logs": [],
}
login_stop_event: threading.Event | None = None


def _session_log(message: str) -> None:
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    logs = session_state.setdefault("debug_logs", [])
    logs.append(f"[{timestamp}] {message}")
    if len(logs) > 50:
        del logs[:-50]


@router.get("/session")
def get_browser_session_status():
    """Returns browser-session status without exposing credentials or cookies."""
    from app.scraper.browser_driver import BrowserDownloader

    browser = BrowserDownloader()
    browser_open = browser.is_browser_open()
    if browser_open and session_state["status"] != "browser_open":
        _session_log("Session poll detected the dedicated Chrome process.")
    if not browser_open and session_state["status"] == "browser_open":
        _session_log("Session poll detected that the dedicated Chrome process has closed.")
    if browser_open:
        session_state.update({
            "status": "browser_open",
            "message": "Chrome is open. Complete login in this same window; it will stay open while scraping uses the live session.",
        })
    elif session_state["status"] == "browser_open":
        session_state.update({
            "status": "authenticated",
            "message": "Browser session saved locally.",
        })
    return session_state


@router.post("/open-browser-login")
def open_browser_login(req: OpenBrowserLoginRequest):
    """Starts a visible Chrome session and returns immediately while it remains open."""
    global login_stop_event

    if session_state["status"] == "browser_open":
        return session_state

    login_stop_event = threading.Event()
    _session_log(f"Opening dedicated Chrome session for target URL: {req.url}")
    session_state.update({
        "status": "browser_open",
        "site": req.url,
        "message": f"Chrome is open at {req.url}. Complete login in this same window, then mark login complete; scraping will use this live session.",
    })

    def _run_browser(stop_event: threading.Event):
        from app.scraper.browser_driver import BrowserDownloader

        try:
            browser = BrowserDownloader(headless=False)
            browser.open_browser_login(req.url, log=_session_log, stop_event=stop_event)
            if stop_event.is_set():
                _session_log("Dedicated Chrome session was closed by the application; keeping the saved authentication result.")
                return
            _session_log("Dedicated Chrome process ended and the browser profile is available for reading.")
            authenticated = browser.verify_authenticated_session(req.url, log=_session_log)
            if authenticated is False and browser.has_persisted_session():
                _session_log("The profile check disagreed, but the live authenticated cookie capture is available for scraping.")
                session_state.update({
                    "status": "authenticated",
                    "message": "Live login session captured and ready for scraping.",
                })
            elif authenticated is False:
                session_state.update({
                    "status": "not_authenticated",
                    "message": "Chrome closed, but SlideModel login was not detected in the saved session.",
                })
            else:
                session_state.update({
                    "status": "authenticated",
                    "message": "Browser session saved locally.",
                })
        except Exception as error:
            _session_log(f"Browser session error: {error}")
            session_state.update({
                "status": "error",
                "message": f"Browser login failed: {error}",
            })

    thread = threading.Thread(target=_run_browser, args=(login_stop_event,), daemon=True)
    thread.start()
    return session_state


@router.post("/session/verify")
def verify_browser_session():
    """Checks the currently open Chrome page before scraping uses the live session."""
    from app.scraper.browser_driver import BrowserDownloader

    target_url = session_state.get("site")
    if not target_url:
        return {**session_state, "status": "error", "message": "No active target URL is available for live authentication verification."}

    try:
        authenticated = BrowserDownloader(headless=False).verify_live_authenticated_session(target_url, log=_session_log)
    except Exception as error:
        _session_log(f"Live authentication check failed: {error}")
        return {**session_state, "status": "error", "message": f"Live authentication check failed: {error}"}

    if authenticated:
        session_state.update({"status": "browser_open", "message": "Login detected in the open Chrome session. Keep Chrome open while scraping."})
    else:
        session_state.update({"status": "not_authenticated", "message": "Login was not detected in the open Chrome session."})
    return session_state


@router.post("/session/complete")
def complete_browser_session():
    """Marks login complete while keeping Chrome open for authenticated scraping."""
    _session_log("User marked login complete; Chrome will remain open for live authenticated scraping.")
    session_state.update({
        "status": "authenticated",
        "message": "Login marked complete. Keep Chrome open; scraping will use the live authenticated session.",
    })
    return session_state


@router.post("/session/close")
def close_browser_session():
    """Closes only the scraper-owned Chrome window while retaining the saved session."""
    from app.scraper.browser_driver import BrowserDownloader

    _session_log("Closing the dedicated scraper browser; saved session will be retained.")
    if login_stop_event:
        login_stop_event.set()

    browser = BrowserDownloader()
    browser.close_browser_session()
    session_state.update({
        "status": "authenticated",
        "message": "Scraper browser closed. Saved browser session retained.",
    })
    return session_state


@router.delete("/session")
def clear_browser_session():
    """Clears the locally persisted browser session."""
    from app.scraper.browser_driver import BrowserDownloader

    _session_log("Clearing the dedicated Chrome profile and saved session.")
    if login_stop_event:
        login_stop_event.set()
    BrowserDownloader().clear_session()
    session_state.update({
        "status": "not_connected",
        "site": None,
        "message": "Saved browser session cleared.",
    })
    return session_state

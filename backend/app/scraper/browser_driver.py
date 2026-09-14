"""
Playwright Browser Automation Driver for PowerPoint Scraping.
Automates browser interaction, handles JavaScript execution, Google authentication persistence,
and intercepts .pptx file downloads directly from interactive web pages.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import webbrowser
from pathlib import Path
from typing import Callable
from playwright.sync_api import sync_playwright, BrowserContext, Page, Download

from app.config import settings
from app.scraper.detector import is_powerpoint_content


class BrowserDownloader:
    def __init__(self, user_data_dir: Path | None = None, headless: bool = True):
        self.user_data_dir = user_data_dir or (settings.data_dir / "browser_profile")
        self.user_data_dir.mkdir(parents=True, exist_ok=True)
        self.headless = headless

    def get_session_cookie_header(self) -> str:
        """Reads the locally persisted browser session for internal scraper use only."""
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                channel="chrome",
                user_data_dir=str(self.user_data_dir),
                headless=True,
                accept_downloads=True,
            )
            try:
                cookies = context.cookies()
                return "; ".join(f"{cookie['name']}={cookie['value']}" for cookie in cookies)
            finally:
                context.close()

    def clear_session(self) -> None:
        """Removes the persisted browser profile after the user requests sign-out."""
        import shutil

        if self.user_data_dir.exists():
            shutil.rmtree(self.user_data_dir)
        self.user_data_dir.mkdir(parents=True, exist_ok=True)

    def open_browser_login(
        self,
        url: str,
        log: Callable[[str], None] | None = None,
        stop_event: threading.Event | None = None,
    ) -> None:
        """Opens the target URL in a dedicated Chrome profile for manual authentication."""
        def _log(msg: str):
            if log:
                log(msg)

        chrome_candidates = [
            shutil.which("chrome.exe"),
            os.path.join(os.environ.get("PROGRAMFILES", ""), "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "Application", "chrome.exe"),
        ]
        chrome_path = next((candidate for candidate in chrome_candidates if candidate and os.path.exists(candidate)), None)
        if not chrome_path:
            raise RuntimeError("Google Chrome executable was not found")

        self.user_data_dir.mkdir(parents=True, exist_ok=True)
        command = [
            chrome_path,
            f"--user-data-dir={self.user_data_dir}",
            "--new-window",
            "--start-maximized",
            "--no-first-run",
            "--no-default-browser-check",
            url,
        ]
        _log("[Browser Automation] Launching the target page in a dedicated Chrome session...")
        browser_process = subprocess.Popen(command)
        _log(f"[Browser Automation] Target page opened in Chrome: {url}")
        _log("[Browser Automation] Complete any site or Google authentication prompts manually.")

        while browser_process.poll() is None:
            if stop_event and stop_event.wait(timeout=1):
                browser_process.terminate()
                break
            time.sleep(0.1)

        _log("[Browser Automation] Chrome session closed. Browser session saved locally.")

    def download_powerpoint_from_page(
        self,
        url: str,
        log: Callable[[str], None] | None = None,
        timeout_sec: int = 30,
    ) -> tuple[str, bytes] | None:
        """
        Visits the page in a persistent Chromium session, finds and clicks the download button/form,
        and intercepts the downloaded PowerPoint file.
        Returns (filename, file_bytes) or None.
        """
        def _log(msg: str):
            if log:
                log(msg)

        _log(f"[Browser Automation] Launching Chromium session for: {url}")

        with sync_playwright() as p:
            launch_kwargs = {
                "user_data_dir": str(self.user_data_dir),
                "headless": self.headless,
                "accept_downloads": True,
                "viewport": {"width": 1280, "height": 800},
                "ignore_default_args": ["--enable-automation"],
                "args": [
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-infobars",
                ],
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            }

            context: BrowserContext = None
            for ch in ["chrome", "msedge", None]:
                try:
                    kwargs = dict(launch_kwargs)
                    if ch:
                        kwargs["channel"] = ch
                    context = p.chromium.launch_persistent_context(**kwargs)
                    break
                except Exception:
                    continue

            if not context:
                context = p.chromium.launch_persistent_context(**launch_kwargs)

            # Evade navigator.webdriver detection
            context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

            try:
                page: Page = context.new_page()
                page.set_default_timeout(timeout_sec * 1000)

                _log(f"[Browser Automation] Navigating to target page...")
                page.goto(url, wait_until="domcontentloaded")
                page.wait_for_timeout(2000)

                login_link = page.locator("a[href*='/account/login']").first
                email_field = page.locator("input[name='rcp_user_email']").first
                if login_link.is_visible() and email_field.is_visible():
                    _log("[Browser Automation] The saved Chrome session is not authenticated to the target site.")
                    _log("[Browser Automation] Complete the target site's login in Chrome, then click Login complete before scraping.")
                    return None

                # 1. Search for download candidates on the page
                download_selectors = [
                    "#box-activate-download-button",
                    "input[value*='Download' i]",
                    "input[value*='Continue' i]",
                    "button:has-text('Download')",
                    "button:has-text('PowerPoint')",
                    "button:has-text('PPTX')",
                    "a:has-text('Download PowerPoint')",
                    "a:has-text('Download PPTX')",
                    "a:has-text('Download Template')",
                    "a:has-text('Download')",
                    "a[href*='.pptx']",
                    "a[href*='/download/']",
                    ".btn-download",
                    ".download-btn",
                    ".btn-purchase",
                ]

                download_element = None
                for selector in download_selectors:
                    try:
                        locator = page.locator(selector).first
                        if locator.is_visible():
                            download_element = locator
                            _log(f"[Browser Automation] Detected download element: '{selector}'")
                            break
                    except Exception:
                        continue

                if not download_element:
                    _log(f"[Browser Automation] No interactive download button found on page.")
                    return None

                # 2. Trigger download and wait for download event
                _log(f"[Browser Automation] Clicking download button and awaiting file stream...")
                with tempfile.TemporaryDirectory() as tmp_dir:
                    try:
                        with page.expect_download(timeout=20000) as download_info:
                            download_element.click()

                        download: Download = download_info.value
                        suggested_name = download.suggested_filename or "presentation.pptx"
                        save_path = Path(tmp_dir) / suggested_name
                        download.save_as(str(save_path))

                        if save_path.exists() and save_path.stat().st_size > 0:
                            content = save_path.read_bytes()
                            is_ppt, fmt = is_powerpoint_content(content)
                            if is_ppt:
                                _log(f"[Browser Automation] Successfully intercepted {fmt.upper()} file: {suggested_name} ({len(content) // 1024} KB)")
                                return suggested_name, content
                            else:
                                _log(f"[Browser Automation] Downloaded file is not a valid PowerPoint presentation ({len(content)} bytes).")
                    except Exception as click_err:
                        _log(f"[Browser Automation] Download wait event notice: {click_err}")

            finally:
                context.close()

        return None

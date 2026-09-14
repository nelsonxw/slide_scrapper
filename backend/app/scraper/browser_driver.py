"""
Playwright Browser Automation Driver for PowerPoint Scraping.
Automates browser interaction, handles JavaScript execution, Google authentication persistence,
and intercepts .pptx file downloads directly from interactive web pages.
"""
from __future__ import annotations

import os
import re
import tempfile
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

    def extract_cookies_after_login(self, log: Callable[[str], None] | None = None) -> str:
        """
        Opens a browser for manual login and automatically extracts cookies after login.
        Returns the cookies as a string for use in automated scraping.
        """
        def _log(msg: str):
            if log:
                log(msg)

        _log("[Browser Automation] Launching browser for login and cookie extraction...")

        with sync_playwright() as p:
            # Use realistic browser settings to appear as normal as possible
            launch_kwargs = {
                "user_data_dir": str(self.user_data_dir),
                "headless": False,
                "accept_downloads": True,
                "viewport": {"width": 1920, "height": 1080},
                "ignore_default_args": ["--enable-automation", "--enable-blink-features=AutomationControlled"],
                "args": [
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-infobars",
                    "--disable-dev-shm-usage",
                    "--disable-web-security",
                    "--disable-features=IsolateOrigins,site-per-process,VizDisplayCompositor",
                    "--disable-background-networking",
                    "--disable-default-apps",
                    "--disable-extensions",
                    "--disable-sync",
                    "--disable-translate",
                    "--hide-scrollbars",
                    "--metrics-recording-only",
                    "--mute-audio",
                    "--no-first-run",
                    "--safebrowsing-disable-auto-update",
                    "--disable-ipc-flooding-protection",
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
                # Open Google login page first
                page1: Page = context.new_page()
                try:
                    page1.goto("https://accounts.google.com/", wait_until="domcontentloaded")
                    _log("[Browser Automation] Google login page opened - please log in to your Google account")
                except Exception as e:
                    _log(f"[Browser Automation] Warning: Could not open Google login page: {e}")

                # Open SlideModel login page
                page2: Page = context.new_page()
                try:
                    page2.goto("https://www.slidemodel.com/account/login/", wait_until="domcontentloaded")
                    page2.wait_for_timeout(3000)
                    _log("[Browser Automation] SlideModel login page opened")
                except Exception as e:
                    _log(f"[Browser Automation] Warning: Could not open SlideModel login page: {e}")

                # Keep browser open for manual login
                _log("[Browser Automation] Browser window is open. Please log in to Google on Tab 1, then complete authentication on Tab 2.")
                _log("[Browser Automation] Close the browser window when finished to automatically extract cookies.")

                # Wait indefinitely until browser is closed
                try:
                    while True:
                        page2.wait_for_timeout(5000)
                except Exception:
                    _log("[Browser Automation] Browser closed. Extracting cookies...")

                # Extract cookies from the context
                cookies = context.cookies()
                _log(f"[Browser Automation] Extracted {len(cookies)} cookies from browser session")

                # Format cookies as a string for HTTP requests
                cookie_string = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
                _log(f"[Browser Automation] Cookie string ready (length: {len(cookie_string)} characters)")

                return cookie_string

            finally:
                context.close()

    def open_browser_login(self, log: Callable[[str], None] | None = None) -> None:
        """
        Opens a visible browser window for manual login to target websites.
        Preserves the session for future automated scrapes.
        """
        def _log(msg: str):
            if log:
                log(msg)

        _log("[Browser Automation] Launching visible browser for manual login...")

        with sync_playwright() as p:
            launch_kwargs = {
                "user_data_dir": str(self.user_data_dir),
                "headless": False,
                "accept_downloads": True,
                "viewport": {"width": 1280, "height": 800},
                "ignore_default_args": ["--enable-automation"],
                "args": [
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-infobars",
                    "--disable-web-security",
                    "--disable-features=IsolateOrigins,site-per-process",
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
                # Open Google login page first to establish Google session
                page1: Page = context.new_page()
                try:
                    page1.goto("https://accounts.google.com/", wait_until="domcontentloaded")
                    _log("[Browser Automation] Google login page opened - please log in to your Google account first")
                except Exception as e:
                    _log(f"[Browser Automation] Warning: Could not open Google login page: {e}")

                # Open SlideModel login page
                page2: Page = context.new_page()
                try:
                    page2.goto("https://www.slidemodel.com/account/login/", wait_until="domcontentloaded")
                    page2.wait_for_timeout(3000)
                    _log("[Browser Automation] SlideModel login page opened")
                except Exception as e:
                    _log(f"[Browser Automation] Warning: Could not open SlideModel login page: {e}")
                    _log("[Browser Automation] You can manually navigate to any site requiring login in the browser window.")

                # Keep browser open for manual login
                _log("[Browser Automation] Browser window is open. Tab 1: Google login, Tab 2: SlideModel login.")
                _log("[Browser Automation] Log in to Google on Tab 1 first, then complete Google authentication on Tab 2.")
                _log("[Browser Automation] Close the browser window when finished to save your session.")

                # Wait indefinitely until browser is closed
                try:
                    while True:
                        page2.wait_for_timeout(5000)
                except Exception:
                    _log("[Browser Automation] Browser closed. Session saved.")

            finally:
                context.close()

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

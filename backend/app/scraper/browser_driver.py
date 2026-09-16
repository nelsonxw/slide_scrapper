"""
Playwright Browser Automation Driver for PowerPoint Scraping.
Automates browser interaction, handles JavaScript execution, persists site login sessions,
and intercepts .pptx file downloads directly from interactive web pages.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import webbrowser
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright, BrowserContext, Page, Download

from app.config import settings
from app.scraper.detector import is_powerpoint_content


class BrowserDownloader:
    def __init__(self, user_data_dir: Path | None = None, headless: bool = True):
        self.user_data_dir = user_data_dir or (settings.data_dir / "browser_profile")
        self.user_data_dir.mkdir(parents=True, exist_ok=True)
        self.headless = headless

    def _session_cookie_file(self) -> Path:
        return settings.data_dir / "browser_session_cookies.json"

    def _read_persisted_cookie_header(self) -> str:
        cookie_file = self._session_cookie_file()
        if not cookie_file.exists():
            return ""
        try:
            cookies = json.loads(cookie_file.read_text(encoding="utf-8"))
            return "; ".join(f"{cookie['name']}={cookie['value']}" for cookie in cookies)
        except (OSError, ValueError, TypeError, KeyError):
            return ""

    def _save_persisted_cookies(self, cookies: list[dict[str, object]]) -> None:
        cookie_file = self._session_cookie_file()
        cookie_file.write_text(json.dumps(cookies), encoding="utf-8")

    def has_persisted_session(self) -> bool:
        return bool(self._read_persisted_cookie_header())

    def get_session_cookies(
        self,
        target_url: str | None = None,
        retries: int = 5,
        retry_delay_sec: float = 1.0,
    ) -> list[dict[str, object]]:
        """Reads target-host cookies from the persisted Chrome session."""
        target_host = (urlparse(target_url).hostname or "").lower() if target_url else None
        last_error: Exception | None = None

        for attempt in range(retries):
            try:
                with sync_playwright() as p:
                    context = p.chromium.launch_persistent_context(
                        channel="chrome",
                        user_data_dir=str(self.user_data_dir),
                        headless=True,
                        accept_downloads=True,
                    )
                    try:
                        try:
                            persisted = json.loads(self._session_cookie_file().read_text(encoding="utf-8"))
                        except (OSError, ValueError, TypeError):
                            persisted = []

                        persisted_cookies = self._filter_session_cookies(persisted, target_host)
                        if persisted_cookies:
                            return persisted_cookies
                        return self._filter_session_cookies(context.cookies(), target_host)
                    finally:
                        context.close()
            except Exception as error:
                last_error = error
                if attempt < retries - 1:
                    time.sleep(retry_delay_sec)

        raise RuntimeError(
            f"Could not open the saved Chrome profile after {retries} attempts: {last_error}"
        ) from last_error

    def get_session_cookie_header(
        self,
        target_url: str | None = None,
        retries: int = 5,
        retry_delay_sec: float = 1.0,
    ) -> str:
        """Returns a compatibility Cookie header for the target host."""
        cookies = self.get_session_cookies(target_url, retries, retry_delay_sec)
        return "; ".join(
            f"{cookie['name']}={cookie['value']}"
            for cookie in cookies
            if cookie.get("name")
        )

    def _filter_session_cookies(
        self,
        cookies: list[dict[str, object]],
        target_host: str | None,
    ) -> list[dict[str, object]]:
        """Keeps valid target-host cookies while preserving browser metadata."""
        selected: dict[tuple[str, str, str], dict[str, object]] = {}
        for cookie in cookies:
            name = str(cookie.get("name", ""))
            domain = str(cookie.get("domain", "")).lower().lstrip(".")
            path = str(cookie.get("path", "/"))
            if not name or (
                target_host
                and domain
                and target_host != domain
                and not target_host.endswith(f".{domain}")
            ):
                continue
            key = (name, domain, path)
            selected[key] = cookie
        return list(selected.values())

    def _page_requires_authentication(self, page: Page) -> bool:
        """Detects generic login, subscription, and upgrade gates without site-specific rules."""
        if page.locator("a[href*='logout']:visible").count() or page.get_by_text("My Account", exact=True).count():
            return False
        if page.locator("input[type='password']").first.is_visible():
            return True
        if page.locator("form[action*='signup']:visible, form[action*='register']:visible").count():
            return True
        body_text = page.locator("body").inner_text().lower()
        return any(
            phrase in body_text
            for phrase in (
                "login to download",
                "log in to download",
                "sign in to download",
                "please log in",
                "please sign in",
                "upgrade to download",
                "subscribe to download",
                "membership required",
                "complete the form in order to download",
                "create a free account",
                "free account to download",
            )
        )

    def verify_authenticated_session(self, target_url: str, log: Callable[[str], None] | None = None) -> bool | None:
        """Verifies generic authentication indicators on the target page."""
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                channel="chrome",
                user_data_dir=str(self.user_data_dir),
                headless=True,
                accept_downloads=True,
            )
            try:
                page = context.new_page()
                page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(2000)
                is_authenticated = not self._page_requires_authentication(page)
                if log:
                    log(f"[Browser Automation] Target-page authentication check at {page.url}: gated={not is_authenticated}, authenticated={is_authenticated}.")
                return is_authenticated
            finally:
                context.close()

    def verify_live_authenticated_session(self, target_url: str, log: Callable[[str], None] | None = None) -> bool:
        """Checks authentication indicators on the actual target page in open Chrome."""
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
            pages = [page for context in browser.contexts for page in context.pages]
            if not pages:
                raise RuntimeError("No open page was found in the dedicated Chrome session")

            page = pages[0]
            page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(2000)
            authenticated = not self._page_requires_authentication(page)
            if authenticated:
                cookies = browser.contexts[0].cookies()
                self._save_persisted_cookies(cookies)
                if log:
                    log(f"[Browser Automation] Captured {len(cookies)} live session cookies for server-side reuse; values hidden.")
            if log:
                log(f"[Browser Automation] Live auth check at {page.url}: gated={not authenticated}, authenticated={authenticated}.")
            return authenticated

    def _profile_process_ids(self) -> list[int]:
        """Returns Chrome processes using this app-owned profile on Windows."""
        if os.name != "nt":
            return []

        profile_path = str(self.user_data_dir.resolve()).replace("'", "''")
        script = (
            "$profile = '" + profile_path + "'; "
            "$processes = Get-CimInstance Win32_Process -Filter \"Name = 'chrome.exe'\"; "
            "$processes | Where-Object { $_.CommandLine -and $_.CommandLine.Contains($profile) -and -not $_.CommandLine.Contains('--type=') -and -not $_.CommandLine.Contains('--headless') } "
            "| Select-Object -ExpandProperty ProcessId"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            check=False,
        )
        process_ids = []
        for line in result.stdout.splitlines():
            try:
                process_ids.append(int(line.strip()))
            except ValueError:
                continue
        return process_ids

    def is_browser_open(self) -> bool:
        """Returns whether the dedicated app-owned Chrome profile is currently open."""
        return bool(self._profile_process_ids())

    def close_browser_session(self) -> None:
        """Closes only Chrome processes belonging to this app-owned profile."""
        for process_id in self._profile_process_ids():
            subprocess.run(
                ["taskkill", "/PID", str(process_id), "/T", "/F"],
                capture_output=True,
                text=True,
                check=False,
            )
        for _ in range(20):
            if not self.is_browser_open():
                break
            time.sleep(0.25)

    def clear_session(self) -> None:
        """Removes the persisted browser profile after the user requests sign-out."""
        self.close_browser_session()
        if self.user_data_dir.exists():
            shutil.rmtree(self.user_data_dir)
        self._session_cookie_file().unlink(missing_ok=True)
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
            "--disable-background-mode",
            "--remote-debugging-port=9222",
            url,
        ]
        _log("[Browser Automation] Launching the target page in a dedicated Chrome session...")
        browser_process = subprocess.Popen(command)
        _log(f"[Browser Automation] Target page opened in Chrome: {url}")
        _log("[Browser Automation] Complete the target site's username and password login manually.")

        while browser_process.poll() is None:
            if stop_event and stop_event.wait(timeout=1):
                browser_process.terminate()
                break
            time.sleep(0.1)

        _log("[Browser Automation] Chrome session closed. Browser session saved locally.")

    def _prepare_context_cookies(
        self,
        session_cookies: list[dict[str, object]] | dict[str, str],
        target_domain: str,
    ) -> list[dict[str, object]]:
        """Converts saved Chrome cookies into Playwright context cookies."""
        if isinstance(session_cookies, dict):
            return [
                {
                    "name": name,
                    "value": value,
                    "domain": target_domain,
                    "path": "/",
                }
                for name, value in session_cookies.items()
            ]

        target_domain = target_domain.lower().lstrip(".")
        prepared: list[dict[str, object]] = []
        for cookie in session_cookies:
            domain = str(cookie.get("domain", "")).lower().lstrip(".")
            if domain and target_domain != domain and not target_domain.endswith(f".{domain}"):
                continue

            name = str(cookie.get("name", ""))
            if not name:
                continue

            prepared_cookie: dict[str, object] = {
                "name": name,
                "value": str(cookie.get("value", "")),
                "domain": domain or target_domain,
                "path": str(cookie.get("path", "/")),
            }
            for key in ("expires", "httpOnly", "secure", "sameSite"):
                if key in cookie and cookie[key] is not None:
                    prepared_cookie[key] = cookie[key]
            prepared.append(prepared_cookie)
        return prepared

    def download_powerpoint_from_page(
        self,
        url: str,
        log: Callable[[str], None] | None = None,
        timeout_sec: int = 20,
        session_cookies: list[dict[str, object]] | dict[str, str] | None = None,
        session_cookie_domain: str | None = None,
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
                "headless": self.headless,
                "args": [
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-infobars",
                ],
            }

            browser = None
            for ch in ["chrome", "msedge", None]:
                try:
                    kwargs = dict(launch_kwargs)
                    if ch:
                        kwargs["channel"] = ch
                    browser = p.chromium.launch(**kwargs)
                    break
                except Exception:
                    continue

            if not browser:
                browser = p.chromium.launch(**launch_kwargs)

            context = browser.new_context(
                viewport={"width": 1280, "height": 800},
                accept_downloads=True,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            )
            cookie_domain = session_cookie_domain or urlparse(url).hostname
            if session_cookies and cookie_domain:
                cookies = self._prepare_context_cookies(
                    session_cookies,
                    cookie_domain,
                )
                _log(f"[Browser Automation] Injecting {len(cookies)} saved cookie entries for {cookie_domain} (values hidden).")
                if cookies:
                    context.add_cookies(cookies)

            # Evade navigator.webdriver detection
            context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

            try:
                page: Page = context.new_page()
                timeout_ms = timeout_sec * 1000
                page.set_default_timeout(timeout_ms)
                page.set_default_navigation_timeout(timeout_ms)

                _log(f"[Browser Automation] Navigating to target page...")
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                page.wait_for_timeout(min(500, timeout_ms))
                _log(f"[Browser Automation] Page loaded at {page.url}.")

                password_visible = page.locator("input[type='password']").first.is_visible()
                body_text = page.locator("body").inner_text(timeout=timeout_ms).lower()
                gate_phrases = (
                    "login to download",
                    "log in to download",
                    "sign in to download",
                    "please log in",
                    "please sign in",
                    "upgrade to download",
                    "subscribe to download",
                    "membership required",
                    "complete the form in order to download",
                    "create a free account",
                    "free account to download",
                )
                is_gated = password_visible or any(phrase in body_text for phrase in gate_phrases)
                if is_gated:
                    _log("[Browser Automation] Skipping download because the page requires login, subscription, or upgrade.")
                    return None

                # 1. Search for download candidates on the page
                download_selectors = [
                    "input[type='submit']",
                    "button[type='submit']",
                    "input[type='submit'][value*='Download' i]",
                    "button:has-text('Download')",
                    "button:has-text('PowerPoint')",
                    "button:has-text('PPTX')",
                    "a:has-text('Download PowerPoint')",
                    "a:has-text('Download PPTX')",
                    "a:has-text('Download')",
                    "a[href*='.pptx']",
                    "a[href*='.ppt']",
                    "a[href*='download']",
                    "[download]",
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

                # 2. Trigger download and wait for download event or a PowerPoint response
                ppt_responses: list[Any] = []

                def capture_ppt_response(response):
                    content_type = response.headers.get("content-type", "").lower()
                    response_url = response.url.lower()
                    if "presentation" in content_type or response_url.endswith((".pptx", ".ppt")):
                        ppt_responses.append(response)

                context.on("response", capture_ppt_response)
                _log("[Browser Automation] Clicking download button and awaiting file stream...")
                with tempfile.TemporaryDirectory() as tmp_dir:
                    try:
                        with page.expect_download(timeout=timeout_sec * 1000) as download_info:
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
                        for response in ppt_responses:
                            try:
                                content = response.body()
                                is_ppt, fmt = is_powerpoint_content(content)
                                if is_ppt:
                                    filename = Path(urlparse(response.url).path).name or "presentation.pptx"
                                    _log(f"[Browser Automation] Captured {fmt.upper()} response without a native download event: {filename} ({len(content) // 1024} KB)")
                                    return filename, content
                            except Exception as response_error:
                                _log(f"[Browser Automation] Could not read PowerPoint response: {response_error}")

            finally:
                context.close()
                browser.close()

        return None

"""Opt-in integration test for the persisted SlideModel Chrome session.

Run with RUN_SLIDEMODEL_INTEGRATION=1 after logging in through the app's
isolated Chrome profile. The test is skipped during normal test runs because
it depends on a local browser profile and live network access.
"""
import os
from urllib.parse import urlparse

import httpx
import pytest

from app.scraper.browser_driver import BrowserDownloader
from app.scraper.crawler import SiteScraper


TARGET_URL = os.getenv(
    "SLIDEMODEL_TARGET_URL",
    "https://slidemodel.com/free-powerpoint-templates/3-ring-milestone-infographic-powerpoint-template/",
)
AUTH_COOKIE_PREFIXES = ("wordpress_logged_in_", "wordpress_sec_")


def _cookie_path_matches(cookie_path: str, request_path: str) -> bool:
    normalized_path = cookie_path.rstrip("/") or "/"
    return normalized_path == "/" or request_path == normalized_path or request_path.startswith(f"{normalized_path}/")


def test_persisted_slidemodel_session_is_accepted_by_httpx():
    if os.getenv("RUN_SLIDEMODEL_INTEGRATION") != "1":
        pytest.skip("Set RUN_SLIDEMODEL_INTEGRATION=1 to run the live SlideModel check")

    browser = BrowserDownloader()
    cookies = browser.get_session_cookies(target_url=TARGET_URL)
    cookie_names = {str(cookie.get("name", "")) for cookie in cookies}
    auth_cookie_names = sorted(
        name
        for name in cookie_names
        if name.startswith(AUTH_COOKIE_PREFIXES)
    )

    assert auth_cookie_names, (
        "The current isolated Chrome profile has no SlideModel authentication "
        f"cookie. Available cookie names: {sorted(cookie_names)}"
    )

    scraper = SiteScraper(TARGET_URL, cookies=cookies, use_browser=False)
    with httpx.Client(
        headers=scraper.headers,
        timeout=30.0,
        follow_redirects=True,
        verify=False,
    ) as client:
        scraper._configure_client_cookies(client)
        response = client.get(TARGET_URL)

    request_cookie_header = response.request.headers.get("cookie", "")
    target_path = urlparse(TARGET_URL).path
    request_auth_cookie_names = sorted(
        str(cookie.get("name"))
        for cookie in cookies
        if str(cookie.get("name", "")).startswith(AUTH_COOKIE_PREFIXES)
        and _cookie_path_matches(str(cookie.get("path", "/")), target_path)
    )
    assert all(name in request_cookie_header for name in request_auth_cookie_names), (
        "The applicable SlideModel authentication cookies were not included in "
        f"the HTTPX request. Cookie names: {request_auth_cookie_names}"
    )
    assert response.status_code == 200, (
        f"SlideModel returned HTTP {response.status_code}; final URL: {response.url}"
    )
    assert "/account/login" not in str(response.url).lower(), (
        f"SlideModel redirected the authenticated request to login: {response.url}"
    )
    assert "/account/signup" not in str(response.url).lower(), (
        f"SlideModel redirected the authenticated request to signup: {response.url}"
    )
    assert "complete the form in order to download" not in response.text.lower(), (
        "SlideModel returned its unauthenticated signup/download form despite "
        f"receiving authentication cookies. Final URL: {response.url}"
    )

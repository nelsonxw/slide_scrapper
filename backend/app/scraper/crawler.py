"""
Site & Sub-site Web Crawler for PowerPoint Download Buttons.
Crawls the target domain to identify download buttons/links and downloads verified PowerPoint presentations.
"""
from __future__ import annotations

import collections
import re
from dataclasses import dataclass
from typing import Callable, Iterable
from urllib.parse import urljoin, urlparse
import httpx
from bs4 import BeautifulSoup

from app.scraper.detector import is_powerpoint_content, is_powerpoint_url_or_header
from app.scraper.browser_driver import BrowserDownloader


Cookie = dict[str, object]


@dataclass
class DiscoveredPowerPoint:
    title: str
    download_url: str
    source_page_url: str
    format_type: str  # "pptx" or "ppt"
    content_bytes: bytes
    file_size: int


class SiteScraper:
    def __init__(
        self,
        target_url: str,
        max_crawl_pages: int = 30,
        max_depth: int = 3,
        user_agent: str | None = None,
        cookies: str | dict[str, str] | list[Cookie] | None = None,
        custom_headers: dict[str, str] | None = None,
        use_browser: bool = True,
        browser_driver: BrowserDownloader | None = None,
        enable_pagination: bool = True,
    ):
        self.target_url = target_url.strip()
        if not self.target_url.startswith(("http://", "https://")):
            self.target_url = "https://" + self.target_url

        self.max_crawl_pages = max_crawl_pages
        self.max_depth = max_depth
        self.use_browser = use_browser
        self.enable_pagination = enable_pagination
        self.browser_driver = browser_driver or BrowserDownloader()
        self._browser_processed_pages: set[str] = set()
        self.headers = {
            "User-Agent": user_agent
            or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        if custom_headers:
            self.headers.update(custom_headers)

        self.cookies: list[Cookie] = self._normalize_cookies(cookies)

    def _normalize_cookies(
        self,
        cookies: str | dict[str, str] | list[Cookie] | None,
    ) -> list[Cookie]:
        if isinstance(cookies, list):
            return [dict(cookie) for cookie in cookies]

        if isinstance(cookies, dict):
            return [{"name": name, "value": value, "path": "/"} for name, value in cookies.items()]

        if not isinstance(cookies, str) or not cookies.strip():
            return []

        normalized: list[Cookie] = []
        clean_cookie_str = cookies.replace("Cookie:", "").replace("cookie:", "").strip()
        for item in re.split(r"[;\n\r]+", clean_cookie_str):
            if "=" not in item:
                continue
            name, value = item.strip().split("=", 1)
            if name.strip():
                normalized.append({"name": name.strip(), "value": value.strip(), "path": "/"})
        return normalized

    def _configure_client_cookies(self, client: httpx.Client) -> None:
        """Adds Chrome cookies to an httpx client without logging their values."""
        for cookie in self.cookies:
            name = str(cookie.get("name", ""))
            value = str(cookie.get("value", ""))
            if not name:
                continue

            cookie_kwargs = {"path": str(cookie.get("path", "/"))}
            domain = str(cookie.get("domain", ""))
            if domain:
                cookie_kwargs["domain"] = domain
            client.cookies.set(name, value, **cookie_kwargs)

    def _response_requires_authentication(self, response: httpx.Response) -> bool:
        """Detects strong authentication gates without treating listing copy as a gate."""
        final_url = str(response.url).lower()
        auth_path_markers = ("/login", "/signin", "/sign-in", "/signup", "/register")
        if any(marker in final_url for marker in auth_path_markers):
            return True

        soup = BeautifulSoup(response.text, "html.parser")
        if soup.select_one("input[type='password']"):
            return True

        auth_forms = soup.select(
            "form[action*='login' i], form[action*='signin' i], "
            "form[action*='signup' i], form[action*='register' i]"
        )
        if auth_forms:
            return True

        download_auth_controls = soup.select(
            "a[href*='login' i][href*='download' i], "
            "a[href*='signin' i][href*='download' i], "
            "a[href*='signup' i][href*='download' i], "
            "form[action*='login' i], form[action*='signin' i], form[action*='signup' i]"
        )
        if download_auth_controls:
            return True

        return False

    def _is_download_element(self, tag: BeautifulSoup, href_or_action: str) -> bool:
        """
        Detects if a tag (<a>, <button>, <form>, <input>, etc.) represents a download button or direct PowerPoint download link.
        """
        href_lower = href_or_action.lower().split("?")[0]

        # Exclude static assets
        if any(
            href_lower.endswith(ext)
            for ext in [".css", ".js", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".mp4", ".mp3", ".pdf", ".zip"]
        ):
            return False

        # Direct PowerPoint file extensions
        if href_lower.endswith((".pptx", ".ppt", ".potx", ".ppsx")):
            return True

        # Tag has HTML5 'download' attribute
        if tag.has_attr("download"):
            return True

        text = tag.get_text(separator=" ", strip=True).lower()
        title_attr = tag.get("title", "").lower()
        aria_label = tag.get("aria-label", "").lower()
        classes = " ".join(tag.get("class", [])).lower() if tag.get("class") else ""
        elem_id = tag.get("id", "").lower()
        tag_value = tag.get("value", "").lower() if tag.has_attr("value") else ""
        descendant_values = " ".join(
            str(control.get("value", ""))
            for control in tag.find_all(["input", "button"])
            if control.has_attr("value")
        ).lower()
        all_text = f"{text} {title_attr} {aria_label} {classes} {elem_id} {tag_value} {descendant_values}"

        # Check for explicit PowerPoint download action keywords
        download_action_keywords = [
            "download",
            "get ppt",
            "get pptx",
            "get template",
            "free download",
            "download powerpoint",
            "download pptx",
            "download presentation",
            "telecharger",
            "descargar",
            "herunterladen",
            "télécharger",
            "download-btn",
            "download-button",
            "download-area",
            "btn-download",
        ]
        has_download_action = any(k in all_text for k in download_action_keywords) or "download" in href_lower

        if has_download_action:
            return True

        return False

    def _extract_download_candidates(
        self,
        soup: BeautifulSoup,
        current_url: str,
    ) -> list[tuple[str, str]]:
        candidates: list[tuple[str, str]] = []
        for tag in soup.find_all(["a", "button", "form", "input", "div", "span"]):
            href = (
                tag.get("href")
                or tag.get("data-href")
                or tag.get("data-url")
                or tag.get("action")
                or tag.get("formaction")
                or (tag.find_parent("form").get("action") if tag.find_parent("form") else None)
            )
            if not href or href.startswith(("javascript:", "mailto:", "tel:", "#")):
                continue

            full_url = urljoin(current_url, href)
            if not self._is_download_element(tag, full_url):
                continue

            link_title = (
                tag.get_text(strip=True)
                or tag.get("value")
                or tag.get("title")
                or tag.get("aria-label")
                or self._extract_title_from_url(full_url)
            )
            clean_title = re.sub(
                r"(?i)\b(download|free|pptx|ppt|powerpoint|template|get)\b",
                "",
                str(link_title),
            ).strip()
            candidates.append((full_url, clean_title or self._extract_title_from_url(full_url)))

        for ppt_match in re.finditer(
            r'https?://[^\s"\'<>]+\.(?:pptx|ppt)(?:\?[^\s"\'<>]*)?',
            str(soup),
            re.IGNORECASE,
        ):
            matched_url = ppt_match.group(0)
            candidates.append((matched_url, self._extract_title_from_url(matched_url)))
        return candidates

    def _is_pagination_link(self, url: str, current_url: str) -> bool:
        """
        Detects if a URL is a pagination link based on common patterns.
        Returns True if the URL appears to be a pagination link.
        """
        url_lower = url.lower()
        current_lower = current_url.lower()
        
        # Common pagination patterns
        pagination_patterns = [
            r'/page/\d+',           # /page/2/, /page/3/
            r'/page-\d+',           # /page-2, /page-3
            r'[?&]page=\d+',        # ?page=2, &page=3
            r'[?&]p=\d+',           # ?p=2, &p=3
            r'[?&]offset=\d+',      # ?offset=20
            r'[?&]start=\d+',       # ?start=20
            r'/p\d+',               # /p2, /p3
            r'/pg\d+',              # /pg2, /pg3
        ]
        
        for pattern in pagination_patterns:
            if re.search(pattern, url_lower):
                return True
        
        # Check for next/prev buttons in same path structure
        parsed_current = urlparse(current_lower)
        parsed_url = urlparse(url_lower)
        
        # Same domain and similar path structure
        if (parsed_current.hostname == parsed_url.hostname and 
            parsed_url.path.startswith(parsed_current.path.rstrip('/'))):
            # Check if it adds a pagination component
            current_path_parts = parsed_current.path.rstrip('/').split('/')
            url_path_parts = parsed_url.path.rstrip('/').split('/')
            
            # If URL has exactly one more path segment that looks like a number
            if (len(url_path_parts) == len(current_path_parts) + 1 and
                url_path_parts[-1].isdigit()):
                return True
        
        return False

    def _extract_internal_links(
        self,
        soup: BeautifulSoup,
        current_url: str,
        root_hostname: str,
    ) -> tuple[list[str], list[str]]:
        """
        Extracts internal links from a page, separating pagination links from regular links.
        Returns (regular_links, pagination_links).
        """
        regular_links: list[str] = []
        pagination_links: list[str] = []
        
        for anchor in soup.find_all("a", href=True):
            href = anchor["href"].strip()
            if not href or href.startswith(("javascript:", "mailto:", "tel:", "#")):
                continue
            sub_url = urljoin(current_url, href)
            parsed_sub = urlparse(sub_url)
            sub_hostname = (parsed_sub.hostname or "").lower()
            if sub_hostname != root_hostname and not sub_hostname.endswith(f".{root_hostname}"):
                continue
            if parsed_sub.scheme not in {"http", "https"}:
                continue
            if parsed_sub.path.lower().rstrip("/").endswith(
                (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".pdf", ".zip", ".css", ".js", ".mp4", ".mp3", ".json", ".xml")
            ):
                continue
            
            # Separate pagination links from regular links if pagination is enabled
            if self.enable_pagination and self._is_pagination_link(sub_url, current_url):
                pagination_links.append(sub_url)
            else:
                regular_links.append(sub_url)
        
        return regular_links, pagination_links

    def _crawl_via_live_browser(
        self,
        root_hostname: str,
        on_log: Callable[[str], None] | None,
        on_found: Callable[[DiscoveredPowerPoint], None] | None,
        should_stop: Callable[[], bool] | None,
    ) -> list[DiscoveredPowerPoint]:
        def log(message: str):
            if on_log:
                on_log(message)

        discovered_items: list[DiscoveredPowerPoint] = []
        visited_pages: set[str] = set()
        queue: collections.deque[tuple[str, int]] = collections.deque([(self.target_url, 0)])

        with self.browser_driver.connect_live_browser() as browser:
            if not browser.contexts:
                log("Live CDP browser has no context; no rendered pages can be crawled.")
                return []

            context = browser.contexts[0]
            page = context.pages[0] if context.pages else context.new_page()
            page.set_default_timeout(5000)
            page.set_default_navigation_timeout(10000)
            log("Active Chrome session detected. Crawling rendered pages through live CDP.")

            while queue and len(visited_pages) < self.max_crawl_pages:
                if should_stop and should_stop():
                    log("Crawling stopped by user.")
                    break

                current_url, depth = queue.popleft()
                clean_url = current_url.split("#")[0].rstrip("/")
                if clean_url in visited_pages:
                    continue
                visited_pages.add(clean_url)
                log(f"Crawling rendered page ({len(visited_pages)}/{self.max_crawl_pages}, depth={depth}): {current_url}")

                try:
                    page.goto(current_url, wait_until="domcontentloaded", timeout=10000)
                    page.wait_for_timeout(500)
                    rendered_html = page.content()
                except Exception as error:
                    log(f"Failed to render {current_url} in live browser: {error}")
                    continue

                soup = BeautifulSoup(rendered_html, "html.parser")
                auth_gate_detected = self.browser_driver.page_requires_authentication(page)
                authentication = BrowserDownloader.has_authentication_cookies(context.cookies())
                log(
                    "Live browser authentication check: "
                    f"authentication={str(authentication).lower()}, "
                    f"final_url={page.url}, auth_gate_detected={str(auth_gate_detected).lower()}"
                )

                candidates = self._extract_download_candidates(soup, page.url)
                if candidates:
                    log(f"Rendered page exposes {len(candidates)} download candidates.")
                has_download_control = self.browser_driver.has_visible_download_control(page)
                if candidates and has_download_control and page.url not in self._browser_processed_pages:
                    self._browser_processed_pages.add(page.url)
                    try:
                        result = self.browser_driver.download_powerpoint_from_live_page(
                            page,
                            page.url,
                            log=log,
                            timeout_sec=5,
                        )
                    except Exception as error:
                        log(f"Live browser download error on {page.url}: {error}")
                        result = None
                    if result:
                        name, content = result
                        item = DiscoveredPowerPoint(
                            title=name.rsplit(".", 1)[0].replace("_", " ").title(),
                            download_url=page.url,
                            source_page_url=current_url,
                            format_type="pptx",
                            content_bytes=content,
                            file_size=len(content),
                        )
                        discovered_items.append(item)
                        if on_found:
                            on_found(item)

                if depth < self.max_depth:
                    regular_links, pagination_links = self._extract_internal_links(soup, page.url, root_hostname)
                    
                    if pagination_links:
                        log(f"Found {len(pagination_links)} pagination links, prioritizing them")
                    
                    # Prioritize pagination links by adding them to the front of the queue
                    for sub_url in pagination_links:
                        clean_sub = sub_url.split("#")[0].rstrip("/")
                        if clean_sub not in visited_pages:
                            queue.appendleft((sub_url, depth))  # Keep same depth for pagination
                            log(f"Prioritized pagination link: {sub_url}")
                    
                    # Add regular links to the back of the queue
                    for sub_url in regular_links:
                        clean_sub = sub_url.split("#")[0].rstrip("/")
                        if clean_sub not in visited_pages:
                            queue.append((sub_url, depth + 1))

        log(f"Live browser crawl complete. Discovered {len(discovered_items)} valid PowerPoint presentations across {len(visited_pages)} pages.")
        return discovered_items

    def crawl_and_extract(
        self,
        on_log: Callable[[str], None] | None = None,
        on_found: Callable[[DiscoveredPowerPoint], None] | None = None,
        should_stop: Callable[[], bool] | None = None,
    ) -> list[DiscoveredPowerPoint]:
        """
        Performs BFS crawling across the target URL and sub-pages to locate download buttons and verify PowerPoint files.
        """
        def log(msg: str):
            if on_log:
                on_log(msg)

        parsed_root = urlparse(self.target_url)
        root_hostname = (parsed_root.hostname or "").lower()

        log(f"Starting crawl on: {self.target_url} (Domain: {root_hostname})")

        # Direct check if user provided a direct PPTX download URL
        if is_powerpoint_url_or_header(self.target_url):
            log(f"Target URL appears to be a direct PowerPoint link. Fetching directly...")
            item = self._fetch_and_validate(self.target_url, self.target_url, "Direct Presentation", log)
            if item:
                if on_found:
                    on_found(item)
                return [item]

        self._browser_processed_pages.clear()
        if self.use_browser and self.browser_driver.is_browser_open():
            return self._crawl_via_live_browser(
                root_hostname,
                on_log,
                on_found,
                should_stop,
            )

        discovered_items: list[DiscoveredPowerPoint] = []
        visited_pages: set[str] = set()
        seen_download_urls: set[str] = set()

        queue: collections.deque[tuple[str, int]] = collections.deque([(self.target_url, 0)])

        with httpx.Client(
            headers=self.headers,
            timeout=5.0,
            follow_redirects=True,
            verify=False,
        ) as client:
            self._configure_client_cookies(client)
            while queue and len(visited_pages) < self.max_crawl_pages:
                if should_stop and should_stop():
                    log("Crawling stopped by user.")
                    break

                current_url, depth = queue.popleft()
                clean_url = current_url.split("#")[0].rstrip("/")
                if clean_url in visited_pages:
                    continue
                visited_pages.add(clean_url)

                log(f"Crawling page ({len(visited_pages)}/{self.max_crawl_pages}, depth={depth}): {current_url}")

                try:
                    resp = client.get(current_url)
                except Exception as e:
                    log(f"Failed to fetch {current_url}: {e}")
                    continue

                if resp.status_code != 200:
                    log(f"HTTP {resp.status_code} on {current_url}")
                    continue

                auth_gate_detected = self._response_requires_authentication(resp)
                authentication = BrowserDownloader.has_authentication_cookies(self.cookies)
                log(
                    "Authentication check: "
                    f"authentication={str(authentication).lower()}, "
                    f"HTTP {resp.status_code}, final_url={resp.url}, "
                    f"cookies_applied={len(self.cookies)}, "
                    f"auth_gate_detected={auth_gate_detected}"
                )

                content_type = resp.headers.get("content-type", "").lower()

                # If the URL itself directly returned binary content
                is_ppt, fmt = is_powerpoint_content(resp.content)
                if is_ppt:
                    if current_url not in seen_download_urls:
                        seen_download_urls.add(current_url)
                        title = self._extract_title_from_url(current_url)
                        item = DiscoveredPowerPoint(
                            title=title,
                            download_url=current_url,
                            source_page_url=current_url,
                            format_type=fmt,
                            content_bytes=resp.content,
                            file_size=len(resp.content),
                        )
                        log(f"Found direct PowerPoint file: {title} ({fmt.upper()}, {len(resp.content) // 1024} KB)")
                        discovered_items.append(item)
                        if on_found:
                            on_found(item)
                    continue

                if "html" not in content_type and not current_url.endswith((".html", ".htm", "/")):
                    continue

                # Parse HTML for download buttons and links
                soup = BeautifulSoup(resp.text, "html.parser")

                # 1. Search <a> links, download buttons, and download form submits
                candidate_download_links: list[tuple[str, str]] = []  # (url, title)

                for tag in soup.find_all(["a", "button", "form", "input", "div", "span"]):
                    href = (
                        tag.get("href")
                        or tag.get("data-href")
                        or tag.get("data-url")
                        or tag.get("action")
                        or tag.get("formaction")
                        or (tag.find_parent("form").get("action") if tag.find_parent("form") else None)
                    )
                    if not href or href.startswith(("javascript:", "mailto:", "tel:", "#")):
                        continue

                    full_url = urljoin(current_url, href)

                    if self._is_download_element(tag, full_url):
                        link_title = (
                            tag.get_text(strip=True)
                            or tag.get("value")
                            or tag.get("title")
                            or tag.get("aria-label")
                            or self._extract_title_from_url(full_url)
                        )
                        clean_title = re.sub(r"(?i)\b(download|free|pptx|ppt|powerpoint|template|get)\b", "", str(link_title)).strip()
                        clean_title = clean_title or self._extract_title_from_url(full_url)
                        candidate_download_links.append((full_url, clean_title))

                # Also search for any direct .pptx / .ppt links in HTML attributes or script tags
                for ppt_match in re.finditer(r'https?://[^\s"\'<>]+\.(?:pptx|ppt)(?:\?[^\s"\'<>]*)?', resp.text, re.IGNORECASE):
                    matched_url = ppt_match.group(0)
                    candidate_download_links.append((matched_url, self._extract_title_from_url(matched_url)))

                # Process download candidates
                for dl_url, dl_title in candidate_download_links:
                    if dl_url in seen_download_urls:
                        continue
                    seen_download_urls.add(dl_url)

                    log(f"Inspecting download candidate: {dl_title} -> {dl_url}")
                    item = self._fetch_and_validate(dl_url, current_url, dl_title, log, client=client)
                    if item:
                        discovered_items.append(item)
                        if on_found:
                            on_found(item)

                # 2. Queue internal sub-pages for crawling
                if depth < self.max_depth:
                    regular_links, pagination_links = self._extract_internal_links(soup, current_url, root_hostname)
                    
                    if pagination_links:
                        log(f"Found {len(pagination_links)} pagination links, prioritizing them")
                    
                    # Prioritize pagination links by adding them to the front of the queue
                    for sub_url in pagination_links:
                        clean_sub = sub_url.split("#")[0].rstrip("/")
                        if clean_sub not in visited_pages:
                            queue.appendleft((sub_url, depth))  # Keep same depth for pagination
                            log(f"Prioritized pagination link: {sub_url}")
                    
                    # Add regular links to the back of the queue
                    for sub_url in regular_links:
                        clean_sub = sub_url.split("#")[0].rstrip("/")
                        if clean_sub not in visited_pages:
                            queue.append((sub_url, depth + 1))

        log(f"Crawling complete. Discovered {len(discovered_items)} valid PowerPoint presentations across {len(visited_pages)} pages.")
        return discovered_items

    def _fetch_url(self, url: str, client: httpx.Client | None = None) -> httpx.Response | None:
        """Helper to fetch a URL safely using existing client or temporary client."""
        try:
            if client:
                return client.get(url, headers=self.headers, timeout=5.0, follow_redirects=True)
            with httpx.Client(headers=self.headers, timeout=5.0, follow_redirects=True, verify=False) as temp_client:
                self._configure_client_cookies(temp_client)
                return temp_client.get(url)
        except Exception:
            return None

    def _fetch_and_validate(
        self,
        url: str,
        source_page_url: str,
        title: str,
        log: Callable[[str], None],
        client: httpx.Client | None = None,
    ) -> DiscoveredPowerPoint | None:
        """
        Downloads a candidate URL and validates if the response is a PowerPoint presentation.
        """
        try:
            resp = self._fetch_url(url, client=client)
            if not resp or resp.status_code != 200:
                log(f"Candidate request to {url} returned HTTP {resp.status_code if resp else 'Error'}")
                return None

            is_ppt, fmt = is_powerpoint_content(resp.content)
            if is_ppt:
                log(f"Verified PowerPoint file: {title} ({fmt.upper()}, {len(resp.content) // 1024} KB)")
                return DiscoveredPowerPoint(
                    title=title or self._extract_title_from_url(url),
                    download_url=url,
                    source_page_url=source_page_url,
                    format_type=fmt,
                    content_bytes=resp.content,
                    file_size=len(resp.content),
                )
            else:
                # Check if the response was an HTML page with an inner direct PPT link
                if b"<html" in resp.content[:1000].lower():
                    sub_soup = BeautifulSoup(resp.text, "html.parser")
                    inner_a = sub_soup.find("a", href=re.compile(r"\.(?:pptx|ppt)(?:\?.*)?$", re.IGNORECASE))
                    if inner_a and inner_a.get("href"):
                        inner_url = urljoin(url, inner_a["href"])
                        log(f"Following inner download link from landing page: {inner_url}")
                        inner_resp = self._fetch_url(inner_url, client=client)
                        if inner_resp and inner_resp.status_code == 200:
                            inner_is_ppt, inner_fmt = is_powerpoint_content(inner_resp.content)
                            if inner_is_ppt:
                                log(f"Verified PowerPoint file from landing page: {title} ({inner_fmt.upper()})")
                                return DiscoveredPowerPoint(
                                    title=title or self._extract_title_from_url(inner_url),
                                    download_url=inner_url,
                                    source_page_url=source_page_url,
                                    format_type=inner_fmt,
                                    content_bytes=inner_resp.content,
                                    file_size=len(inner_resp.content),
                                )

                    # Check if the page is an account login/signup gate or interactive download form
                    page_text = resp.text.lower()
                    interactive_download_form = sub_soup.find(
                        "form",
                        action=re.compile(r"/download(?:/|\?)", re.IGNORECASE),
                    )
                    signup_download_form = sub_soup.find(
                        "form",
                        action=re.compile(r"/account/signup(?:/|\?)", re.IGNORECASE),
                    )
                    is_auth_gate = self._response_requires_authentication(resp)
                    is_signup_download_form = bool(
                        signup_download_form
                        and signup_download_form.find("input", attrs={"type": "email"})
                        and "download" in page_text
                    )
                    is_interactive_download = (
                        "/download" in urlparse(url).path.lower()
                        and urlparse(source_page_url).path.lower() != urlparse(url).path.lower()
                    ) or bool(
                        interactive_download_form
                        and (
                            interactive_download_form.get("method", "get").lower() == "post"
                            or interactive_download_form.find("input", attrs={"name": "magn-ddaid"})
                            or interactive_download_form.find("input", attrs={"name": "magn-ddid"})
                        )
                    ) or is_signup_download_form

                    live_browser_available = self.use_browser and self.browser_driver.is_browser_open()
                    if is_auth_gate and not live_browser_available:
                        log(f"Skipping gated download page for {url}; login, subscription, or upgrade is required.")
                    elif self.use_browser and (is_interactive_download or is_auth_gate):
                        if is_auth_gate:
                            log(f"Page appears gated in HTTP response; retrying through the live authenticated browser: {source_page_url}")
                        browser_target_url = url if interactive_download_form else source_page_url
                        if browser_target_url in self._browser_processed_pages:
                            return None
                        self._browser_processed_pages.add(browser_target_url)
                        authentication = BrowserDownloader.has_authentication_cookies(self.cookies)
                        log(
                            "Launching automated browser session to intercept file download; "
                            f"authentication={str(authentication).lower()}."
                        )
                        try:
                            res = self.browser_driver.download_powerpoint_from_page(
                                browser_target_url,
                                log=log,
                                session_cookies=self.cookies,
                                session_cookie_domain=urlparse(browser_target_url).hostname,
                            )
                            if res:
                                name, content = res
                                return DiscoveredPowerPoint(
                                    title=name.replace(".pptx", "").replace("_", " ").title(),
                                    download_url=browser_target_url,
                                    source_page_url=source_page_url,
                                    format_type="pptx",
                                    content_bytes=content,
                                    file_size=len(content),
                                )
                        except Exception as b_err:
                            log(f"Browser automation error: {b_err}")
        except Exception as e:
            log(f"Error checking download candidate {url}: {e}")

        return None

    def _extract_title_from_url(self, url: str) -> str:
        path = urlparse(url).path
        filename = path.split("/")[-1]
        name = re.sub(r"\.(pptx|ppt|potx|ppsx)$", "", filename, flags=re.IGNORECASE)
        name = re.sub(r"[-_]+", " ", name).strip()
        return name.title() if name else "Presentation"

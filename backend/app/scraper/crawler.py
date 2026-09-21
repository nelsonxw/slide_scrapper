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
        consecutive_gate_threshold: int = 3,
        consecutive_empty_threshold: int = 3,
    ):
        self.target_url = target_url.strip()
        if not self.target_url.startswith(("http://", "https://")):
            self.target_url = "https://" + self.target_url

        self.max_crawl_pages = max_crawl_pages
        self.max_depth = max_depth
        self.use_browser = use_browser
        self.enable_pagination = enable_pagination
        self.consecutive_gate_threshold = consecutive_gate_threshold
        self.consecutive_empty_threshold = consecutive_empty_threshold
        self.browser_driver = browser_driver or BrowserDownloader()
        self._browser_processed_pages: set[str] = set()
        self.page_status: dict[str, str] = {}  # clean_url -> "not_empty" | "empty"
        self.visited_urls: set[str] = set()
        self._pagination_gate_tracking: dict[str, int] = {}  # Track consecutive gated pages per pagination pattern
        self._pagination_empty_tracking: dict[str, int] = {}  # Track consecutive empty pages per pagination pattern
        self._pagination_context_stack: list[str] = []  # Stack of pagination contexts for nested exploration
        self._pagination_file_discovery: dict[str, bool] = {}  # Track if files found during pagination exploration
        self._pagination_page_status: dict[str, bool] = {}  # Track individual pagination page completion status
        self._user_agent = user_agent
        self._custom_headers = custom_headers
        self._cookies = cookies
        self.headers = {
            "User-Agent": self._user_agent
            or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        if self._custom_headers:
            self.headers.update(self._custom_headers)

        self.cookies: list[Cookie] = self._normalize_cookies(self._cookies)

    def _clean_url(self, url: str) -> str:
        """Normalizes a URL by removing fragment and trailing slashes for status lookup."""
        return url.split("#")[0].rstrip("/")

    def get_page_status(self, url: str) -> str | None:
        """Returns 'not_empty', 'empty', or None if not yet evaluated."""
        return self.page_status.get(self._clean_url(url))

    def set_page_status(self, url: str, status: str) -> None:
        """Sets status for a page ('not_empty' or 'empty')."""
        self.page_status[self._clean_url(url)] = status

    def _extract_page_number(self, url: str) -> int:
        """Extracts integer page number from a pagination URL, defaulting to 1."""
        url_lower = url.lower()
        patterns = [
            r'/page/(\d+)',
            r'/page-(\d+)',
            r'[?&]page=(\d+)',
            r'[?&]p=(\d+)',
            r'/p(\d+)(?:/|$|\?)',
            r'/pg(\d+)(?:/|$|\?)',
        ]
        for pattern in patterns:
            m = re.search(pattern, url_lower)
            if m:
                try:
                    return int(m.group(1))
                except ValueError:
                    pass
        return 1

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

    def _get_pagination_base_url(self, url: str) -> str:
        """
        Extracts the base URL for a pagination page.
        For example: https://example.com/products/page/2/ -> https://example.com/products/page/
        This ensures all pages in the same pagination sequence share the same base URL.
        """
        pattern = self._get_pagination_pattern(url)
        if pattern:
            # Return the URL up to and including the pattern
            url_lower = url.lower()
            pattern_index = url_lower.find(pattern)
            if pattern_index != -1:
                return url_lower[:pattern_index + len(pattern)]
        # If no pattern found, return the URL without query string and fragment
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path.rsplit('/', 1)[0]}/"

    def _is_nested_pagination(self, url: str, current_context: str) -> bool:
        """
        Determines if a URL is a nested pagination page within the current context.
        For example, if current context is /page/ and URL is /page/4/, this is nested pagination.
        Only returns true if the URL is itself a pagination page, not just under the pagination base.
        """
        # First check if the URL is a pagination page at all
        if not self._is_pagination_link(url, current_context):
            return False
        
        url_base = self._get_pagination_base_url(url)
        current_base = self._get_pagination_base_url(current_context)
        
        # Check if it's in the same pagination sequence
        if url_base != current_base:
            return False
        
        # Check if it's a different pagination page (not the current one)
        return url != current_context

    def _get_pagination_pattern(self, url: str) -> str:
        """
        Extracts the base pagination pattern from a URL.
        For example: /page/2/ -> /page/, ?page=2 -> ?page=
        """
        url_lower = url.lower()
        
        # Match common pagination patterns and extract the base
        patterns = [
            (r'/page/\d+', '/page/'),
            (r'/page-\d+', '/page-'),
            (r'[?&]page=\d+', '?page='),
            (r'[?&]p=\d+', '?p='),
            (r'[?&]offset=\d+', '?offset='),
            (r'[?&]start=\d+', '?start='),
            (r'/p\d+', '/p'),
            (r'/pg\d+', '/pg'),
        ]
        
        for pattern, replacement in patterns:
            if re.search(pattern, url_lower):
                # Extract just the pattern part, not the full URL
                match = re.search(pattern, url_lower, re.IGNORECASE)
                if match:
                    return re.sub(r'\d+', '', match.group(0))
        
        return ""

    def _start_pagination_exploration(self, pagination_url: str) -> None:
        """
        Marks the start of exploring a pagination page's link tree.
        Uses a stack to handle nested pagination contexts.
        """
        base_url = self._get_pagination_base_url(pagination_url)
        self._pagination_context_stack.append(base_url)
        self._pagination_file_discovery[base_url] = False
        self._pagination_page_status[pagination_url] = 'exploring'

    def _record_file_discovery(self, current_url: str) -> None:
        """
        Records that a file was found during the current pagination exploration.
        Propagates the discovery up the entire context stack.
        """
        # Propagate file discovery to all contexts in the stack
        for base_url in self._pagination_context_stack:
            self._pagination_file_discovery[base_url] = True

    def _complete_pagination_exploration(self, pagination_url: str) -> bool:
        """
        Called when exploration of a pagination page's link tree is complete.
        Returns True if the pagination sequence should be skipped (no files found).
        """
        base_url = self._get_pagination_base_url(pagination_url)
        
        # Check if any files were found during this exploration
        had_files = self._pagination_file_discovery.get(base_url, False)
        
        # Mark this page as completed
        self._pagination_page_status[pagination_url] = 'completed'
        
        if not had_files:
            # No files found - increment empty counter
            self._pagination_empty_tracking[base_url] = self._pagination_empty_tracking.get(base_url, 0) + 1
            should_skip = self._pagination_empty_tracking[base_url] >= self.consecutive_empty_threshold
        else:
            # Files found - reset empty counter
            self._pagination_empty_tracking[base_url] = 0
            should_skip = False
        
        # Pop this context from the stack
        if self._pagination_context_stack and self._pagination_context_stack[-1] == base_url:
            self._pagination_context_stack.pop()
        
        # Clean up file discovery for this context
        if base_url in self._pagination_file_discovery:
            del self._pagination_file_discovery[base_url]
        
        return should_skip

    def _should_skip_pagination(self, url: str, was_gated: bool) -> bool:
        """
        Determines if we should skip a pagination URL based on consecutive gated pages.
        Note: Empty page detection is now handled after full exploration via _complete_pagination_exploration.
        """
        if not self.enable_pagination:
            return False
        
        pattern = self._get_pagination_pattern(url)
        if not pattern:
            return False
        
        should_skip = False
        
        # Check consecutive gated pages (immediate decision)
        if was_gated:
            self._pagination_gate_tracking[pattern] = self._pagination_gate_tracking.get(pattern, 0) + 1
            if self._pagination_gate_tracking[pattern] >= self.consecutive_gate_threshold:
                should_skip = True
        else:
            # Reset gate counter if we found a successful page
            self._pagination_gate_tracking[pattern] = 0
        
        return should_skip

    def _is_pagination_link(self, url: str, current_url: str) -> bool:
        """
        Detects if a URL is a pagination link based on common patterns.
        Ensures the pagination link belongs to the same path sequence as current_url.
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

        has_pattern = False
        for pattern in pagination_patterns:
            if re.search(pattern, url_lower):
                has_pattern = True
                break

        # Check for next/prev buttons in same path structure
        if not has_pattern:
            parsed_current = urlparse(current_lower)
            parsed_url = urlparse(url_lower)
            if (parsed_current.hostname == parsed_url.hostname and 
                parsed_url.path.startswith(parsed_current.path.rstrip('/'))):
                current_path_parts = parsed_current.path.rstrip('/').split('/')
                url_path_parts = parsed_url.path.rstrip('/').split('/')
                if (len(url_path_parts) == len(current_path_parts) + 1 and
                    url_path_parts[-1].isdigit()):
                    has_pattern = True

        if not has_pattern:
            return False

        # Verify that the URL belongs to the same section/sequence as current_url or target_url
        def _strip_pagination_segments(u: str) -> str:
            u_clean = u.split('?')[0].split('#')[0].rstrip('/')
            u_clean = re.sub(r'/page/\d+', '', u_clean, flags=re.IGNORECASE)
            u_clean = re.sub(r'/page-\d+', '', u_clean, flags=re.IGNORECASE)
            u_clean = re.sub(r'/p\d+$', '', u_clean, flags=re.IGNORECASE)
            u_clean = re.sub(r'/pg\d+$', '', u_clean, flags=re.IGNORECASE)
            return u_clean.rstrip('/')

        url_base = _strip_pagination_segments(url_lower)
        current_base = _strip_pagination_segments(current_lower)
        target_base = _strip_pagination_segments(self.target_url.lower())

        if url_base == current_base:
            return True

        parsed_tgt = urlparse(target_base)
        parsed_url = urlparse(url_base)

        if parsed_tgt.hostname == parsed_url.hostname:
            if parsed_tgt.path in ('', '/'):
                return True
            if url_base.startswith(target_base):
                return True
            return False

        # In unit tests or cross-host scenarios
        return url_base == current_base or parsed_url.hostname != urlparse(current_base).hostname

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

            sub_url_lower = sub_url.lower()

            # 1. CRITICAL: Never follow logout or session-destroying URLs!
            if any(k in sub_url_lower for k in (
                "action=logout", "logout", "signout", "log-out", "sign-out", "wp-login.php"
            )):
                continue

            # 2. Skip account management, checkout, and admin pages
            if any(k in parsed_sub.path.lower() for k in (
                "/account", "/wp-admin", "/checkout", "/cart", "/billing", "/plans-upgrade"
            )):
                continue

            # 3. Skip static legal / utility pages that never contain slide templates
            if any(k in parsed_sub.path.lower() for k in (
                "/privacy-policy", "/terms-use", "/terms-of-use", "/dmca"
            )):
                continue
            
            # Separate pagination links from regular links if pagination is enabled
            if self.enable_pagination and self._is_pagination_link(sub_url, current_url):
                pagination_links.append(sub_url)
            else:
                regular_links.append(sub_url)

        # Prioritize child links that match the target path section
        target_path = urlparse(self.target_url).path.rstrip('/')
        if target_path and target_path != '/':
            target_prefix = target_path.lower()
            in_section_links = []
            other_links = []
            for r_link in regular_links:
                r_path = urlparse(r_link).path.lower()
                if r_path.startswith(target_prefix):
                    in_section_links.append(r_link)
                else:
                    other_links.append(r_link)
            regular_links = in_section_links + other_links
        
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
        pagination_queue: list[tuple[int, str]] = []
        enqueued_pagination_urls: set[str] = set()

        def enqueue_pagination_link(p_url: str):
            if not self.enable_pagination:
                return
            clean_p = self._clean_url(p_url)
            if clean_p not in enqueued_pagination_urls:
                enqueued_pagination_urls.add(clean_p)
                p_num = self._extract_page_number(p_url)
                pagination_queue.append((p_num, p_url))
                pagination_queue.sort(key=lambda x: x[0])
                log(f"Enqueued pagination page #{p_num}: {p_url}")

        enqueue_pagination_link(self.target_url)

        with self.browser_driver.connect_live_browser() as browser:
            if not browser.contexts:
                log("Live CDP browser has no context; no rendered pages can be crawled.")
                return []

            context = browser.contexts[0]
            page = context.pages[0] if context.pages else context.new_page()
            page.set_default_timeout(5000)
            page.set_default_navigation_timeout(10000)
            log("Active Chrome session detected. Crawling rendered pages through live CDP.")

            def evaluate_live_page(page_url: str, current_depth: int, max_depth_limit: int) -> bool:
                if should_stop and should_stop():
                    return False

                clean = self._clean_url(page_url)
                existing_status = self.get_page_status(clean)
                if existing_status is not None:
                    log(f"Skipping already evaluated page ({existing_status}): {page_url}")
                    return existing_status == "not_empty"

                if len(self.visited_urls) >= self.max_crawl_pages:
                    log(f"Reached max crawl pages limit ({self.max_crawl_pages}).")
                    return False

                self.visited_urls.add(clean)
                log(f"Crawling rendered page ({len(self.visited_urls)}/{self.max_crawl_pages}, depth={current_depth}/{max_depth_limit}): {page_url}")

                try:
                    page.goto(page_url, wait_until="domcontentloaded", timeout=10000)
                    page.wait_for_timeout(500)
                    rendered_html = page.content()
                except Exception as error:
                    log(f"Failed to render {page_url} in live browser: {error}")
                    self.set_page_status(page_url, "empty")
                    return False

                soup = BeautifulSoup(rendered_html, "html.parser")
                auth_gate_detected = self.browser_driver.page_requires_authentication(page)
                authentication = BrowserDownloader.has_authentication_cookies(context.cookies())
                was_gated = auth_gate_detected and not authentication

                if was_gated:
                    log(f"Gated page detected without authentication on {page.url}.")

                candidates = self._extract_download_candidates(soup, page.url)
                has_download_control = self.browser_driver.has_visible_download_control(page)

                files_saved_here = 0
                if candidates and has_download_control and page.url not in self._browser_processed_pages and not was_gated:
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
                            source_page_url=page_url,
                            format_type="pptx",
                            content_bytes=content,
                            file_size=len(content),
                        )
                        discovered_items.append(item)
                        files_saved_here += 1
                        if on_found:
                            on_found(item)

                regular_links, pagination_links = self._extract_internal_links(soup, page.url, root_hostname)
                for pag_url in pagination_links:
                    enqueue_pagination_link(pag_url)

                if files_saved_here > 0:
                    self.set_page_status(page_url, "not_empty")
                    log(f"📊 STATUS: {page_url} is NOT EMPTY ({files_saved_here} file(s) captured directly)")
                    return True

                has_child_files = False
                if current_depth < max_depth_limit and regular_links and not was_gated:
                    log(f"Exploring {len(regular_links)} linked pages from {page_url} (depth={current_depth + 1}/{max_depth_limit})...")
                    for sub_url in regular_links:
                        if should_stop and should_stop():
                            break
                        if len(self.visited_urls) >= self.max_crawl_pages:
                            break

                        sub_clean = self._clean_url(sub_url)
                        sub_status = self.get_page_status(sub_clean)
                        if sub_status == "not_empty":
                            has_child_files = True
                            continue
                        elif sub_status == "empty":
                            continue

                        child_result = evaluate_live_page(sub_url, current_depth + 1, max_depth_limit)
                        if child_result:
                            has_child_files = True

                if has_child_files:
                    self.set_page_status(page_url, "not_empty")
                    log(f"📊 STATUS: {page_url} is NOT EMPTY (downloaded from linked pages)")
                    return True
                else:
                    self.set_page_status(page_url, "empty")
                    log(f"📊 STATUS: {page_url} is EMPTY (no files captured from page or linked pages)")
                    return False

            consecutive_empty_pages = 0

            while pagination_queue and len(self.visited_urls) < self.max_crawl_pages:
                if should_stop and should_stop():
                    log("Crawling stopped by user.")
                    break

                page_num, page_url = pagination_queue.pop(0)
                clean_p_url = self._clean_url(page_url)
                if self.get_page_status(clean_p_url) is not None:
                    continue

                log(f"--- Processing Priority Pagination Page #{page_num}: {page_url} ---")
                is_not_empty = evaluate_live_page(page_url, current_depth=0, max_depth_limit=self.max_depth)

                if is_not_empty:
                    consecutive_empty_pages = 0
                    log(f"Pagination page #{page_num} is NOT EMPTY. Consecutive empty count reset to 0.")
                else:
                    consecutive_empty_pages += 1
                    log(f"Pagination page #{page_num} is EMPTY ({consecutive_empty_pages}/{self.consecutive_empty_threshold}).")
                    if consecutive_empty_pages >= self.consecutive_empty_threshold:
                        log(f"Reached {self.consecutive_empty_threshold} consecutive empty pagination pages. Skipping remaining pagination sequence.")
                        break

        log(f"Live browser crawl complete. Discovered {len(discovered_items)} valid PowerPoint presentations across {len(self.visited_urls)} pages.")
        return discovered_items

    def crawl_and_extract(
        self,
        on_log: Callable[[str], None] | None = None,
        on_found: Callable[[DiscoveredPowerPoint], None] | None = None,
        should_stop: Callable[[], bool] | None = None,
    ) -> list[DiscoveredPowerPoint]:
        """
        Revamped crawling pipeline:
        1. Checks empty/non-empty status before crawling any page. If already determined, skips immediately.
        2. Prioritizes pagination pages as the primary catalog sequence (Page 1 -> Page 2 -> Page 3...).
        3. On each page, checks for direct download candidates first. If captured, marks page 'not_empty'.
           If no direct files captured, explores linked pages up to max_depth. If >=1 file captured from
           linked pages, marks page 'not_empty'; otherwise marks page 'empty'.
        4. When consecutive pagination pages are flagged 'empty' up to consecutive_empty_threshold,
           skips remaining pagination sequence.
        """
        def log(msg: str):
            if on_log:
                on_log(msg)

        parsed_root = urlparse(self.target_url)
        root_hostname = (parsed_root.hostname or "").lower()

        log(f"Starting crawl on: {self.target_url} (Domain: {root_hostname}, max_depth={self.max_depth}, max_pages={self.max_crawl_pages})")

        # Direct check if user provided a direct PPTX download URL
        if is_powerpoint_url_or_header(self.target_url):
            log("Target URL appears to be a direct PowerPoint link. Fetching directly...")
            item = self._fetch_and_validate(self.target_url, self.target_url, "Direct Presentation", log)
            if item:
                self.set_page_status(self.target_url, "not_empty")
                if on_found:
                    on_found(item)
                return [item]
            self.set_page_status(self.target_url, "empty")
            return []

        self._browser_processed_pages.clear()
        if self.use_browser and self.browser_driver.is_browser_open():
            return self._crawl_via_live_browser(
                root_hostname,
                on_log,
                on_found,
                should_stop,
            )

        discovered_items: list[DiscoveredPowerPoint] = []
        seen_download_urls: set[str] = set()

        # Priority queue for pagination pages: list of (page_num, url)
        pagination_queue: list[tuple[int, str]] = []
        enqueued_pagination_urls: set[str] = set()

        def enqueue_pagination_link(p_url: str):
            if not self.enable_pagination:
                return
            clean_p = self._clean_url(p_url)
            if clean_p not in enqueued_pagination_urls:
                enqueued_pagination_urls.add(clean_p)
                p_num = self._extract_page_number(p_url)
                pagination_queue.append((p_num, p_url))
                pagination_queue.sort(key=lambda x: x[0])
                log(f"Enqueued pagination page #{p_num}: {p_url}")

        # Seed pagination queue with target URL
        enqueue_pagination_link(self.target_url)

        with httpx.Client(
            headers=self.headers,
            timeout=5.0,
            follow_redirects=True,
            verify=False,
        ) as client:
            self._configure_client_cookies(client)

            def evaluate_page(page_url: str, current_depth: int, max_depth_limit: int) -> bool:
                """
                Evaluates a page up to max_depth_limit.
                Returns True if at least 1 file was saved from this page or its allowed linked pages.
                Sets page_status to 'not_empty' if True, else 'empty'.
                """
                if should_stop and should_stop():
                    return False

                clean = self._clean_url(page_url)

                # Rule 2: Check status before crawling. If already determined, skip!
                existing_status = self.get_page_status(clean)
                if existing_status is not None:
                    log(f"Skipping already evaluated page ({existing_status}): {page_url}")
                    return existing_status == "not_empty"

                if len(self.visited_urls) >= self.max_crawl_pages:
                    log(f"Reached max crawl pages limit ({self.max_crawl_pages}).")
                    return False

                self.visited_urls.add(clean)
                log(f"Crawling page ({len(self.visited_urls)}/{self.max_crawl_pages}, depth={current_depth}/{max_depth_limit}): {page_url}")

                try:
                    resp = client.get(page_url)
                except Exception as e:
                    log(f"Failed to fetch {page_url}: {e}")
                    self.set_page_status(page_url, "empty")
                    return False

                if resp.status_code != 200:
                    log(f"HTTP {resp.status_code} on {page_url}")
                    self.set_page_status(page_url, "empty")
                    return False

                content_type = resp.headers.get("content-type", "").lower()

                # Direct binary presentation check
                is_ppt, fmt = is_powerpoint_content(resp.content)
                if is_ppt:
                    if page_url not in seen_download_urls:
                        seen_download_urls.add(page_url)
                        title = self._extract_title_from_url(page_url)
                        item = DiscoveredPowerPoint(
                            title=title,
                            download_url=page_url,
                            source_page_url=page_url,
                            format_type=fmt,
                            content_bytes=resp.content,
                            file_size=len(resp.content),
                        )
                        log(f"Found direct PowerPoint file: {title} ({fmt.upper()}, {len(resp.content) // 1024} KB)")
                        discovered_items.append(item)
                        if on_found:
                            on_found(item)
                    self.set_page_status(page_url, "not_empty")
                    log(f"📊 STATUS: {page_url} is NOT EMPTY")
                    return True

                if "html" not in content_type and not page_url.endswith((".html", ".htm", "/")):
                    self.set_page_status(page_url, "empty")
                    return False

                soup = BeautifulSoup(resp.text, "html.parser")

                # 1. Check if page has any direct download candidate
                candidates = self._extract_download_candidates(soup, page_url)
                files_saved_here = 0
                for dl_url, dl_title in candidates:
                    if dl_url in seen_download_urls:
                        continue
                    seen_download_urls.add(dl_url)
                    log(f"Inspecting download candidate: {dl_title} -> {dl_url}")
                    item = self._fetch_and_validate(dl_url, page_url, dl_title, log, client=client)
                    if item:
                        discovered_items.append(item)
                        files_saved_here += 1
                        if on_found:
                            on_found(item)

                # Extract internal links & pagination links
                regular_links, pagination_links = self._extract_internal_links(soup, page_url, root_hostname)
                for pag_url in pagination_links:
                    enqueue_pagination_link(pag_url)

                # If direct files were captured:
                if files_saved_here > 0:
                    self.set_page_status(page_url, "not_empty")
                    log(f"📊 STATUS: {page_url} is NOT EMPTY ({files_saved_here} file(s) captured directly)")
                    return True

                # If no direct file, explore linked pages up to max_depth_limit
                has_child_files = False
                if current_depth < max_depth_limit and regular_links:
                    log(f"Exploring {len(regular_links)} linked pages from {page_url} (depth={current_depth + 1}/{max_depth_limit})...")
                    for sub_url in regular_links:
                        if should_stop and should_stop():
                            break
                        if len(self.visited_urls) >= self.max_crawl_pages:
                            break

                        sub_clean = self._clean_url(sub_url)
                        sub_status = self.get_page_status(sub_clean)
                        if sub_status == "not_empty":
                            has_child_files = True
                            continue
                        elif sub_status == "empty":
                            continue

                        child_result = evaluate_page(sub_url, current_depth + 1, max_depth_limit)
                        if child_result:
                            has_child_files = True

                if has_child_files:
                    self.set_page_status(page_url, "not_empty")
                    log(f"📊 STATUS: {page_url} is NOT EMPTY (downloaded from linked pages)")
                    return True
                else:
                    self.set_page_status(page_url, "empty")
                    log(f"📊 STATUS: {page_url} is EMPTY (no files captured from page or linked pages)")
                    return False

            consecutive_empty_pages = 0

            # Priority 1: Process pagination queue in order (Page 1, Page 2, Page 3, ...)
            while pagination_queue and len(self.visited_urls) < self.max_crawl_pages:
                if should_stop and should_stop():
                    log("Crawling stopped by user.")
                    break

                page_num, page_url = pagination_queue.pop(0)
                clean_p_url = self._clean_url(page_url)
                if self.get_page_status(clean_p_url) is not None:
                    continue

                log(f"--- Processing Priority Pagination Page #{page_num}: {page_url} ---")
                is_not_empty = evaluate_page(page_url, current_depth=0, max_depth_limit=self.max_depth)

                if is_not_empty:
                    consecutive_empty_pages = 0
                    log(f"Pagination page #{page_num} is NOT EMPTY. Consecutive empty count reset to 0.")
                else:
                    consecutive_empty_pages += 1
                    log(f"Pagination page #{page_num} is EMPTY ({consecutive_empty_pages}/{self.consecutive_empty_threshold}).")
                    if consecutive_empty_pages >= self.consecutive_empty_threshold:
                        log(f"Reached {self.consecutive_empty_threshold} consecutive empty pagination pages. Skipping remaining pagination sequence.")
                        break

        log(f"Crawling complete. Discovered {len(discovered_items)} valid PowerPoint presentations across {len(self.visited_urls)} pages.")
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

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
        cookies: str | dict[str, str] | None = None,
        custom_headers: dict[str, str] | None = None,
        use_browser: bool = True,
    ):
        self.target_url = target_url.strip()
        if not self.target_url.startswith(("http://", "https://")):
            self.target_url = "https://" + self.target_url

        self.max_crawl_pages = max_crawl_pages
        self.max_depth = max_depth
        self.use_browser = use_browser
        self.headers = {
            "User-Agent": user_agent
            or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        if custom_headers:
            self.headers.update(custom_headers)

        self.cookies: dict[str, str] = {}
        if isinstance(cookies, str) and cookies.strip():
            clean_cookie_str = cookies.replace("Cookie:", "").replace("cookie:", "").strip()
            for item in re.split(r"[;\n\r]+", clean_cookie_str):
                if "=" in item:
                    k, v = item.strip().split("=", 1)
                    if k.strip():
                        self.cookies[k.strip()] = v.strip()
        elif isinstance(cookies, dict):
            self.cookies = cookies

    def _is_download_element(self, tag: BeautifulSoup, href_or_action: str) -> bool:
        """
        Detects if a tag (<a>, <button>, <form>, <input>, etc.) represents a download button or direct PowerPoint download link.
        """
        href_lower = href_or_action.lower().split("?")[0]

        # Ignore Google Docs/Slides, Canva, social media, and non-PowerPoint third-party services
        if any(ignored in href_lower for ignored in ["docs.google.com", "slides.google.com", "canva.com", "linkedin.com", "twitter.com", "facebook.com", "pinterest.com"]):
            return False

        # Exclude static assets
        if any(
            href_lower.endswith(ext)
            for ext in [".css", ".js", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".mp4", ".mp3", ".pdf", ".zip"]
        ):
            return False

        # Exclude pure category/tag/blog browsing urls
        if any(
            p in href_lower
            for p in ["/category/", "/tag/", "/author/", "/blog/", "/terms/", "/privacy/", "/contact/", "/about/"]
        ):
            # Unless the URL explicitly targets a pptx file or download endpoint
            if not href_lower.endswith((".pptx", ".ppt", ".potx", ".ppsx")) and "download" not in href_lower:
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
        all_text = f"{text} {title_attr} {aria_label} {classes} {elem_id} {tag_value}"

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
        root_domain = parsed_root.netloc.lower()

        log(f"Starting crawl on: {self.target_url} (Domain: {root_domain})")

        # Direct check if user provided a direct PPTX download URL
        if is_powerpoint_url_or_header(self.target_url):
            log(f"Target URL appears to be a direct PowerPoint link. Fetching directly...")
            item = self._fetch_and_validate(self.target_url, self.target_url, "Direct Presentation", log)
            if item:
                if on_found:
                    on_found(item)
                return [item]

        discovered_items: list[DiscoveredPowerPoint] = []
        visited_pages: set[str] = set()
        seen_download_urls: set[str] = set()

        queue: collections.deque[tuple[str, int]] = collections.deque([(self.target_url, 0)])

        with httpx.Client(
            headers=self.headers,
            cookies=self.cookies,
            timeout=20.0,
            follow_redirects=True,
            verify=False,
        ) as client:
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

                    if self._is_download_element(tag, href):
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
                    parsed_initial = urlparse(self.target_url)
                    initial_path = parsed_initial.path.rstrip("/")

                    for a in soup.find_all("a", href=True):
                        href = a["href"].strip()
                        if not href or href.startswith(("javascript:", "mailto:", "tel:", "#")):
                            continue
                        sub_url = urljoin(current_url, href)
                        parsed_sub = urlparse(sub_url)

                        # Crawl within same root domain
                        if parsed_sub.netloc.lower() == root_domain:
                            sub_path = parsed_sub.path.lower().rstrip("/")

                            # Exclude homepage if initial URL was a specific sub-page
                            if initial_path and initial_path != "" and (sub_path == "" or sub_path == "/"):
                                continue

                            # Exclude account, auth, pricing, legal, and utility pages
                            excluded_paths = [
                                "/account", "/login", "/signup", "/register", "/plans", "/pricing",
                                "/cart", "/checkout", "/privacy", "/terms", "/contact", "/about",
                                "/faq", "/author", "/user", "/wp-login", "/wp-admin", "/cdn-cgi",
                            ]
                            if any(sub_path.startswith(exp) or f"{exp}/" in sub_path for exp in excluded_paths):
                                continue

                            # Skip non-HTML static assets
                            if not sub_path.endswith(
                                (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".pdf", ".zip", ".css", ".js", ".mp4", ".mp3", ".json", ".xml")
                            ):
                                clean_sub = sub_url.split("#")[0].rstrip("/")
                                if clean_sub not in visited_pages:
                                    queue.append((sub_url, depth + 1))

        log(f"Crawling complete. Discovered {len(discovered_items)} valid PowerPoint presentations across {len(visited_pages)} pages.")
        return discovered_items

    def _fetch_url(self, url: str, client: httpx.Client | None = None) -> httpx.Response | None:
        """Helper to fetch a URL safely using existing client or temporary client."""
        try:
            if client:
                return client.get(url, headers=self.headers, timeout=30.0, follow_redirects=True)
            with httpx.Client(headers=self.headers, cookies=self.cookies, timeout=30.0, follow_redirects=True, verify=False) as temp_client:
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
                    is_gated_form = (
                        any(g in str(resp.url).lower() for g in ["/signup", "/login", "/register", "/plans"])
                        or "create free account" in page_text
                        or "rcp_user_pass" in page_text
                        or "complete the form" in page_text
                    )

                    if is_gated_form:
                        log(f"Detected interactive download form on {source_page_url}.")
                        if self.use_browser:
                            log(f"Launching automated browser session to intercept file download...")
                            try:
                                b_driver = BrowserDownloader()
                                res = b_driver.download_powerpoint_from_page(source_page_url, log=log)
                                if res:
                                    name, content = res
                                    return DiscoveredPowerPoint(
                                        title=name.replace(".pptx", "").replace("_", " ").title(),
                                        download_url=source_page_url,
                                        source_page_url=source_page_url,
                                        format_type="pptx",
                                        content_bytes=content,
                                        file_size=len(content),
                                    )
                            except Exception as b_err:
                                log(f"Browser automation error: {b_err}")
                        else:
                            log(f"Download endpoint ({url}) requires an active user login/signup session.")
        except Exception as e:
            log(f"Error checking download candidate {url}: {e}")

        return None

    def _extract_title_from_url(self, url: str) -> str:
        path = urlparse(url).path
        filename = path.split("/")[-1]
        name = re.sub(r"\.(pptx|ppt|potx|ppsx)$", "", filename, flags=re.IGNORECASE)
        name = re.sub(r"[-_]+", " ", name).strip()
        return name.title() if name else "Presentation"

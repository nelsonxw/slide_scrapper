"""Tests for generic target-site crawling and download control detection."""
import unittest
from unittest.mock import Mock

import httpx
from bs4 import BeautifulSoup

from app.scraper.browser_driver import BrowserDownloader
from app.scraper.crawler import SiteScraper


class TestCrawlerDetection(unittest.TestCase):
    def setUp(self):
        self.scraper = SiteScraper("https://example.com/catalog", use_browser=False)

    def test_ignores_auth_phrase_in_template_listing_copy(self):
        response = httpx.Response(
            200,
            request=httpx.Request("GET", "https://example.com/templates"),
            content=b"<article>Free account to download this template</article>",
        )
        self.assertFalse(self.scraper._response_requires_authentication(response))

    def test_marks_login_form_response_as_unauthenticated(self):
        response = httpx.Response(
            200,
            request=httpx.Request("GET", "https://example.com/templates"),
            content=b'<form action="/account/login/"><input type="password"><button>Log in to download</button></form>',
        )
        scraper = SiteScraper(
            "https://example.com/templates",
            cookies=[{"name": "session", "value": "authenticated", "domain": "example.com", "path": "/"}],
            use_browser=False,
        )

        self.assertTrue(scraper._response_requires_authentication(response))

    def test_detects_powerpoint_link_on_any_site(self):
        tag = BeautifulSoup('<a href="https://cdn.example.net/files/deck.pptx">Open file</a>', "html.parser").a
        self.assertTrue(self.scraper._is_download_element(tag, tag["href"]))

    def test_detects_generic_download_button(self):
        tag = BeautifulSoup('<button data-url="/files/export">Download presentation</button>', "html.parser").button
        self.assertTrue(self.scraper._is_download_element(tag, tag["data-url"]))

    def test_does_not_treat_regular_navigation_as_download(self):
        tag = BeautifulSoup('<a href="/catalog/item-1">View item</a>', "html.parser").a
        self.assertFalse(self.scraper._is_download_element(tag, tag["href"]))

    def test_view_and_download_link_is_allowed_as_candidate(self):
        tag = BeautifulSoup(
            '<a href="/catalog/template-1">View &amp; Download Template</a>',
            "html.parser",
        ).a
        self.assertTrue(self.scraper._is_download_element(tag, tag["href"]))

    def test_does_not_apply_site_specific_url_rules(self):
        tag = BeautifulSoup('<a href="https://docs.google.com/download?id=123">Download</a>', "html.parser").a
        self.assertTrue(self.scraper._is_download_element(tag, tag["href"]))

    def test_detects_download_form_message_in_hidden_input(self):
        tag = BeautifulSoup(
            '<form action="/account/signup/">'
            '<input type="hidden" value="Please complete the form in order to download">'
            '<input type="email">'
            '<input type="submit" value="Continue">'
            '</form>',
            "html.parser",
        ).form
        self.assertTrue(self.scraper._is_download_element(tag, tag["action"]))

    def test_ignores_analytics_cookies_as_authentication(self):
        self.assertFalse(
            BrowserDownloader.has_authentication_cookies([
                {"name": "_ga", "value": "analytics"},
                {"name": "g_state", "value": "state"},
                {"name": "magn_hellobar_session", "value": "session"},
            ])
        )

    def test_recognizes_login_cookie_as_authentication(self):
        self.assertTrue(
            BrowserDownloader.has_authentication_cookies([
                {"name": "wordpress_logged_in_abc", "value": "authenticated"},
            ])
        )

    def test_merges_persisted_auth_cookie_with_current_profile_cookies(self):
        cookies = BrowserDownloader._merge_session_cookies(
            [{"name": "wordpress_logged_in_abc", "value": "authenticated", "domain": ".example.com", "path": "/"}],
            [{"name": "_ga", "value": "analytics", "domain": ".example.com", "path": "/"}],
        )

        self.assertTrue(BrowserDownloader.has_authentication_cookies(cookies))
        self.assertEqual(len(cookies), 2)

    def test_filters_saved_cookies_to_target_host(self):
        browser = BrowserDownloader()
        cookies = browser._filter_session_cookies(
            [
                {"name": "session", "value": "target", "domain": ".example.com", "path": "/"},
                {"name": "session", "value": "other", "domain": ".other.example", "path": "/"},
            ],
            "catalog.example.com",
        )

        self.assertEqual([cookie["value"] for cookie in cookies], ["target"])

    def test_preserves_structured_cookie_metadata_for_httpx(self):
        scraper = SiteScraper(
            "https://example.com/catalog",
            cookies=[
                {
                    "name": "session",
                    "value": "authenticated",
                    "domain": ".example.com",
                    "path": "/",
                }
            ],
            use_browser=False,
        )
        with httpx.Client() as client:
            scraper._configure_client_cookies(client)
            request = client.build_request("GET", "https://example.com/catalog")

        self.assertIn("session=authenticated", request.headers["Cookie"])

    def test_extracts_download_candidate_from_rendered_html(self):
        soup = BeautifulSoup(
            '<form action="/download/"><input type="submit" value="Download PowerPoint"></form>',
            "html.parser",
        )
        candidates = self.scraper._extract_download_candidates(soup, "https://example.com/template/")

        self.assertEqual(
            [candidate[0] for candidate in candidates],
            ["https://example.com/download/", "https://example.com/download/"],
        )
        self.assertEqual({candidate[1] for candidate in candidates}, {"Presentation"})

    def test_captures_page_storage_without_exposing_values(self):
        page = Mock()
        page.evaluate.side_effect = [
            "https://example.com",
            {"access_token": "secret"},
            {"csrf": "nonce"},
        ]

        storage = BrowserDownloader().capture_page_storage(page)

        self.assertEqual(storage["origin"], "https://example.com")
        self.assertEqual(storage["local"], {"access_token": "secret"})
        self.assertEqual(storage["session"], {"csrf": "nonce"})
        self.assertEqual(page.evaluate.call_count, 3)


if __name__ == "__main__":
    unittest.main()

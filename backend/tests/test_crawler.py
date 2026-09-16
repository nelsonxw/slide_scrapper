"""Tests for generic target-site crawling and download control detection."""
import unittest

from bs4 import BeautifulSoup

from app.scraper.crawler import SiteScraper


class TestCrawlerDetection(unittest.TestCase):
    def setUp(self):
        self.scraper = SiteScraper("https://example.com/catalog", use_browser=False)

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


if __name__ == "__main__":
    unittest.main()

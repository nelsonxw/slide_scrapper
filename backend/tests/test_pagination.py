"""Test pagination detection in the crawler."""
from app.scraper.crawler import SiteScraper


def test_pagination_detection():
    """Test that pagination links are correctly identified."""
    scraper = SiteScraper("https://example.com")
    
    # Test various pagination patterns
    test_cases = [
        ("https://slidemodel.com/free-powerpoint-templates/page/2/", True),
        ("https://slidemodel.com/free-powerpoint-templates/page/3/", True),
        ("https://example.com/products?page=2", True),
        ("https://example.com/products?p=3", True),
        ("https://example.com/products?offset=20", True),
        ("https://example.com/products?start=20", True),
        ("https://example.com/products/p2", True),
        ("https://example.com/products/pg3", True),
        ("https://example.com/products/page-2", True),
        ("https://slidemodel.com/free-powerpoint-templates/3-ring-milestone-infographic-powerpoint-template/", False),
        ("https://example.com/products/item-1", False),
        ("https://example.com/about", False),
    ]
    
    for url, expected_is_pagination in test_cases:
        result = scraper._is_pagination_link(url, "https://slidemodel.com/free-powerpoint-templates/")
        assert result == expected_is_pagination, f"Failed for {url}: expected {expected_is_pagination}, got {result}"
    
    print("All pagination detection tests passed!")


def test_pagination_link_extraction():
    """Test that pagination links are separated from regular links."""
    from bs4 import BeautifulSoup
    
    scraper = SiteScraper("https://slidemodel.com/free-powerpoint-templates/")
    
    html = """
    <html>
    <body>
        <a href="/free-powerpoint-templates/page/2/">Next Page</a>
        <a href="/free-powerpoint-templates/page/3/">Page 3</a>
        <a href="/free-powerpoint-templates/template-1/">Template 1</a>
        <a href="/free-powerpoint-templates/template-2/">Template 2</a>
        <a href="/about">About</a>
    </body>
    </html>
    """
    
    soup = BeautifulSoup(html, "html.parser")
    regular_links, pagination_links = scraper._extract_internal_links(
        soup, 
        "https://slidemodel.com/free-powerpoint-templates/",
        "slidemodel.com"
    )
    
    assert len(pagination_links) == 2, f"Expected 2 pagination links, got {len(pagination_links)}"
    assert len(regular_links) == 3, f"Expected 3 regular links, got {len(regular_links)}"
    
    # Check that pagination links are correctly identified
    assert any("page/2" in url for url in pagination_links), "Should contain page/2"
    assert any("page/3" in url for url in pagination_links), "Should contain page/3"
    
    print("Pagination link extraction test passed!")


if __name__ == "__main__":
    test_pagination_detection()
    test_pagination_link_extraction()
    print("All pagination tests passed successfully!")
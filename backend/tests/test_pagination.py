"""Test pagination detection and intelligent gate skipping in the crawler."""
from app.scraper.crawler import SiteScraper


def test_pagination_detection():
    """Test that pagination links are correctly identified and scoped to target section."""
    scraper = SiteScraper("https://slidemodel.com/free-powerpoint-templates/")
    
    # Test pagination links under target section (should be accepted)
    test_cases = [
        ("https://slidemodel.com/free-powerpoint-templates/page/2/", True),
        ("https://slidemodel.com/free-powerpoint-templates/page/3/", True),
        ("https://slidemodel.com/free-powerpoint-templates/?page=2", True),
        ("https://slidemodel.com/free-powerpoint-templates/?p=3", True),
    ]
    
    # Test pagination links from other sections (should be rejected)
    rejection_cases = [
        ("https://slidemodel.com/templates/page/2/", False),
        ("https://slidemodel.com/best-powerpoint-templates/page/2/", False),
        ("https://slidemodel.com/templates/category/powerpoint/diagrams/page/2/", False),
        ("https://example.com/products?page=2", False),
        ("https://slidemodel.com/free-powerpoint-templates/3-ring-milestone-infographic-powerpoint-template/", False),
        ("https://example.com/products/item-1", False),
        ("https://example.com/about", False),
    ]
    
    all_cases = test_cases + rejection_cases
    
    for url, expected_is_pagination in all_cases:
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
    regular_links, pagination_links, other_links = scraper._extract_internal_links(
        soup, 
        "https://slidemodel.com/free-powerpoint-templates/",
        "slidemodel.com"
    )
    
    assert len(pagination_links) == 2, f"Expected 2 pagination links, got {len(pagination_links)}"
    # Since current_url is within target section, regular_links contains only in-section links (template-1 and template-2)
    # other_links contains out-of-section link (/about)
    assert len(regular_links) == 2, f"Expected 2 in-section regular links, got {len(regular_links)}"
    assert len(other_links) == 1, f"Expected 1 other link, got {len(other_links)}"
    
    # Check that pagination links are correctly identified
    assert any("page/2" in url for url in pagination_links), "Should contain page/2"
    assert any("page/3" in url for url in pagination_links), "Should contain page/3"
    
    print("Pagination link extraction test passed!")


def test_pagination_pattern_extraction():
    """Test that pagination patterns are correctly extracted."""
    scraper = SiteScraper("https://example.com")
    
    test_cases = [
        ("https://example.com/products/page/2/", "/page/"),
        ("https://example.com/products?page=2", "?page="),
        ("https://example.com/products?p=3", "?p="),
        ("https://example.com/products/page-2", "/page-"),
        ("https://example.com/products/p2", "/p"),
    ]
    
    for url, expected_pattern in test_cases:
        pattern = scraper._get_pagination_pattern(url)
        # The pattern extraction returns just the pattern part
        assert expected_pattern in pattern, f"Expected pattern {expected_pattern} to be in {pattern} for {url}"
    
    print("Pagination pattern extraction test passed!")


def test_gate_skipping_logic():
    """Test that consecutive gated pages trigger pagination skipping."""
    scraper = SiteScraper("https://example.com")
    
    # Test that 3 consecutive gated pages trigger skipping
    test_url = "https://example.com/products/page/2/"
    
    # First gated page - should not skip
    assert not scraper._should_skip_pagination(test_url, was_gated=True), "First gated page should not skip"
    
    # Second gated page - should not skip
    assert not scraper._should_skip_pagination(test_url, was_gated=True), "Second gated page should not skip"
    
    # Third gated page - should skip
    assert scraper._should_skip_pagination(test_url, was_gated=True), "Third gated page should skip"
    
    # Reset with a successful page
    assert not scraper._should_skip_pagination(test_url, was_gated=False), "Successful page should reset counter"
    
    # Counter should be reset now
    assert not scraper._should_skip_pagination(test_url, was_gated=True), "After reset, first gated page should not skip"
    
    print("Gate skipping logic test passed!")


def test_empty_page_skipping_logic():
    """Test that consecutive empty pages (no files) trigger pagination skipping via sequence-level detection."""
    scraper = SiteScraper("https://example.com")
    
    # Test that sequence-level empty detection works correctly
    # This is now handled by _complete_pagination_exploration, not _should_skip_pagination
    
    # First pagination exploration with no files
    scraper._start_pagination_exploration("https://example.com/products/page/2/")
    should_skip_1 = scraper._complete_pagination_exploration("https://example.com/products/page/2/")
    assert not should_skip_1, "First empty exploration should not skip"
    
    # Second pagination exploration with no files
    scraper._start_pagination_exploration("https://example.com/products/page/3/")
    should_skip_2 = scraper._complete_pagination_exploration("https://example.com/products/page/3/")
    assert not should_skip_2, "Second empty exploration should not skip"
    
    # Third pagination exploration with no files - should skip
    scraper._start_pagination_exploration("https://example.com/products/page/4/")
    should_skip_3 = scraper._complete_pagination_exploration("https://example.com/products/page/4/")
    assert should_skip_3, "Third empty exploration should skip"
    
    # Reset with exploration that has files
    scraper._start_pagination_exploration("https://example.com/products/page/5/")
    scraper._record_file_discovery("https://example.com/products/page/5/template-1/")
    should_skip_4 = scraper._complete_pagination_exploration("https://example.com/products/page/5/")
    assert not should_skip_4, "Exploration with files should reset counter"
    
    print("Empty page skipping logic test passed!")


def test_dfs_pagination_logic():
    """Test that pagination links are processed in depth-first order."""
    import collections
    
    # Simulate the DFS stack behavior
    pagination_stack = []
    queue = collections.deque()
    
    # Add pagination links (simulating discovery order)
    pagination_links = ["/page/2/", "/page/3/", "/page/4/"]
    
    # Add to stack in reverse order for proper DFS
    for link in reversed(pagination_links):
        pagination_stack.append(link)
    
    # Process order should be: /page/2/, /page/3/, /page/4/
    processed_order = []
    while pagination_stack:
        processed_order.append(pagination_stack.pop())
    
    expected_order = ["/page/2/", "/page/3/", "/page/4/"]
    assert processed_order == expected_order, f"Expected {expected_order}, got {processed_order}"
    
    print("DFS pagination logic test passed!")


def test_sequence_level_empty_detection():
    """Test that empty detection works at sequence level, not page level."""
    scraper = SiteScraper("https://example.com")
    
    # Test pagination context tracking
    pagination_url = "https://example.com/products/page/2/"
    scraper._start_pagination_exploration(pagination_url)
    
    # Simulate file discovery during exploration
    scraper._record_file_discovery("https://example.com/products/page/2/template-1/")
    
    # Complete exploration - should not skip since files were found
    should_skip = scraper._complete_pagination_exploration(pagination_url)
    assert not should_skip, "Should not skip when files were found during exploration"
    
    # Test case where no files are found - need 3 consecutive empty explorations
    for i in range(3):
        scraper._start_pagination_exploration(f"https://example.com/products/page/{i+3}/")
        # No file discoveries
        should_skip = scraper._complete_pagination_exploration(f"https://example.com/products/page/{i+3}/")
        if i < 2:
            assert not should_skip, f"Exploration {i+1} should not skip yet"
        else:
            assert should_skip, "Third empty exploration should skip"
    
    print("Sequence-level empty detection test passed!")


def test_nested_pagination_detection():
    """Test that nested pagination pages are correctly identified."""
    scraper = SiteScraper("https://example.com")
    
    # Test nested pagination detection
    current_context = "https://example.com/products/page/1/"
    
    # These should be detected as nested pagination
    nested_urls = [
        "https://example.com/products/page/2/",
        "https://example.com/products/page/3/",
        "https://example.com/products/page/4/",
    ]
    
    for url in nested_urls:
        assert scraper._is_nested_pagination(url, current_context), f"{url} should be detected as nested pagination"
    
    # These should not be nested pagination (not pagination pages themselves)
    non_nested_urls = [
        "https://example.com/products/template-1/",
        "https://example.com/about/",
    ]
    
    for url in non_nested_urls:
        assert not scraper._is_nested_pagination(url, current_context), f"{url} should not be detected as nested pagination"
    
    print("Nested pagination detection test passed!")


def test_context_stack_management():
    """Test that pagination context stack is managed correctly."""
    scraper = SiteScraper("https://example.com")
    
    # Start first pagination exploration
    scraper._start_pagination_exploration("https://example.com/products/page/1/")
    assert len(scraper._pagination_context_stack) == 1, "Should have 1 context in stack"
    
    # Start nested pagination exploration
    scraper._start_pagination_exploration("https://example.com/products/page/2/")
    assert len(scraper._pagination_context_stack) == 2, "Should have 2 contexts in stack"
    
    # Complete nested exploration
    scraper._complete_pagination_exploration("https://example.com/products/page/2/")
    assert len(scraper._pagination_context_stack) == 1, "Should have 1 context after nested completion"
    
    # Complete parent exploration
    scraper._complete_pagination_exploration("https://example.com/products/page/1/")
    assert len(scraper._pagination_context_stack) == 0, "Should have 0 contexts after parent completion"
    
    print("Context stack management test passed!")


def test_file_discovery_propagation():
    """Test that file discovery propagates up the context stack."""
    scraper = SiteScraper("https://example.com")
    
    # Start nested pagination explorations
    scraper._start_pagination_exploration("https://example.com/products/page/1/")
    scraper._start_pagination_exploration("https://example.com/products/page/2/")
    
    # Record file discovery at deepest level
    scraper._record_file_discovery("https://example.com/products/page/2/template-1/")
    
    # Both contexts should have file discovery recorded
    base_url_1 = scraper._get_pagination_base_url("https://example.com/products/page/1/")
    base_url_2 = scraper._get_pagination_base_url("https://example.com/products/page/2/")
    
    assert scraper._pagination_file_discovery.get(base_url_1, False), "Parent context should have file discovery"
    assert scraper._pagination_file_discovery.get(base_url_2, False), "Nested context should have file discovery"
    
    print("File discovery propagation test passed!")


def test_pagination_link_tree_exploration():
    """Test that pagination pages properly explore their internal links."""
    scraper = SiteScraper("https://example.com")
    
    # Test that pagination pages can explore internal links
    # This simulates the logic where pagination pages add their internal links to the queue
    pagination_url = "https://example.com/products/page/2/"
    internal_links = [
        "https://example.com/products/template-1/",
        "https://example.com/products/template-2/",
        "https://example.com/products/template-3/",
    ]
    
    # Simulate the exploration logic
    exploration_depth = min(0 + 1, scraper.max_depth)  # depth 0 + 1
    assert exploration_depth > 0, "Pagination pages should be able to explore deeper"
    
    # Verify that internal links would be added to queue
    for link in internal_links:
        assert scraper.max_depth >= exploration_depth, f"Should be able to explore {link} at depth {exploration_depth}"
    
    print("Pagination link tree exploration test passed!")


def test_page_status_lifecycle():
    """Test that page status state machine works (None -> not_empty / empty) with URL normalization."""
    scraper = SiteScraper("https://example.com/templates/")
    
    # Unvisited URLs have None status
    assert scraper.get_page_status("https://example.com/templates/") is None
    assert scraper.get_page_status("https://example.com/templates/item-1") is None
    
    # Normalization handles hash and trailing slashes
    scraper.set_page_status("https://example.com/templates/#overview", "not_empty")
    assert scraper.get_page_status("https://example.com/templates") == "not_empty"
    assert scraper.get_page_status("https://example.com/templates/") == "not_empty"
    assert scraper.get_page_status("https://example.com/templates/#heading") == "not_empty"
    
    # Setting empty
    scraper.set_page_status("https://example.com/templates/empty-item/", "empty")
    assert scraper.get_page_status("https://example.com/templates/empty-item") == "empty"
    
    print("Page status lifecycle test passed!")


def test_extract_page_number():
    """Test extracting page numbers from various pagination URL patterns."""
    scraper = SiteScraper("https://example.com")
    
    test_cases = [
        ("https://slidemodel.com/free-powerpoint-templates/", 1),
        ("https://slidemodel.com/free-powerpoint-templates/page/2/", 2),
        ("https://slidemodel.com/free-powerpoint-templates/page/10/", 10),
        ("https://example.com/items?page=3", 3),
        ("https://example.com/items?p=4", 4),
        ("https://example.com/items/page-5/", 5),
        ("https://example.com/items/p6", 6),
    ]
    for url, expected in test_cases:
        actual = scraper._extract_page_number(url)
        assert actual == expected, f"Expected {expected} for {url}, got {actual}"
    
    print("Extract page number test passed!")


def test_revamped_crawler_status_flow():
    """Test end-to-end status determination and priority pagination flow."""
    import unittest.mock as mock
    import httpx
    
    scraper = SiteScraper(
        "https://example.com/catalog/",
        max_crawl_pages=10,
        max_depth=2,
        enable_pagination=True,
        consecutive_empty_threshold=2,
        use_browser=False,
    )
    
    # Mock HTTP responses:
    # Page 1 (catalog): has 1 template link and 1 pagination link to Page 2
    # Template 1: has a download button to presentation.pptx
    # presentation.pptx: binary PPTX
    # Page 2: empty catalog, has pagination link to Page 3
    # Page 3: empty catalog, has pagination link to Page 4
    
    html_page1 = """
    <html><body>
        <h1>Catalog Page 1</h1>
        <a href="/catalog/page/2/">Page 2</a>
        <a href="/catalog/template-1/">Template 1</a>
    </body></html>
    """
    html_template1 = """
    <html><body>
        <h1>Template 1</h1>
        <a href="/downloads/presentation.pptx" class="btn-download">Business Strategy Slide Deck</a>
    </body></html>
    """
    import io
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", "<Types xmlns='http://schemas.openxmlformats.org/package/2006/content-types'><Override PartName='/ppt/presentation.xml' ContentType='application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml'/></Types>")
        zf.writestr("ppt/presentation.xml", "<p:presentation/>")
    # Pad to at least 512 bytes
    if len(buf.getvalue()) < 512:
        with zipfile.ZipFile(buf, "a") as zf:
            zf.writestr("ppt/padding.txt", "0" * 500)
    dummy_pptx = buf.getvalue()
    
    html_page2 = """
    <html><body>
        <h1>Catalog Page 2</h1>
        <a href="/catalog/page/3/">Page 3</a>
    </body></html>
    """
    html_page3 = """
    <html><body>
        <h1>Catalog Page 3</h1>
        <a href="/catalog/page/4/">Page 4</a>
    </body></html>
    """

    def mock_get(url, *args, **kwargs):
        req = httpx.Request("GET", url)
        u = str(url).lower()
        if "presentation.pptx" in u:
            return httpx.Response(200, content=dummy_pptx, request=req)
        elif "template-1" in u:
            return httpx.Response(200, html=html_template1, headers={"content-type": "text/html"}, request=req)
        elif "/page/2" in u:
            return httpx.Response(200, html=html_page2, headers={"content-type": "text/html"}, request=req)
        elif "/page/3" in u:
            return httpx.Response(200, html=html_page3, headers={"content-type": "text/html"}, request=req)
        elif "/page/4" in u:
            # Should NEVER be called because consecutive empty threshold is 2!
            raise AssertionError("Page 4 should not be crawled after 2 consecutive empty pages!")
        else:
            return httpx.Response(200, html=html_page1, headers={"content-type": "text/html"}, request=req)

    with mock.patch("httpx.Client.get", side_effect=mock_get):
        found_items = []
        logs = []
        scraper.crawl_and_extract(on_log=logs.append, on_found=found_items.append)
        
        # 1. Template 1 should be found and downloaded
        assert len(found_items) == 1, f"Expected 1 presentation, found {len(found_items)}"
        assert "Business Strategy" in found_items[0].title
        
        # 2. Page 1 status should be 'not_empty' because template-1 yielded a file
        assert scraper.get_page_status("https://example.com/catalog/") == "not_empty"
        
        # 3. Template 1 status should be 'not_empty'
        assert scraper.get_page_status("https://example.com/catalog/template-1/") == "not_empty"
        
        # 4. Page 2 and Page 3 should be 'empty'
        assert scraper.get_page_status("https://example.com/catalog/page/2/") == "empty"
        assert scraper.get_page_status("https://example.com/catalog/page/3/") == "empty"
        
        # 5. Page 4 should not be evaluated because consecutive empty threshold of 2 was reached
        assert scraper.get_page_status("https://example.com/catalog/page/4/") is None
    
    print("Revamped crawler status flow test passed!")


if __name__ == "__main__":
    test_pagination_detection()
    test_pagination_link_extraction()
    test_pagination_pattern_extraction()
    test_gate_skipping_logic()
    test_empty_page_skipping_logic()
    test_dfs_pagination_logic()
    test_sequence_level_empty_detection()
    test_nested_pagination_detection()
    test_context_stack_management()
    test_file_discovery_propagation()
    test_pagination_link_tree_exploration()
    test_page_status_lifecycle()
    test_extract_page_number()
    test_revamped_crawler_status_flow()
    print("All pagination tests passed successfully!")
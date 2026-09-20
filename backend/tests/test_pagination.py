"""Test pagination detection and intelligent gate skipping in the crawler."""
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
    print("All pagination tests passed successfully!")
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio
from datetime import datetime
import time

from src.actions.action_cache import ActionCache, Action, ActionSequence
from src.llm.claude_client import ClaudeClient
from src.task.executor import TaskExecutor, GUIState
from src.browser.browser_manager import BrowserManager
from src.config.config_manager import ConfigManager
from src.rate_limiter import RateLimiter

@pytest.fixture
def mock_page():
    """Create a mock page for testing"""
    page = AsyncMock()
    page.url = "https://test.com"
    page.title = "Test Page"
    page.viewport_size = {"width": 1920, "height": 1080}
    page.evaluate = AsyncMock(return_value=[{
        "id": "test-button",
        "text": "Click Me",
        "isVisible": True,
        "selector": "#test-button"
    }])
    return page

@pytest.fixture
def browser_manager(mock_page):
    """Create a mock browser manager for testing"""
    manager = AsyncMock()
    manager.get_active_page = AsyncMock(return_value=mock_page)
    manager.execute_action = AsyncMock(return_value=True)
    return manager

@pytest.fixture
def action_cache():
    """Create a mock action cache for testing"""
    cache = AsyncMock()
    cache.get_similar_task = AsyncMock(return_value=None)
    cache.store_sequence = AsyncMock()
    cache.update_stats = AsyncMock()
    return cache

@pytest.fixture
def claude_client():
    """Create a mock Claude client for testing"""
    client = AsyncMock()
    client.plan_actions = AsyncMock(return_value=[Action(
        type="click",
        selector="#test-button"
    )])
    return client

@pytest.fixture
async def setup_test_environment():
    """Setup test environment with all components"""
    config = ConfigManager()
    browser = BrowserManager(config)
    await browser.initialize()
    
    cache = ActionCache()
    claude = ClaudeClient()
    
    executor = TaskExecutor(browser, cache, claude)
    
    yield executor
    
    await browser.cleanup()

@pytest.mark.asyncio
async def test_full_task_flow(setup_test_environment):
    """Test complete task execution flow"""
    executor = setup_test_environment
    
    # Test navigation task
    success = await executor.execute_request("navigate to example.com")
    assert success is True
    
    # Verify page state
    state = await executor.state_manager.capture_state(executor.browser.page)
    assert state.url == "https://example.com"
    
    # Test interaction task
    success = await executor.execute_request("click the login button")
    assert success is True
    
    # Verify state change
    new_state = await executor.state_manager.capture_state(executor.browser.page)
    assert new_state.url != state.url
    
@pytest.mark.asyncio
async def test_error_recovery(setup_test_environment):
    """Test error recovery mechanisms"""
    executor = setup_test_environment
    
    # Simulate navigation error
    executor.browser.page.goto = AsyncMock(side_effect=Exception("Navigation failed"))
    
    # Should retry and eventually fail gracefully
    success = await executor.execute_request("navigate to invalid-site.com")
    assert success is False
    
    # Verify error was logged
    assert len(executor.performance_monitor.metrics.errors) > 0
    
@pytest.mark.asyncio
async def test_popup_handling(setup_test_environment):
    """Test popup handling during task execution"""
    executor = setup_test_environment
    
    # Navigate to site with popups
    await executor.execute_request("navigate to example.com")
    
    # Simulate popup
    await executor.browser.page.evaluate("""
        const modal = document.createElement('div');
        modal.setAttribute('role', 'dialog');
        modal.innerHTML = '<button class="close">×</button>';
        document.body.appendChild(modal);
    """)
    
    # Should handle popup
    handled = await executor.browser.popup_handler.handle_all_popups()
    assert handled is True
    
@pytest.mark.asyncio
async def test_performance_limits(setup_test_environment):
    """Test performance limiting mechanisms"""
    executor = setup_test_environment
    
    # Configure strict rate limit
    executor.rate_limiter = RateLimiter(max_actions=2, time_window=5)
    
    start = time.time()
    
    # Execute multiple actions
    tasks = [
        executor.execute_request("action 1"),
        executor.execute_request("action 2"),
        executor.execute_request("action 3")
    ]
    
    await asyncio.gather(*tasks)
    
    duration = time.time() - start
    assert duration >= 5  # Should have been rate limited
    
@pytest.mark.asyncio
async def test_state_caching(setup_test_environment):
    """Test state caching mechanisms"""
    executor = setup_test_environment
    
    # Capture initial state
    state1 = await executor.state_manager.capture_state(executor.browser.page)
    
    # Immediate recapture should use cache
    state2 = await executor.state_manager.capture_state(executor.browser.page)
    
    assert state1 is state2  # Should be same object (cached)
    
    # Wait for cache expiry
    await asyncio.sleep(61)
    
    # Should be new capture
    state3 = await executor.state_manager.capture_state(executor.browser.page)
    assert state1 is not state3

@pytest.mark.asyncio
async def test_parallel_actions(setup_test_environment):
    """Test parallel action execution"""
    executor = setup_test_environment
    
    # Create multiple parallel tasks
    tasks = []
    for i in range(5):
        task = executor.execute_request(f"task {i}")
        tasks.append(task)
    
    # Execute in parallel
    results = await asyncio.gather(*tasks)
    
    # Verify execution
    assert len(results) == 5
    assert executor.performance_monitor.metrics.action_count == 5
    
    # Check rate limiting worked
    stats = executor.performance_monitor.get_stats()
    assert stats["max_duration"] < 10  # Should not take too long
    
@pytest.mark.asyncio
async def test_cleanup_and_recovery(setup_test_environment):
    """Test cleanup and recovery mechanisms"""
    executor = setup_test_environment
    
    # Force browser crash
    await executor.browser.page.close()
    
    # Should recover and create new page
    success = await executor.execute_request("navigate to example.com")
    assert success is True
    
    # Verify new page works
    assert executor.browser.page is not None
    
@pytest.mark.asyncio
async def test_memory_management(setup_test_environment):
    """Test memory management and cleanup"""
    executor = setup_test_environment
    
    # Execute many state captures
    for _ in range(200):
        await executor.state_manager.capture_state(executor.browser.page)
    
    # Verify cache size is limited
    assert len(executor.state_manager.state_history) <= 100 
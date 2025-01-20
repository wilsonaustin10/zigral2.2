import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from src.actions.action_cache import Action, ActionSequence
from src.task.executor import TaskExecutor, GUIState

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

@pytest.mark.asyncio
async def test_execute_request_new(browser_manager, action_cache, claude_client, setup_task_executor_mocks):
    """Test executing a new request without cache"""
    # Setup mocks with helper
    setup_task_executor_mocks(success=True)
    
    task_executor = TaskExecutor(browser_manager, action_cache, claude_client)
    success = await task_executor.execute_request("click the button")
    
    assert success is True
    action_cache.get_similar_task.assert_awaited_once_with("click the button")
    claude_client.plan_actions.assert_awaited_once()
    action_cache.store_sequence.assert_awaited_once()

@pytest.mark.asyncio
async def test_execute_request_cached(browser_manager, action_cache, claude_client, setup_task_executor_mocks):
    """Test executing a request with cached sequence"""
    cached_sequence = ActionSequence(
        task_key="click the button",
        actions=[Action(type="click", selector="#test-button")],
        success_rate=1.0,
        execution_count=5,
        avg_execution_time=0.5,
        metadata={},
        last_used=datetime.now()
    )
    
    # Override get_similar_task to return our cached sequence
    action_cache.get_similar_task = AsyncMock(return_value=cached_sequence)
    
    # Setup mocks with helper
    setup_task_executor_mocks(success=True)
    
    task_executor = TaskExecutor(browser_manager, action_cache, claude_client)
    success = await task_executor.execute_request("click the button")
    
    assert success is True
    action_cache.get_similar_task.assert_awaited_once_with("click the button")
    claude_client.plan_actions.assert_not_awaited()
    action_cache.update_stats.assert_awaited_once()

@pytest.mark.asyncio
async def test_execute_request_failure(browser_manager, action_cache, claude_client, setup_task_executor_mocks):
    """Test handling execution failure"""
    # Setup mocks with helper, setting success=False to simulate failure
    setup_task_executor_mocks(success=False)
    
    # Override execute_action to return False to simulate failure
    browser_manager.execute_action = AsyncMock(return_value=False)
    
    task_executor = TaskExecutor(browser_manager, action_cache, claude_client)
    success = await task_executor.execute_request("click the button")
    
    assert success is False
    action_cache.store_sequence.assert_not_awaited()
    browser_manager.get_active_page.assert_awaited_once()

@pytest.mark.asyncio
async def test_execute_request_no_actions(browser_manager, action_cache, claude_client, setup_task_executor_mocks):
    """Test handling when no actions are planned"""
    # Setup mocks with helper, but override plan_actions to return None
    setup_task_executor_mocks(success=True)
    claude_client.plan_actions = AsyncMock(return_value=None)
    
    task_executor = TaskExecutor(browser_manager, action_cache, claude_client)
    success = await task_executor.execute_request("click the button")
    
    assert success is False
    action_cache.store_sequence.assert_not_awaited()
    browser_manager.get_active_page.assert_awaited_once() 
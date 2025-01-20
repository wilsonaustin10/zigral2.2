import pytest
import os
import tempfile
import json
from pathlib import Path
from typing import Dict, Any
from unittest.mock import AsyncMock, MagicMock
from src.actions.action_cache import Action

def setup_async_mock_with_result(mock, method_name, result):
    """Helper to setup async mock with specific result"""
    async_mock = AsyncMock(return_value=result)
    setattr(mock, method_name, async_mock)
    return async_mock

def setup_async_mock_sequence(mock, method_name, results):
    """Helper to setup async mock with sequence of results"""
    async_mock = AsyncMock(side_effect=results)
    setattr(mock, method_name, async_mock)
    return async_mock

@pytest.fixture
def temp_config_file():
    """Create a temporary config file"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump({}, f)
        config_path = f.name
    
    yield config_path
    
    # Cleanup
    if os.path.exists(config_path):
        os.unlink(config_path)
        
@pytest.fixture
def valid_config_data() -> Dict[str, Any]:
    """Valid configuration data for testing"""
    return {
        "api": {
            "anthropic_api_key": "test_key",
            "requests_per_minute": 60,
            "burst_limit": 10,
            "max_retries": 3,
            "timeout": 30.0
        },
        "browser": {
            "headless": True,
            "viewport_width": 1920,
            "viewport_height": 1080,
            "locale": "en-US",
            "timezone": "UTC",
            "user_data_dir": str(Path.home() / "chrome-test"),
            "auto_login": True,
            "proxy": None,
            "downloads_path": None,
            "slow_mo": None,
            "ignore_default_args": None,
            "launch_args": [],
            "user_agent": "Mozilla/5.0 (Test)",
            "permissions": ["geolocation"],
            "bypass_csp": True,
            "geolocation": {"latitude": 37.7749, "longitude": -122.4194}
        },
        "auth": {
            "google_email": "test@gmail.com",
            "google_password": "test_password_123",
            "google_2fa_enabled": True,
            "google_2fa_timeout": 30000
        }
    }
    
@pytest.fixture
def invalid_config_data() -> Dict[str, Any]:
    """Invalid configuration data for testing"""
    return {
        "api": {
            "anthropic_api_key": "",  # Empty key
            "requests_per_minute": -1,  # Negative value
        },
        "browser": {
            "viewport_width": -100,  # Invalid viewport
            "locale": "invalid",  # Invalid locale
            "auto_login": True,  # No user_data_dir
            "geolocation": {"latitude": 200}  # Invalid coordinates
        },
        "auth": {
            "google_email": "invalid-email",  # Invalid email
            "google_2fa_timeout": -1  # Invalid timeout
        }
    }

@pytest.fixture
def mock_config_manager(valid_config_data):
    """Mock config manager for testing"""
    class MockConfig:
        def __init__(self, data):
            for key, value in data.items():
                setattr(self, key, type('Config', (), value))
                
    class MockConfigManager:
        def __init__(self):
            self.config = MockConfig(valid_config_data)
            
    return MockConfigManager()
    
@pytest.fixture
def mock_browser_context(mocker):
    """Mock browser context for testing"""
    context = mocker.MagicMock()
    context.new_page = mocker.AsyncMock()
    context.close = mocker.AsyncMock()
    context.cookies = mocker.AsyncMock(return_value=[{"name": "test", "value": "value"}])
    context.add_cookies = mocker.AsyncMock()
    context.clear_cookies = mocker.AsyncMock()
    return context
    
@pytest.fixture
def mock_browser(mocker, mock_browser_context):
    """Mock browser for testing"""
    browser = mocker.MagicMock()
    browser.new_context = mocker.AsyncMock(return_value=mock_browser_context)
    browser.close = mocker.AsyncMock()
    browser.version = mocker.AsyncMock(return_value="Chrome/100.0.0.0")
    browser.contexts = [mock_browser_context]
    return browser
    
@pytest.fixture
def mock_page(mocker):
    """Mock page for testing"""
    page = mocker.MagicMock()
    page.goto = mocker.AsyncMock()
    page.fill = mocker.AsyncMock()
    page.click = mocker.AsyncMock()
    page.wait_for_selector = mocker.AsyncMock()
    page.wait_for_navigation = mocker.AsyncMock()
    page.evaluate = mocker.AsyncMock(return_value={"localStorage": {}, "sessionStorage": {}})
    page.close = mocker.AsyncMock()
    page.screenshot = mocker.AsyncMock()
    page.set_viewport_size = mocker.AsyncMock()
    page.viewport_size = mocker.AsyncMock(return_value={"width": 1920, "height": 1080})
    page.url = "https://example.com"
    
    # Mock accessibility
    accessibility = mocker.MagicMock()
    accessibility.snapshot = mocker.AsyncMock(return_value={"role": "main"})
    page.accessibility = accessibility
    
    return page
    
@pytest.fixture
def mock_playwright(mocker, mock_browser):
    """Mock playwright for testing"""
    playwright = mocker.MagicMock()
    playwright.chromium = mocker.MagicMock()
    playwright.chromium.launch = mocker.AsyncMock(return_value=mock_browser)
    playwright.chromium.connect_over_cdp = mocker.AsyncMock(return_value=mock_browser)
    playwright.stop = mocker.AsyncMock()
    return playwright 

@pytest.fixture
def setup_task_executor_mocks(mock_browser_manager, mock_action_cache, mock_claude_client):
    """Helper fixture to setup common task executor mocks"""
    def _setup(success=True, cached_sequence=None):
        # Setup browser manager
        setup_async_mock_with_result(mock_browser_manager, "execute_action", success)
        setup_async_mock_with_result(mock_browser_manager, "get_active_page", mock_page)
        
        # Setup action cache
        setup_async_mock_with_result(mock_action_cache, "get_similar_task", cached_sequence)
        setup_async_mock_with_result(mock_action_cache, "store_sequence", None)
        setup_async_mock_with_result(mock_action_cache, "update_stats", None)
        
        # Setup Claude client only if we don't have a cached sequence with high success rate
        if not cached_sequence or cached_sequence.success_rate <= 0.8:
            setup_async_mock_with_result(mock_claude_client, "plan_actions", [
                Action(type="click", selector="#test-button")
            ])
        else:
            # Don't set up plan_actions if we have a successful cached sequence
            mock_claude_client.plan_actions = AsyncMock()
    
    return _setup 

@pytest.fixture
def mock_browser_manager(mocker, mock_browser, mock_page):
    """Mock browser manager for testing"""
    manager = mocker.MagicMock()
    manager.browser = mock_browser
    manager.active_page = mock_page
    manager.get_active_page = mocker.AsyncMock(return_value=mock_page)
    manager.execute_action = mocker.AsyncMock(return_value=True)
    manager.cleanup = mocker.AsyncMock()
    return manager

@pytest.fixture
def mock_action_cache(mocker):
    """Mock action cache for testing"""
    cache = mocker.MagicMock()
    cache.get_similar_task = mocker.AsyncMock(return_value=None)
    cache.store_sequence = mocker.AsyncMock()
    cache.update_stats = mocker.AsyncMock()
    cache.clear = mocker.AsyncMock()
    return cache

@pytest.fixture
def mock_claude_client(mocker):
    """Mock Claude client for testing"""
    client = mocker.MagicMock()
    client.plan_actions = mocker.AsyncMock(return_value=[
        Action(type="click", selector="#test-button")
    ])
    return client 
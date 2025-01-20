import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.browser.browser_manager import BrowserManager
from src.config.config_manager import ConfigManager, Config

@pytest.fixture
def mock_playwright():
    """Create mock playwright instance"""
    mock = MagicMock()
    mock.chromium = MagicMock()
    mock.chromium.launch_persistent_context = AsyncMock()
    mock.chromium.connect_over_cdp = AsyncMock()
    return mock

@pytest.fixture
def mock_browser():
    """Create mock browser instance"""
    mock = MagicMock()
    mock.new_context = AsyncMock()
    mock.new_page = AsyncMock()
    mock.contexts = [MagicMock()]
    mock.version = AsyncMock(return_value="Chrome/91.0.4472.0")
    return mock

@pytest.fixture
def mock_page():
    """Create mock page instance"""
    mock = MagicMock()
    mock.goto = AsyncMock()
    mock.evaluate = AsyncMock()
    mock.screenshot = AsyncMock()
    mock.accessibility = MagicMock(snapshot=AsyncMock())
    mock.url = "https://example.com"
    mock.title = AsyncMock(return_value="Test Page")
    return mock

class TestBrowserManager:
    async def test_initialization_with_config(self, mock_playwright, mock_browser, mock_page, mocker):
        """Test browser initialization with config"""
        mocker.patch('playwright.async_api.async_playwright', return_value=mock_playwright)
        mock_browser.new_page.return_value = mock_page
        mock_playwright.chromium.launch_persistent_context.return_value = mock_browser

        config = ConfigManager()
        manager = BrowserManager(config)
        await manager.initialize()

        assert manager.browser is not None
        assert manager.page is not None

    async def test_browser_info(self, mock_playwright, mock_browser, mock_page, mocker):
        """Test browser information retrieval"""
        mocker.patch('playwright.async_api.async_playwright', return_value=mock_playwright)
        mock_browser.new_page.return_value = mock_page
        mock_playwright.chromium.launch_persistent_context.return_value = mock_browser

        manager = BrowserManager()
        await manager.initialize()

        info = await manager.get_browser_info()
        assert isinstance(info, dict)
        assert "version" in info
        assert "user_agent" in info

    async def test_initialization_without_config(self, mock_playwright, mocker):
        """Test browser initialization without config"""
        mocker.patch('playwright.async_api.async_playwright', return_value=mock_playwright)
        
        manager = BrowserManager()
        await manager.initialize()
        
        assert manager.browser is not None
        assert manager.context is not None
        assert manager.default_viewport == {"width": 1920, "height": 1080}
        
    async def test_connect_to_existing_browser(self, mock_playwright, mocker, tmp_path):
        """Test connecting to existing browser"""
        mocker.patch('playwright.async_api.async_playwright', return_value=mock_playwright)
        
        # Create mock DevToolsActivePort file
        devtools_path = tmp_path / "DevToolsActivePort"
        devtools_path.write_text("9222\n")
        
        manager = BrowserManager()
        manager.user_data_dir = str(tmp_path)
        manager.playwright = mock_playwright
        
        browser = await manager._connect_to_existing_browser()
        assert browser is not None
        mock_playwright.chromium.connect_over_cdp.assert_called_once_with("http://localhost:9222")
        
    async def test_login_check_logged_in(self, mock_playwright, mock_browser, mock_page, mocker):
        """Test Google login check when logged in"""
        mocker.patch('playwright.async_api.async_playwright', return_value=mock_playwright)
        mock_browser.new_page.return_value = mock_page
        
        # Mock logged in state
        mock_page.evaluate.return_value = "test@gmail.com"
        
        manager = BrowserManager()
        await manager.initialize()
        
        is_logged_in = await manager._is_logged_in()
        assert is_logged_in is True
        
    async def test_login_check_logged_out(self, mock_playwright, mock_browser, mock_page, mocker):
        """Test Google login check when logged out"""
        mocker.patch('playwright.async_api.async_playwright', return_value=mock_playwright)
        mock_browser.new_page.return_value = mock_page
        
        # Mock logged out state
        mock_page.evaluate.return_value = None
        
        manager = BrowserManager()
        await manager.initialize()
        
        is_logged_in = await manager._is_logged_in()
        assert is_logged_in is False
        
    async def test_google_login_with_2fa(self, mock_playwright, mock_browser, mock_page, mock_config_manager, mocker):
        """Test Google login process with 2FA"""
        mocker.patch('playwright.async_api.async_playwright', return_value=mock_playwright)
        mock_browser.new_page.return_value = mock_page
        
        manager = BrowserManager(config_manager=mock_config_manager)
        await manager.initialize()
        await manager._login_to_google()
        
        # Verify login steps
        mock_page.goto.assert_called_with("https://accounts.google.com")
        mock_page.fill.assert_any_call('input[type="email"]', "test@gmail.com")
        mock_page.fill.assert_any_call('input[type="password"]', "test_password_123")
        mock_page.wait_for_selector.assert_called_with('[aria-label="2-Step Verification"]', timeout=30000)
        
    async def test_page_management(self, mock_playwright, mock_browser, mock_page, mocker):
        """Test page creation and management"""
        mocker.patch('playwright.async_api.async_playwright', return_value=mock_playwright)
        mock_browser.new_page.return_value = mock_page
        
        manager = BrowserManager()
        await manager.initialize()
        
        # Create new page
        page = await manager.new_page("test")
        assert page is not None
        assert "test" in manager.active_pages
        
        # Try to create duplicate page
        page = await manager.new_page("test")
        assert page is None
        
        # Get page
        page = await manager.get_page("test")
        assert page is not None
        
        # Close page
        await manager.close_page("test")
        assert "test" not in manager.active_pages
        
    async def test_viewport_management(self, mock_playwright, mock_browser, mock_page, mocker):
        """Test viewport management"""
        mocker.patch('playwright.async_api.async_playwright', return_value=mock_playwright)
        mock_browser.new_page.return_value = mock_page
        
        manager = BrowserManager()
        await manager.initialize()
        
        # Set viewport
        await manager.set_viewport(1280, 720)
        mock_page.set_viewport_size.assert_called_with({"width": 1280, "height": 720})
        
    async def test_state_management(self, mock_playwright, mock_browser, mock_page, mocker):
        """Test page state management"""
        mocker.patch('playwright.async_api.async_playwright', return_value=mock_playwright)
        mock_browser.new_page.return_value = mock_page
        
        manager = BrowserManager()
        await manager.initialize()
        
        # Get state
        state = await manager.get_page_state()
        assert isinstance(state, dict)
        assert state["url"] == "https://example.com"
        assert state["viewport"] == {"width": 1920, "height": 1080}
        assert state["cookies"] == [{"name": "test", "value": "value"}]
        assert "storage" in state
        
        # Restore state
        test_state = {
            "url": "https://example.com",
            "viewport": {"width": 1280, "height": 720},
            "cookies": [{"name": "test", "value": "value"}],
            "storage": {
                "localStorage": {"key": "value"},
                "sessionStorage": {"key": "value"}
            }
        }
        await manager.restore_page_state(test_state)
        mock_page.goto.assert_called_with("https://example.com")
        mock_page.set_viewport_size.assert_called_with({"width": 1280, "height": 720})
        
    async def test_storage_management(self, mock_playwright, mock_browser, mock_page, mocker):
        """Test storage management"""
        mocker.patch('playwright.async_api.async_playwright', return_value=mock_playwright)
        mock_browser.new_page.return_value = mock_page
        
        manager = BrowserManager()
        await manager.initialize()
        
        # Clear storage
        await manager.clear_storage()
        mock_page.evaluate.assert_called_with("() => { localStorage.clear(); sessionStorage.clear(); }")
        mock_browser.contexts[0].clear_cookies.assert_called_once()
        
    async def test_screenshot_capture(self, mock_playwright, mock_browser, mock_page, mocker, tmp_path):
        """Test screenshot capture"""
        mocker.patch('playwright.async_api.async_playwright', return_value=mock_playwright)
        mock_browser.new_page.return_value = mock_page
        
        manager = BrowserManager()
        await manager.initialize()
        
        screenshot_path = tmp_path / "screenshot.png"
        await manager.take_screenshot(str(screenshot_path))
        mock_page.screenshot.assert_called_with(path=str(screenshot_path), full_page=True)
        
    async def test_accessibility_tree(self, mock_playwright, mock_browser, mock_page, mocker):
        """Test accessibility tree capture"""
        mocker.patch('playwright.async_api.async_playwright', return_value=mock_playwright)
        mock_browser.new_page.return_value = mock_page
        
        manager = BrowserManager()
        await manager.initialize()
        
        tree = await manager.get_accessibility_tree()
        assert tree == {"role": "main"}
        
    async def test_cookie_management(self, mock_playwright, mock_browser, mock_page, mocker):
        """Test cookie management"""
        mocker.patch('playwright.async_api.async_playwright', return_value=mock_playwright)
        mock_browser.new_page.return_value = mock_page
        
        manager = BrowserManager()
        await manager.initialize()
        
        cookies = await manager.get_cookies("example.com")
        assert cookies == [{"name": "test", "value": "value"}]
        
    async def test_cleanup(self, mock_playwright, mock_browser, mocker):
        """Test browser cleanup"""
        mocker.patch('playwright.async_api.async_playwright', return_value=mock_playwright)
        
        manager = BrowserManager()
        await manager.initialize()
        await manager.cleanup()
        
        mock_browser.close.assert_called_once()
        mock_playwright.stop.assert_called_once()
        
    async def test_error_handling(self, mock_playwright, mocker):
        """Test error handling"""
        mocker.patch('playwright.async_api.async_playwright', return_value=mock_playwright)
        mock_playwright.chromium.launch.side_effect = Exception("Launch error")
        
        manager = BrowserManager()
        with pytest.raises(Exception):
            await manager.initialize() 
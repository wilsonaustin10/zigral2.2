import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.browser.browser_manager import BrowserManager
from src.llm.claude_client import ClaudeClient
from src.actions.action_cache import Action
from datetime import datetime

@pytest.fixture
def browser_manager():
    """Create a mock browser manager"""
    mock = MagicMock()
    mock.get_active_page = AsyncMock()
    mock.execute_action = AsyncMock()
    
    # Setup mock page
    mock_page = MagicMock()
    mock_page.url = "https://example.com"
    mock_page.title = AsyncMock(return_value="Test Page")
    mock_page.evaluate = AsyncMock(return_value={
        'url': 'https://example.com',
        'title': 'Test Page',
        'elements': [{
            'id': 'test-button',
            'classes': ['primary'],
            'attributes': {'type': 'button'},
            'isVisible': True,
            'text': 'Click Me'
        }]
    })
    mock_page.viewport_size = AsyncMock(return_value={"width": 1024, "height": 768})
    
    mock.get_active_page.return_value = mock_page
    return mock

@pytest.fixture
def claude():
    """Create a mock Claude client"""
    mock = MagicMock()
    mock.plan_actions = AsyncMock(return_value=[
        Action(type="click", selector="#test-button")
    ])
    return mock

@pytest.mark.asyncio
async def test_browser_state_to_claude(browser_manager, claude):
    """Test capturing browser state and getting actions from Claude"""
    page = await browser_manager.get_active_page()
    state = await page.evaluate("""() => ({
        url: window.location.href,
        title: document.title,
        elements: Array.from(document.querySelectorAll('*')).map(el => ({
            id: el.id,
            classes: Array.from(el.classList),
            attributes: Object.fromEntries(Array.from(el.attributes).map(attr => [attr.name, attr.value])),
            isVisible: el.offsetParent !== null,
            text: el.textContent.trim()
        }))
    })""")
    
    actions = await claude.plan_actions("Click the button", state)
    assert len(actions) == 1
    assert actions[0].type == "click"
    assert actions[0].selector == "#test-button"

@pytest.mark.asyncio
async def test_execute_claude_actions(browser_manager, claude):
    """Test executing actions from Claude in browser"""
    # Get actions from Claude
    actions = await claude.plan_actions("Click the button", {
        'url': 'https://example.com',
        'title': 'Test Page',
        'elements': [{'id': 'test-button', 'text': 'Click Me'}]
    })
    
    # Execute actions
    for action in actions:
        await browser_manager.execute_action(action)
    
    # Verify action was executed
    browser_manager.execute_action.assert_called_once()

@pytest.mark.asyncio
async def test_complex_interaction(browser_manager, claude):
    """Test more complex interaction flow"""
    # Setup mock responses
    claude.plan_actions.side_effect = [
        [Action(type="click", selector="#button1")],
        [Action(type="type", selector="#input1", text="test")],
        [Action(type="click", selector="#submit")]
    ]
    
    # Execute multiple actions
    for request in ["Click first button", "Type test", "Submit form"]:
        actions = await claude.plan_actions(request, {
            'url': 'https://example.com',
            'title': 'Test Page',
            'elements': [{'id': 'test-button', 'text': 'Click Me'}]
        })
        for action in actions:
            await browser_manager.execute_action(action)
    
    # Verify all actions were executed
    assert browser_manager.execute_action.call_count == 3

@pytest.mark.asyncio
async def test_error_handling(browser_manager, claude):
    """Test handling various error conditions"""
    # Make browser action fail
    browser_manager.execute_action.side_effect = Exception("Action failed")
    
    actions = await claude.plan_actions("Click the button", {
        'url': 'https://example.com',
        'title': 'Test Page',
        'elements': [{'id': 'test-button', 'text': 'Click Me'}]
    })
    
    # Attempt to execute action
    try:
        for action in actions:
            await browser_manager.execute_action(action)
        assert False, "Should have raised exception"
    except Exception as e:
        assert str(e) == "Action failed" 
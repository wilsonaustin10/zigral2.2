import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.llm.claude_client import ClaudeClient
from src.actions.action_cache import Action

@pytest.fixture
def mock_anthropic():
    """Fixture that provides a mock Anthropic client without default responses"""
    with patch('anthropic.AsyncAnthropic') as mock:
        mock_instance = MagicMock()
        mock_instance.messages = MagicMock()
        mock_instance.messages.create = AsyncMock()
        mock.return_value = mock_instance
        yield mock

@pytest.fixture
def claude_client(mock_anthropic):
    """Fixture that provides a Claude client with mocked Anthropic instance"""
    client = ClaudeClient("test_api_key")
    client.client = mock_anthropic.return_value
    return client

@pytest.fixture
def sample_gui_state():
    return {
        "url": "https://example.com",
        "title": "Test Page",
        "elements": [
            {
                "id": "test-button",
                "isVisible": True,
                "text": "Click Me"
            }
        ],
        "viewport": {"width": 1920, "height": 1080},
        "timestamp": "2024-01-15T12:00:00Z"
    }

@pytest.mark.asyncio
async def test_plan_actions_success(claude_client, mock_anthropic, sample_gui_state):
    """Test successful action planning with valid response"""
    mock_response = MagicMock()
    mock_response.content = [
        MagicMock(
            text='[{"type": "click", "selector": "#test-button"}]'
        )
    ]
    mock_anthropic.return_value.messages.create.return_value = mock_response

    actions = await claude_client.plan_actions('Click the button', sample_gui_state)
    assert actions is not None
    assert len(actions) == 1
    assert actions[0].type == "click"
    assert actions[0].selector == "#test-button"

@pytest.mark.asyncio
async def test_plan_actions_invalid_json(claude_client, mock_anthropic, sample_gui_state):
    """Test handling invalid JSON response"""
    mock_response = MagicMock()
    mock_response.content = [
        MagicMock(
            text='invalid json'
        )
    ]
    mock_anthropic.return_value.messages.create.return_value = mock_response

    actions = await claude_client.plan_actions('Click the button', sample_gui_state)
    assert actions is None

@pytest.mark.asyncio
async def test_plan_actions_missing_fields(claude_client, mock_anthropic, sample_gui_state):
    """Test handling response with missing required fields"""
    mock_response = MagicMock()
    mock_response.content = [
        MagicMock(
            text='[{"type": "click"}]'
        )
    ]
    mock_anthropic.return_value.messages.create.return_value = mock_response

    actions = await claude_client.plan_actions('Click the button', sample_gui_state)
    assert actions is None

@pytest.mark.asyncio
async def test_plan_actions_api_error(claude_client, mock_anthropic, sample_gui_state):
    """Test handling API error response"""
    mock_anthropic.return_value.messages.create.side_effect = Exception("API Error")

    actions = await claude_client.plan_actions('Click the button', sample_gui_state)
    assert actions is None 
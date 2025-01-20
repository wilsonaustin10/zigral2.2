import pytest
import json
import os
from pathlib import Path
from src.config.config_manager import ConfigManager, Config
from pydantic import ValidationError

@pytest.fixture
def temp_config_file(tmp_path):
    """Create a temporary config file"""
    config_file = tmp_path / "test_config.json"
    return str(config_file)

@pytest.fixture
def valid_config_data(monkeypatch):
    """Fixture providing valid test configuration data"""
    # Set environment variables for sensitive data
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test_key_for_testing")
    monkeypatch.setenv("GOOGLE_TEST_EMAIL", "test@example.com")
    monkeypatch.setenv("GOOGLE_TEST_PASSWORD", "test_password_12345")
    
    return {
        "api": {
            "anthropic_api_key": os.getenv("ANTHROPIC_API_KEY"),
            "requests_per_minute": 60,
            "max_retries": 3
        },
        "browser": {
            "viewport_width": 1920,
            "viewport_height": 1080,
            "headless": True,
            "user_data_dir": os.path.expanduser("~/.lam/test/browser_data")
        },
        "auth": {
            "google_email": os.getenv("GOOGLE_TEST_EMAIL"),
            "google_password": os.getenv("GOOGLE_TEST_PASSWORD"),
            "google_2fa_enabled": False
        }
    }

@pytest.fixture
def invalid_config_data():
    """Fixture providing invalid test configuration data"""
    return {
        "api": {
            "requests_per_minute": -1,  # Invalid: must be positive
            "max_retries": "invalid"    # Invalid: wrong type
        },
        "browser": {
            "viewport_width": 100,      # Invalid: below minimum
            "viewport_height": 10000    # Invalid: above maximum
        },
        "auth": {
            "google_email": "invalid-email",  # Invalid: wrong format
            "google_password": "short",       # Invalid: too short
            "google_2fa_timeout": -1         # Invalid: negative timeout
        }
    }

@pytest.mark.asyncio
class TestConfigManager:
    
    async def test_init_with_empty_file(self, temp_config_file):
        """Test initialization with empty config file"""
        manager = ConfigManager(temp_config_file)
        assert isinstance(manager.config, Config)
        assert manager.config.api.anthropic_api_key is None
        
    async def test_load_valid_config(self, temp_config_file, valid_config_data):
        """Test loading valid configuration"""
        with open(temp_config_file, 'w') as f:
            json.dump(valid_config_data, f)
            
        manager = ConfigManager(temp_config_file)
        assert manager.config.api.anthropic_api_key == os.getenv("ANTHROPIC_API_KEY")
        assert manager.config.browser.viewport_width == 1920
        assert manager.config.auth.google_email == os.getenv("GOOGLE_TEST_EMAIL")
        
    async def test_validation_error_on_invalid_config(self, temp_config_file, invalid_config_data):
        """Test validation errors with invalid configuration"""
        with open(temp_config_file, 'w') as f:
            json.dump(invalid_config_data, f)

        with pytest.raises(ValidationError) as exc_info:
            ConfigManager(temp_config_file)

        # Verify specific validation errors
        errors = exc_info.value.errors()
        error_messages = [e["msg"] for e in errors]
        
        expected_messages = [
            "Input should be a valid integer, unable to parse string as an integer",
            "Input should be greater than or equal to 800",
            "Input should be less than or equal to 2160",
            "Value error, Invalid email format",
            "Value error, Password must be at least 8 characters",
            "Value error, Timeout values must be positive"
        ]
        
        for msg in expected_messages:
            assert any(msg in error for error in error_messages), f"Expected error message not found: {msg}"
        
    async def test_update_config(self, temp_config_file, valid_config_data):
        """Test updating configuration"""
        manager = ConfigManager(temp_config_file)
        
        # Update with valid data
        manager.update_config(valid_config_data)
        assert manager.config.api.anthropic_api_key == os.getenv("ANTHROPIC_API_KEY")
        
        # Verify file was updated
        with open(temp_config_file, 'r') as f:
            saved_data = json.load(f)
            assert saved_data["api"]["anthropic_api_key"] == os.getenv("ANTHROPIC_API_KEY")

    async def test_validation_edge_cases(self, temp_config_file):
        """Test validation of edge cases"""
        manager = ConfigManager(temp_config_file)

        # Test empty strings
        empty_config = {
            'api': {'anthropic_api_key': ''},
            'auth': {'google_email': '', 'google_password': ''},
            'browser': {'user_data_dir': ''}
        }

        with pytest.raises(ValidationError) as exc_info:
            manager.update_config(empty_config)

        errors = exc_info.value.errors()
        assert any("cannot be empty" in str(e["msg"]) for e in errors)

    async def test_reset_config(self, temp_config_file, valid_config_data):
        """Test resetting configuration to defaults"""
        manager = ConfigManager(temp_config_file)
        
        # Set some values
        manager.update_config(valid_config_data)
        assert manager.config.api.anthropic_api_key == os.getenv("ANTHROPIC_API_KEY")
        
        # Reset config
        manager.reset_config()
        
        # Verify defaults
        assert manager.config.api.anthropic_api_key is None
        assert manager.config.browser.viewport_width == 1920
        assert manager.config.auth.google_email is None
        
    async def test_environment_config(self, temp_config_file, monkeypatch):
        """Test loading configuration from environment variables"""
        manager = ConfigManager(temp_config_file)
        
        # Set environment variables
        monkeypatch.setenv("ANTHROPIC_API_KEY", "env_test_key")
        monkeypatch.setenv("LAM_BROWSER_VIEWPORT_WIDTH", "1280")
        
        # Load from environment
        manager.load_environment_config()
        
        assert manager.config.api.anthropic_api_key == "env_test_key"
        assert manager.config.browser.viewport_width == 1280
        
    async def test_export_import_config(self, temp_config_file, valid_config_data, tmp_path):
        """Test exporting and importing configuration"""
        manager = ConfigManager(temp_config_file)
        manager.update_config(valid_config_data)

        # Export config
        export_path = tmp_path / "exported_config.json"
        manager.export_config(str(export_path))

        # Create new manager and import
        new_manager = ConfigManager(temp_config_file)
        new_manager.import_config(str(export_path))

        # Verify imported config matches
        original_config = manager.config.model_dump()
        imported_config = new_manager.config.model_dump()
        
        # Compare configs excluding sensitive data
        original_config['api']['anthropic_api_key'] = '***'
        imported_config['api']['anthropic_api_key'] = '***'
        assert imported_config == original_config
        
    async def test_sensitive_data_handling(self, temp_config_file, valid_config_data, tmp_path):
        """Test handling of sensitive configuration data"""
        manager = ConfigManager(temp_config_file)
        manager.update_config(valid_config_data)
        
        # Export config
        export_path = tmp_path / "exported_config.json"
        manager.export_config(str(export_path))
        
        # Verify sensitive data is masked
        with open(export_path, 'r') as f:
            exported_data = json.load(f)
            assert exported_data["api"]["anthropic_api_key"] == "***"
            
    async def test_prompt_templates(self, temp_config_file):
        """Test prompt template management"""
        manager = ConfigManager(temp_config_file)
        
        # Update with prompt templates
        manager.update_config({
            "prompts": {
                "action_planning": "Plan actions for: {task}",
                "state_validation": "Validate state: {state}"
            }
        })
        
        # Get templates
        assert manager.get_prompt_template("action_planning") == "Plan actions for: {task}"
        assert manager.get_prompt_template("nonexistent") == "" 
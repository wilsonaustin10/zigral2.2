import logging
import json
import os
import re
from typing import Any, Dict, Optional, List
from dataclasses import dataclass, asdict, field
from pydantic import BaseModel, Field, field_validator, model_validator, ValidationError
from pathlib import Path
from datetime import datetime
import pytz

logger = logging.getLogger(__name__)

class APIConfig(BaseModel):
    """API configuration"""
    anthropic_api_key: Optional[str] = Field(default=None, description="Anthropic API key")
    requests_per_minute: int = Field(60, description="Rate limit for API requests")
    burst_limit: int = Field(10, description="Maximum burst of requests")
    max_retries: int = Field(3, description="Maximum number of retries")
    retry_delay: float = Field(1.0, description="Delay between retries in seconds")
    timeout: float = Field(30.0, description="API timeout in seconds")

class ModelConfig(BaseModel):
    """Model configuration"""
    main_model: str = Field("claude-3-sonnet-20240229", description="Main model for planning")
    fast_model: str = Field("claude-3-haiku-20240307", description="Fast model for validation")
    vision_model: str = Field("claude-3-opus-20240229", description="Vision model for analysis")
    temperature: float = Field(0.7, description="Model temperature")
    max_tokens: int = Field(2000, description="Maximum tokens per request")

class AuthConfig(BaseModel):
    """Authentication configuration"""
    google_email: Optional[str] = Field(default=None, description="Google account email")
    google_password: Optional[str] = Field(default=None, description="Google account password")
    google_2fa_enabled: bool = Field(False, description="Whether 2FA is enabled for Google")
    google_2fa_timeout: int = Field(300, description="Timeout for 2FA completion (seconds)")
    auto_login_retry: int = Field(3, description="Number of login retry attempts")
    session_timeout: int = Field(3600, description="Session timeout in seconds")

    @field_validator('google_email')
    def validate_email(cls, v):
        if v and '@' not in v:
            raise ValueError('Invalid email format')
        return v

    @field_validator('google_password')
    def validate_password(cls, v):
        if v and len(v) < 8:
            raise ValueError('Password must be at least 8 characters')
        return v

    @field_validator('google_2fa_timeout', 'auto_login_retry', 'session_timeout')
    def validate_timeouts(cls, v):
        if v < 0:
            raise ValueError('Timeout values must be positive')
        return v

    @model_validator(mode='after')
    def validate_auth_config(cls, values):
        """Validate authentication configuration"""
        if values.google_email and not values.google_password:
            raise ValueError('Password required if email is provided')
        if values.google_password and not values.google_email:
            raise ValueError('Email required if password is provided')
        return values

class TimeoutConfig(BaseModel):
    """Timeout configuration settings"""
    navigation: int = Field(default=30000, ge=1000)
    element: int = Field(default=5000, ge=1000)
    popup: int = Field(default=2000, ge=500)
    action: int = Field(default=10000, ge=1000)

class RetryConfig(BaseModel):
    """Retry configuration settings"""
    max_attempts: int = Field(default=3, ge=1)
    backoff_base: int = Field(default=2, ge=1)
    max_backoff: int = Field(default=300, ge=1)

class BrowserConfig(BaseModel):
    """Browser configuration settings"""
    headless: bool = Field(default=False)
    auto_login: bool = Field(default=True)
    viewport_width: int = Field(default=1920, ge=800, le=3840)
    viewport_height: int = Field(default=1080, ge=600, le=2160)
    locale: str = Field(default="en-US")
    timezone: str = Field(default="UTC")
    geolocation: Dict = Field(default={"latitude": 37.7749, "longitude": -122.4194})
    permissions: List[str] = Field(default=[])
    proxy: Optional[str] = Field(default=None)
    user_data_dir: str = Field(
        default=os.path.expanduser("~/.zigral/browser_data"),
        description="Directory for storing persistent browser state"
    )
    debug_port: Optional[int] = Field(default=None)
    profile_name: Optional[str] = Field(default=None)
    ignore_default_args: List[str] = Field(default=[])
    downloads_path: str = Field(default="downloads")
    slow_mo: int = Field(default=0)
    bypass_csp: bool = Field(default=True)
    timeouts: TimeoutConfig = Field(default_factory=TimeoutConfig)
    retry: RetryConfig = Field(default_factory=RetryConfig)
    performance: Dict[str, int] = Field(
        default={
            "max_actions_per_minute": 60,
            "max_concurrent_actions": 3,
            "state_cache_size": 100
        }
    )
    
    @field_validator("locale")
    def validate_locale(cls, v):
        if not re.match(r"^[a-z]{2}(-[A-Z]{2})?$", v):
            raise ValueError("Invalid locale format")
        return v
        
    @field_validator("timezone")
    def validate_timezone(cls, v):
        try:
            pytz.timezone(v)
        except pytz.exceptions.UnknownTimeZoneError:
            raise ValueError("Invalid timezone")
        return v
        
    @field_validator("geolocation")
    def validate_geolocation(cls, v):
        if not isinstance(v, dict):
            raise ValueError("Geolocation must be a dictionary")
        if "latitude" not in v or "longitude" not in v:
            raise ValueError("Geolocation must contain latitude and longitude")
        lat = v["latitude"]
        lon = v["longitude"]
        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            raise ValueError("Invalid latitude/longitude values")
        return v
        
    @field_validator("permissions")
    def validate_permissions(cls, v):
        valid_permissions = {"geolocation", "notifications", "camera", "microphone"}
        for perm in v:
            if perm not in valid_permissions:
                raise ValueError(f"Invalid permission: {perm}")
        return v
        
    @field_validator("proxy")
    def validate_proxy(cls, v):
        if v is not None and not re.match(r"^(http|https|socks5)://", v):
            raise ValueError("Invalid proxy URL format")
        return v
        
    @field_validator("user_data_dir")
    def validate_user_data_dir(cls, v):
        """Ensure user_data_dir is an absolute path"""
        if not v:
            raise ValueError("user_data_dir must not be empty")
        if not os.path.isabs(v):
            v = os.path.abspath(v)
        # Create directory if it doesn't exist
        os.makedirs(v, exist_ok=True)
        return v
        
    @field_validator("debug_port")
    def validate_debug_port(cls, v):
        if v is not None and not (1024 <= v <= 65535):
            raise ValueError("Debug port must be between 1024 and 65535")
        return v
        
    @field_validator("profile_name")
    def validate_profile_name(cls, v):
        if v is not None and not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError("Invalid profile name format")
        return v
        
    @model_validator(mode="after")
    def validate_debug_config(self):
        if self.debug_port is not None and not self.user_data_dir:
            raise ValueError("user_data_dir is required when debug_port is set")
        return self

    @field_validator("performance")
    def validate_performance(cls, v):
        if v["max_actions_per_minute"] < 1:
            raise ValueError("max_actions_per_minute must be positive")
        if v["max_concurrent_actions"] < 1:
            raise ValueError("max_concurrent_actions must be positive")
        if v["state_cache_size"] < 1:
            raise ValueError("state_cache_size must be positive")
        return v

class StateConfig(BaseModel):
    """State configuration"""
    max_checkpoints: int = Field(100, description="Maximum stored checkpoints")
    auto_checkpoint_enabled: bool = Field(True, description="Enable auto-checkpointing")
    auto_checkpoint_interval: int = Field(300, description="Auto-checkpoint interval (s)")
    state_file: str = Field("state.json", description="State persistence file")

class TaskConfig(BaseModel):
    """Task configuration"""
    max_concurrent_tasks: int = Field(5, description="Maximum concurrent tasks")
    default_timeout: float = Field(300.0, description="Default task timeout (s)")
    queue_size: int = Field(1000, description="Maximum queue size")
    default_priority: int = Field(0, description="Default task priority")

class CacheConfig(BaseModel):
    """Cache configuration"""
    max_responses: int = Field(1000, description="Maximum cached responses")
    response_ttl: int = Field(3600, description="Response cache TTL (s)")
    use_redis: bool = Field(False, description="Use Redis for caching")
    redis_url: str = Field("redis://localhost:6379", description="Redis connection URL")

class PerformanceConfig(BaseModel):
    """Performance configuration"""
    max_memory_usage: int = Field(1024 * 1024 * 1024, description="Maximum memory usage (bytes)")
    max_operation_time: float = Field(60.0, description="Maximum operation time (s)")
    log_timing: bool = Field(True, description="Log operation timing")
    metrics_enabled: bool = Field(True, description="Enable performance metrics")

class SafetyConfig(BaseModel):
    """Safety configuration"""
    require_confirmation: bool = Field(True, description="Require user confirmation")
    max_retries: int = Field(3, description="Maximum retry attempts")
    emergency_stop_enabled: bool = Field(True, description="Enable emergency stop")
    restricted_domains: list = Field(default_factory=list, description="Restricted domains")
    allowed_actions: list = Field(default_factory=list, description="Allowed actions")

class Config(BaseModel):
    """Main configuration"""
    api: APIConfig = Field(default_factory=APIConfig)
    model: ModelConfig = Field(default_factory=ModelConfig)
    browser: BrowserConfig = Field(default_factory=BrowserConfig)
    state: StateConfig = Field(default_factory=StateConfig)
    task: TaskConfig = Field(default_factory=TaskConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    performance: PerformanceConfig = Field(default_factory=PerformanceConfig)
    safety: SafetyConfig = Field(default_factory=SafetyConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    prompts: Dict[str, Dict[str, str]] = Field(
        default_factory=lambda: {
            "investing.com": {
                "base": """You are analyzing investing.com's interface. Focus on these key elements:
1. Search box: Usually found as "input#searchText" or "input[type='search']"
2. Navigation menu: Located in ".main-nav" or "#navMenu"
3. Market data: Found in tables with class "marketInformation" or "table-browser"
4. Historical data elements:
   - Date range selector: ".flex.items-center.gap-3.5.rounded.border"
   - Download button: "div.cursor-pointer.items-center.gap-3.hidden.md\\:flex"
5. Common popups to handle:
   - Cookie consent: "#onetrust-accept-btn-handler"
   - Subscription: ".modal .close-btn"
   - Ads: "[data-name='gam-ad-popup-close']"

URL Patterns:
1. Currency Pair Live:
   - Pattern: https://www.investing.com/currencies/XXX-YYY
   - Example: GBP/USD -> https://www.investing.com/currencies/gbp-usd
   
2. Historical Data:
   - Pattern: https://www.investing.com/currencies/XXX-YYY-historical-data
   - Example: GBP/USD -> https://www.investing.com/currencies/gbp-usd-historical-data

Rules for URL construction:
- Convert "/" in pair to "-" in URL
- Use lowercase in URL
- Add "-historical-data" suffix for historical pages

Return ONE action at a time. Examples:

For direct navigation to GBP/USD live:
[{"type": "navigate", "url": "https://www.investing.com/currencies/gbp-usd"}]

For direct navigation to GBP/USD historical:
[{"type": "navigate", "url": "https://www.investing.com/currencies/gbp-usd-historical-data"}]

For selecting date range on historical page:
[{"type": "click", "selector": ".flex.items-center.gap-3\\.5.rounded.border"}]

For downloading historical data:
[{"type": "click", "selector": "div.cursor-pointer.items-center.gap-3.hidden.md\\:flex"}]

For searching:
[{"type": "click", "selector": "input#searchText"}]

After search box is focused:
[{"type": "type", "selector": "input#searchText", "text": "GBP/USD"}]

After results appear:
[{"type": "click", "selector": "a[href*='gbp-usd']"}]

Task complete after reaching correct page:
[]""",
                "search": """You are searching for {symbol} on investing.com.

URL Patterns:
1. Live Price URL:
   - Convert pair format: {symbol} -> lowercase, replace "/" with "-"
   - Example: GBP/USD -> gbp-usd
   - Full URL: https://www.investing.com/currencies/gbp-usd

2. Historical Data URL:
   - Same as live price URL + "-historical-data" suffix
   - Example: https://www.investing.com/currencies/gbp-usd-historical-data

Historical Data Interface:
- Date range selector: ".flex.items-center.gap-3.5.rounded.border"
- Download button: "div.cursor-pointer.items-center.gap-3.hidden.md\\:flex"

Two ways to reach the data:
1. Direct Navigation (preferred):
   For live price:
   [{"type": "navigate", "url": "https://www.investing.com/currencies/PAIR"}]
   
   For historical data:
   [{"type": "navigate", "url": "https://www.investing.com/currencies/PAIR-historical-data"}]
   Replace PAIR with formatted symbol (e.g., gbp-usd)

2. Search Method (fallback):
   a. Click search: [{"type": "click", "selector": "input#searchText"}]
   b. Type pair: [{"type": "type", "selector": "input#searchText", "text": "{symbol}"}]
   c. Click result: [{"type": "click", "selector": "a[href*='PAIR']"}]
   d. For historical, click: [{"type": "click", "selector": "a[href*='historical-data']"}]
   Replace PAIR with formatted symbol

For historical data tasks:
1. Navigate to historical page
2. Click date selector: [{"type": "click", "selector": ".flex.items-center.gap-3\\.5.rounded.border"}]
3. Click download: [{"type": "click", "selector": "div.cursor-pointer.items-center.gap-3.hidden.md\\:flex"}]

Return empty array [] when on correct page."""
            },
            "linkedin.com": {
                "base": """You are navigating LinkedIn's interface. Focus on these key elements:
1. Search box: Usually "input[placeholder*='Search']"
2. Navigation: ".global-nav" links
3. Common popups:
   - Sign-in modal: ".modal-overlay button"
   - Cookie notice: "#artdeco-global-alert-container button"
   
Return ONE action at a time."""
            }
        }
    )
    environment: str = Field("development", description="Environment (development/production)")
    debug: bool = Field(False, description="Enable debug mode")

    @field_validator('api', 'auth', 'browser')
    def validate_non_empty_strings(cls, v):
        """Validate that no string fields are empty"""
        def check_empty_strings(obj):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    if isinstance(value, str) and not value.strip():
                        raise ValueError(f"Field {key} cannot be empty")
                    elif isinstance(value, (dict, list)):
                        check_empty_strings(value)
            elif isinstance(obj, list):
                for item in obj:
                    check_empty_strings(item)

        check_empty_strings(v.model_dump())
        return v

class ConfigManager:
    """Configuration manager for loading and managing application settings"""
    
    def __init__(self, config_file: str):
        self.config_file = config_file
        self.config = Config()
        self._load_config()
    
    def _load_config(self):
        """Load configuration from file"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    config_data = json.load(f)
                # Validate config data before assigning
                self.config = Config.model_validate(config_data)
            else:
                logger.info(f"Config file {self.config_file} not found, using defaults")
                self.config = Config()
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse config file: {e}")
            raise ValidationError([{
                "loc": ("config_file",),
                "msg": f"Invalid JSON in config file: {e}",
                "type": "value_error.json"
            }])
        except ValidationError as e:
            logger.error(f"Invalid configuration: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            raise
    
    def update_config(self, updates: Dict) -> None:
        """Update configuration with new values"""
        try:
            # Create a copy of the current config as a dict
            current_config = self.config.model_dump()
            
            # Deep merge the updates
            updated_config = self._deep_merge(current_config, updates)
            
            # Validate the merged config
            self.config = Config.model_validate(updated_config)
            
            # Save updated config
            self.save_config()
        except ValidationError as e:
            logger.error(f"Failed to update config: {e}")
            raise
    
    def _deep_merge(self, d1: Dict, d2: Dict) -> Dict:
        """Deep merge two dictionaries"""
        result = d1.copy()
        for key, value in d2.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result
    
    def save_config(self):
        """Save current configuration to file"""
        try:
            # Ensure the directory exists
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            
            # Convert config to dict, excluding sensitive data
            config_dict = self.config.model_dump(exclude_none=True)
            
            # Write to file
            with open(self.config_file, 'w') as f:
                json.dump(config_dict, f, indent=2)
                
            logger.info(f"Configuration saved to {self.config_file}")
        except Exception as e:
            logger.error(f"Failed to save config: {e}")
            raise
        
    def get_config(self) -> Config:
        """Get current configuration"""
        return self.config
        
    def validate_config(self) -> bool:
        """Validate configuration"""
        try:
            Config(**self.config.model_dump())
            return True
        except Exception as e:
            logger.error(f"Invalid configuration: {e}")
            raise
            
    def reset_config(self):
        """Reset configuration to defaults"""
        try:
            # Create new config with defaults
            self.config = Config()
            
            # Save the default config
            self.save_config()
            
            logger.info("Configuration reset to defaults")
        except Exception as e:
            logger.error(f"Failed to reset config: {e}")
            raise
        
    def load_environment_config(self):
        """Load configuration from environment variables"""
        env_updates = {}
        
        # API configuration
        if os.getenv("ANTHROPIC_API_KEY"):
            env_updates["api"] = {"anthropic_api_key": os.getenv("ANTHROPIC_API_KEY")}
        
        # Browser configuration
        browser_updates = {}
        if os.getenv("LAM_BROWSER_VIEWPORT_WIDTH"):
            browser_updates["viewport_width"] = int(os.getenv("LAM_BROWSER_VIEWPORT_WIDTH"))
        if browser_updates:
            env_updates["browser"] = browser_updates
        
        if env_updates:
            self.update_config(env_updates)
            return True
        return False
            
    def export_config(self, filepath: str):
        """Export configuration to file"""
        try:
            config_data = self.config.model_dump()
            
            # Remove sensitive data
            if "api" in config_data:
                config_data["api"]["anthropic_api_key"] = "***"
                
            with open(filepath, 'w') as f:
                json.dump(config_data, f, indent=2)
                
            logger.debug(f"Exported config to: {filepath}")
            
        except Exception as e:
            logger.error(f"Failed to export config: {e}")
            raise
            
    def import_config(self, filepath: str):
        """Import configuration from file"""
        try:
            with open(filepath, 'r') as f:
                config_data = json.load(f)
                
            # Preserve API key if not in imported config
            if "api" in config_data and not config_data["api"].get("anthropic_api_key"):
                config_data["api"]["anthropic_api_key"] = self.config.api.anthropic_api_key
                
            self.config = Config(**config_data)
            self.save_config()
            
            logger.debug(f"Imported config from: {filepath}")
            
        except Exception as e:
            logger.error(f"Failed to import config: {e}")
            raise
            
    def get_prompt_template(self, template_name: str) -> str:
        """Get prompt template"""
        return self.config.prompts.get(template_name, "") 
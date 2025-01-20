from pydantic import BaseSettings, Field
from typing import Dict, Optional, List

class VisionConfig(BaseSettings):
    """Vision processing configuration"""
    feature_compression: bool = True
    compression_ratio: float = 0.5
    min_confidence: float = 0.7
    supported_element_types: List[str] = [
        "button", "input", "link", "text", "image",
        "checkbox", "radio", "dropdown", "slider"
    ]

class ModelConfig(BaseSettings):
    """LLM configuration"""
    main_model: str = "claude-3-sonnet-20240229"
    fast_model: str = "claude-3-haiku-20240307"
    vision_model: str = "claude-3-opus-20240229"
    temperature: float = 0.7
    max_tokens: int = 4096
    json_mode: bool = True

class BrowserConfig(BaseSettings):
    """Browser automation configuration"""
    user_agent: str = Field(...)
    viewport: Dict[str, int] = {"width": 1920, "height": 1080}
    locale: str = "en-US"
    timezone: str = "America/Los_Angeles"
    headless: bool = False

class SafetyConfig(BaseSettings):
    """Safety mechanisms configuration"""
    require_confirmation: bool = True
    max_retries: int = 3
    action_timeout: int = 30000  # ms
    emergency_stop_enabled: bool = True

class APIConfig(BaseSettings):
    """API configuration"""
    anthropic_api_key: str = Field(..., env="ANTHROPIC_API_KEY")
    rate_limit: int = 5
    burst_limit: int = 10
    timeout: int = 30

class CacheConfig(BaseSettings):
    """Caching configuration"""
    action_cache_size: int = 1000
    feature_cache_size: int = 100
    cache_ttl: int = 3600  # 1 hour
    use_redis: bool = False
    redis_url: Optional[str] = None

class PerformanceConfig(BaseSettings):
    """Performance monitoring configuration"""
    log_timing: bool = True
    resource_monitoring: bool = True
    action_profiling: bool = True
    max_memory_usage: int = 1024 * 1024 * 1024  # 1GB

class Config(BaseSettings):
    """Main configuration"""
    vision: VisionConfig = VisionConfig()
    model: ModelConfig = ModelConfig()
    browser: BrowserConfig = BrowserConfig()
    safety: SafetyConfig = SafetyConfig()
    api: APIConfig = APIConfig()
    cache: CacheConfig = CacheConfig()
    performance: PerformanceConfig = PerformanceConfig()

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

# Create global config instance
config = Config() 
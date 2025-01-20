from typing import Dict, List, Optional, Any
import logging
import json
import time
import asyncio
from datetime import datetime
from anthropic import Anthropic, APIError, APITimeoutError, RateLimitError
from cachetools import TTLCache
from config.settings import config

logger = logging.getLogger(__name__)

class TokenBucket:
    """Rate limiter using token bucket algorithm"""
    def __init__(self, rate: float, capacity: int):
        self.rate = rate  # tokens per second
        self.capacity = capacity
        self.tokens = capacity
        self.last_update = time.time()
        
    async def acquire(self):
        now = time.time()
        time_passed = now - self.last_update
        self.tokens = min(self.capacity, self.tokens + time_passed * self.rate)
        self.last_update = now
        
        if self.tokens < 1:
            wait_time = (1 - self.tokens) / self.rate
            await asyncio.sleep(wait_time)
            self.tokens = 0
            return True
            
        self.tokens -= 1
        return True

class AgentManager:
    """Manages interactions with Claude models"""
    
    def __init__(self):
        self.client = Anthropic(api_key=config.api.anthropic_api_key)
        self.models = {
            "main": config.model.main_model,
            "fast": config.model.fast_model,
            "vision": config.model.vision_model
        }
        
        # Initialize rate limiter
        self.rate_limiter = TokenBucket(
            rate=config.api.requests_per_minute / 60,
            capacity=config.api.burst_limit
        )
        
        # Initialize response cache
        self.cache = TTLCache(
            maxsize=config.cache.max_responses,
            ttl=config.cache.response_ttl
        )
        
        # Load prompt templates
        self.prompt_templates = {
            "action": self._load_prompt_template("action_planning"),
            "validation": self._load_prompt_template("state_validation"),
            "vision": self._load_prompt_template("vision_analysis")
        }
        
    def _load_prompt_template(self, template_name: str) -> str:
        """Load prompt template from config"""
        try:
            return config.prompts.get(template_name, "")
        except Exception as e:
            logger.error(f"Failed to load prompt template {template_name}: {str(e)}")
            return ""
            
    def _get_cache_key(self, prompt: str, model: str) -> str:
        """Generate cache key for a prompt"""
        return f"{model}:{hash(prompt)}"
        
    async def _handle_api_error(self, error: Exception, retry_count: int = 0) -> None:
        """Handle API errors with exponential backoff"""
        if retry_count >= config.api.max_retries:
            raise error
            
        if isinstance(error, RateLimitError):
            wait_time = min(2 ** retry_count, 60)  # Max 60 second wait
            logger.warning(f"Rate limit hit, waiting {wait_time} seconds")
            await asyncio.sleep(wait_time)
            return
            
        if isinstance(error, APITimeoutError):
            wait_time = min(2 ** retry_count * 5, 300)  # Max 5 minute wait
            logger.warning(f"API timeout, waiting {wait_time} seconds")
            await asyncio.sleep(wait_time)
            return
            
        raise error
        
    async def plan_actions(self, task: str, gui_state: Dict) -> List[Dict]:
        """Plan actions to accomplish a task given the current GUI state"""
        try:
            # Construct prompt
            prompt = self.prompt_templates["action"].format(
                task=task,
                gui_state=json.dumps(gui_state, indent=2)
            )
            
            # Check cache
            cache_key = self._get_cache_key(prompt, self.models["main"])
            if cache_key in self.cache:
                logger.debug("Using cached action plan")
                return self.cache[cache_key]
                
            # Apply rate limiting
            await self.rate_limiter.acquire()
            
            # Get response from Claude
            response = await self._get_completion(
                prompt,
                model=self.models["main"],
                temperature=config.model.temperature,
                max_tokens=config.model.max_tokens
            )
            
            # Parse and cache actions
            actions = self._parse_actions(response)
            self.cache[cache_key] = actions
            
            logger.debug(f"Planned {len(actions)} actions for task: {task}")
            return actions
            
        except Exception as e:
            logger.error(f"Action planning failed: {str(e)}")
            raise
            
    async def validate_state(self, gui_state: Dict) -> Dict:
        """Validate GUI state using fast model"""
        try:
            prompt = self.prompt_templates["validation"].format(
                gui_state=json.dumps(gui_state, indent=2)
            )
            
            # Check cache
            cache_key = self._get_cache_key(prompt, self.models["fast"])
            if cache_key in self.cache:
                logger.debug("Using cached validation results")
                return self.cache[cache_key]
                
            await self.rate_limiter.acquire()
            
            response = await self._get_completion(
                prompt,
                model=self.models["fast"],
                temperature=0.1,
                max_tokens=100
            )
            
            results = self._parse_validation(response)
            self.cache[cache_key] = results
            return results
            
        except Exception as e:
            logger.error(f"State validation failed: {str(e)}")
            raise
            
    async def analyze_screenshot(self, screenshot_data: str, gui_state: Dict) -> Dict:
        """Analyze screenshot using vision model"""
        try:
            prompt = self.prompt_templates["vision"].format(
                screenshot=screenshot_data,
                gui_state=json.dumps(gui_state, indent=2)
            )
            
            await self.rate_limiter.acquire()
            
            response = await self._get_completion(
                prompt,
                model=self.models["vision"],
                temperature=0.2,
                max_tokens=500
            )
            
            return self._parse_vision_analysis(response)
            
        except Exception as e:
            logger.error(f"Screenshot analysis failed: {str(e)}")
            raise
            
    async def _get_completion(self,
                            prompt: str,
                            model: str,
                            temperature: float,
                            max_tokens: int,
                            retry_count: int = 0) -> str:
        """Get completion from Claude with retries"""
        try:
            response = await self.client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )
            return response.content
            
        except (RateLimitError, APITimeoutError, APIError) as e:
            await self._handle_api_error(e, retry_count)
            return await self._get_completion(
                prompt, model, temperature, max_tokens, retry_count + 1
            )
            
        except Exception as e:
            logger.error(f"Claude API call failed: {str(e)}")
            raise
            
    def _parse_actions(self, response: str) -> List[Dict]:
        """Parse actions from Claude's response"""
        try:
            # Extract JSON from response
            json_str = response.strip()
            if "```json" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0]
            elif "```" in json_str:
                json_str = json_str.split("```")[1].split("```")[0]
                
            actions = json.loads(json_str)
            
            # Validate actions
            validated_actions = []
            for action in actions:
                if not all(k in action for k in ["action_type", "description"]):
                    logger.warning(f"Invalid action format: {action}")
                    continue
                    
                if action["action_type"] not in ["click", "type", "press", "wait"]:
                    logger.warning(f"Unsupported action type: {action['action_type']}")
                    continue
                    
                validated_actions.append(action)
                
            return validated_actions
            
        except json.JSONDecodeError:
            logger.error("Failed to parse JSON from Claude's response")
            raise
            
    def _parse_validation(self, response: str) -> Dict:
        """Parse validation results"""
        try:
            results = json.loads(response)
            if not isinstance(results, dict):
                raise ValueError("Invalid validation response format")
                
            return {
                "is_valid": results.get("is_valid", False),
                "issues": results.get("issues", [])
            }
        except Exception as e:
            logger.error(f"Failed to parse validation results: {str(e)}")
            return {"is_valid": False, "issues": []}
            
    def _parse_vision_analysis(self, response: str) -> Dict:
        """Parse vision analysis results"""
        try:
            results = json.loads(response)
            if not isinstance(results, dict):
                raise ValueError("Invalid vision analysis response format")
                
            return {
                "matches_state": results.get("matches_state", False),
                "additional_elements": results.get("additional_elements", []),
                "discrepancies": results.get("discrepancies", [])
            }
        except Exception as e:
            logger.error(f"Failed to parse vision analysis: {str(e)}")
            return {
                "matches_state": False,
                "additional_elements": [],
                "discrepancies": []
            }
            
    def clear_cache(self):
        """Clear response cache"""
        self.cache.clear()
        logger.debug("Cleared response cache") 
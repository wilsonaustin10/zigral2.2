import json
import logging
import asyncio
from typing import Optional, Dict, List
from dataclasses import dataclass
from anthropic import AsyncAnthropic

from src.actions.action_cache import ActionSequence, Action, ActionCache

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an AI assistant that analyzes GUI states and plans browser automation actions using Playwright.

Your role is to:
1. Return ONE action at a time in a JSON array
2. Wait for that action to complete before planning the next action
3. For navigation, ALWAYS use direct URLs instead of multiple steps

URL Construction Rules:
1. Currency Pairs: https://www.investing.com/currencies/XXX-YYY
   Example: GBP/USD -> https://www.investing.com/currencies/gbp-usd
2. Historical Data: https://www.investing.com/currencies/XXX-YYY-historical-data
   Example: GBP/USD -> https://www.investing.com/currencies/gbp-usd-historical-data

IMPORTANT:
- NEVER return multiple navigation steps
- NEVER navigate to homepage first
- ALWAYS use direct URLs
- Return empty array [] when task is complete

Examples:

For "find GBP/USD":
[{"type": "navigate", "url": "https://www.investing.com/currencies/gbp-usd"}]

For "get EUR/USD historical data":
[{"type": "navigate", "url": "https://www.investing.com/currencies/eur-usd-historical-data"}]

For "get historical data for GBP/USD from 2023-01-01 to 2024-01-01":
1. First navigate to historical page:
[{"type": "navigate", "url": "https://www.investing.com/currencies/gbp-usd-historical-data"}]

2. After navigation, click date range selector:
[{"type": "click", "selector": ".flex.items-center.gap-3\\.5.rounded.border"}]

3. After date picker opens, enter start date:
[{"type": "type", "selector": "input[placeholder*='Start']", "text": "2023-01-01"}]

4. Then enter end date:
[{"type": "type", "selector": "input[placeholder*='End']", "text": "2024-01-01"}]

5. Finally click apply:
[{"type": "click", "selector": "button[type='submit'], button:has-text('Apply')"}]

6. Return empty array when dates are set:
[]

Common Elements on Historical Data Page:
- Date Range Selector: ".flex.items-center.gap-3\\.5.rounded.border"
- Start Date Input: "input[placeholder*='Start']"
- End Date Input: "input[placeholder*='End']"
- Apply Button: "button[type='submit'], button:has-text('Apply')"
- Download Button: "div.cursor-pointer.items-center.gap-3.hidden.md\\:flex"

Remember:
- ONE action at a time
- Direct URLs only
- Empty array [] when done
- Wait for each action to complete before returning next action"""

class ClaudeClient:
    """Client for interacting with Claude API"""
    
    def __init__(self, api_key: str, config_manager=None):
        """Initialize Claude client"""
        self.client = AsyncAnthropic(
            api_key=api_key,
            max_retries=2,
            timeout=10.0
        )
        self.model = "claude-3-5-sonnet-20241022"
        self.action_cache = ActionCache()  # Initialize action cache
        self.config = config_manager.config if config_manager else None
        
    async def _get_site_specific_prompt(self, url: str, task: str) -> str:
        """Get site-specific prompt based on URL and task type"""
        if not self.config or not self.config.prompts:
            return SYSTEM_PROMPT

        # Determine which site we're on
        site = None
        if "investing.com" in url:
            site = "investing.com"
        elif "linkedin.com" in url:
            site = "linkedin.com"
        
        if not site or site not in self.config.prompts:
            return SYSTEM_PROMPT

        prompts = self.config.prompts[site]
        
        # Determine task type and get specific prompt
        if site == "investing.com":
            if any(term in task.lower() for term in ["search", "find", "get", "lookup"]):
                # Extract symbol from task for search prompt
                words = task.lower().split()
                symbol_idx = -1
                for term in ["for", "symbol", "pair"]:
                    if term in words:
                        symbol_idx = words.index(term) + 1
                        break
                symbol = words[symbol_idx] if symbol_idx < len(words) and symbol_idx > -1 else ""
                
                # Use search-specific prompt with symbol
                if symbol and "search" in prompts:
                    return prompts["search"].format(symbol=symbol)
        
        # Default to base prompt for the site
        return prompts.get("base", SYSTEM_PROMPT)

    async def plan_actions(self, task: str, gui_state: dict, action_history: Optional[List[Dict]] = None) -> Optional[List[Action]]:
        """Plan actions for a given task based on current GUI state and action history"""
        try:
            # First check cache for similar task
            cached_sequence = await self.action_cache.get_similar_task(task)
            if cached_sequence:
                logger.info(f"Found cached sequence for task: {task}")
                return cached_sequence.actions

            # Get site-specific prompt based on current URL
            system_prompt = await self._get_site_specific_prompt(gui_state.get("url", ""), task)
            
            # Reduce context size
            reduced_gui_state = self._reduce_gui_state(gui_state)
            reduced_history = []
            if action_history:
                # Only keep last 2 actions to reduce context
                reduced_history = action_history[-2:]
                
            # Build context with emphasis on current state and task progress
            context = (
                f"Task: {task}\n\n"
                f"Current GUI State:\n{json.dumps(reduced_gui_state, indent=2)}"
            )
            
            # Add action history with outcomes if available
            if reduced_history:
                history_str = "\nPrevious Actions and Results:\n"
                for action in reduced_history:
                    history_str += f"- {action['type']}: "
                    if action.get('success'):
                        history_str += "✓ Completed successfully\n"
                    else:
                        history_str += "✗ Failed\n"
                    if action.get('error'):
                        history_str += f"  Error: {action['error']}\n"
                context += history_str
                
                # Add explicit prompt for next action
                context += "\nBased on these results and the current GUI state, what is the next action needed to complete the task?"
            
            # Estimate tokens
            estimated_tokens = len(context.split()) * 1.5  # Rough estimate
            
            # Handle rate limiting with retries
            max_retries = 3
            retry_count = 0
            while retry_count < max_retries:
                try:
                    # Check rate limit before making request
                    if not await self._handle_rate_limit(estimated_tokens):
                        await asyncio.sleep(1)  # Wait before retry
                        retry_count += 1
                        continue
                        
                    # Call Claude API
                    response = await self.client.messages.create(
                        model=self.model,
                        max_tokens=1000,
                        system=system_prompt,
                        messages=[{
                            "role": "user",
                            "content": f"{context}\n\nPlan the next sequence of actions to accomplish this task."
                        }]
                    )
                    
                    if not response.content:
                        logger.error("Empty response from Claude")
                        return None
                        
                    content = response.content[0].text
                    if not content:
                        logger.error("Empty message content")
                        return None
                        
                    # Extract and parse actions
                    start_idx = content.find('[')
                    end_idx = content.rfind(']')
                    if start_idx == -1 or end_idx == -1:
                        logger.error("No action array found in response")
                        return None
                        
                    json_str = content[start_idx:end_idx + 1]
                    actions_json = json.loads(json_str)
                    
                    if not isinstance(actions_json, list):
                        logger.error(f"Invalid response format: {type(actions_json)}")
                        return None
                        
                    # Convert to Action objects
                    actions = []
                    for action_data in actions_json:
                        if not isinstance(action_data, dict):
                            continue
                            
                        action_type = action_data.get("type")
                        if not action_type:
                            continue
                            
                        action = Action(
                            type=action_type,
                            selector=action_data.get("selector"),
                            url=action_data.get("url"),
                            text=action_data.get("text"),
                            timeout=action_data.get("timeout", 5000),
                            key=action_data.get("key")
                        )
                        actions.append(action)
                        
                    return actions
                    
                except Exception as e:
                    if "rate_limit" in str(e).lower():
                        logger.warning(f"Rate limit hit, attempt {retry_count + 1}/{max_retries}")
                        await asyncio.sleep(2 ** retry_count)  # Exponential backoff
                        retry_count += 1
                    else:
                        logger.error(f"Failed to get actions from Claude: {str(e)}")
                        return None
                        
            logger.error("Max retries exceeded for rate limiting")
            return None
            
        except Exception as e:
            logger.error(f"Failed to get actions from Claude: {str(e)}")
            return None

    def _reduce_gui_state(self, gui_state: dict) -> dict:
        """Reduce GUI state size by keeping only essential information"""
        if not gui_state:
            return {}
            
        reduced = {
            "url": gui_state.get("url"),
            "title": gui_state.get("title"),
            "elements": []
        }
        
        # Only keep interactive elements with essential properties
        for element in gui_state.get("elements", []):
            if element.get("clickable") or element.get("tag") in ["input", "button", "a", "select"]:
                reduced_element = {
                    "tag": element.get("tag"),
                    "text": element.get("text", "")[:100],  # Truncate long text
                    "id": element.get("id"),
                    "clickable": element.get("clickable"),
                    "visible": element.get("visible")
                }
                # Only include non-empty values
                reduced_element = {k: v for k, v in reduced_element.items() if v}
                reduced["elements"].append(reduced_element)
                
        return reduced

    async def _handle_rate_limit(self, estimated_tokens: int) -> bool:
        """Check if the current rate limit allows for the request"""
        # This is a placeholder implementation. You might want to implement a more robust rate limit checking mechanism
        # based on your Claude API usage and the estimated_tokens.
        return True  # Placeholder return, actual implementation needed
        
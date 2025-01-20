import logging
from typing import Optional, Dict, List, Union
from dataclasses import dataclass, field
from datetime import datetime
import uuid
import json
import asyncio
import hashlib
import time

from src.browser.browser_manager import BrowserManager
from src.actions.action_cache import ActionCache, ActionSequence, Action
from src.llm.claude_client import ClaudeClient

logger = logging.getLogger(__name__)

@dataclass
class TaskState:
    """Represents the current state of a task execution"""
    task_id: str
    description: str
    goal_achieved: bool = False
    current_step: int = 0
    total_steps: int = 0
    last_gui_state: Optional[Dict] = None
    action_history: List[Dict] = field(default_factory=list)
    error: Optional[str] = None

class TaskExecutor:
    """Executes user tasks by coordinating browser actions, caching, and LLM planning"""
    
    def __init__(self, browser: BrowserManager, cache: ActionCache, claude: ClaudeClient):
        self.browser = browser
        self.cache = cache
        self.claude = claude
        self.active_tasks = {}  # Store active task states
        self.last_request_time = 0  # Initialize last request time
        
    async def check_status(self, task: str, gui_state: dict) -> bool:
        """Verify task completion by asking Claude"""
        try:
            verification_response = await self.claude.plan_actions(
                f"Verify if the following task was completed successfully: {task}\nCurrent GUI state:\n{json.dumps(gui_state, indent=2)}",
                gui_state,
                action_history=None
            )
            
            # If Claude returns actions, task is not complete
            if verification_response:
                return False
            return True
            
        except Exception as e:
            logger.error(f"Status check failed: {str(e)}")
            return False

    async def execute_request(self, request: str) -> bool:
        """Execute a user request"""
        try:
            self.request = request
            action_results = []
            success = False
            max_retries = 3
            retry_count = 0
            last_url = "about:blank"
            
            # 1. Check cache for similar tasks FIRST
            cached_sequence = await self.cache.get_similar_task(request)
            if cached_sequence:
                logging.info(f"Found cached sequence for task: {request}")
                # Execute cached sequence
                for i, action in enumerate(cached_sequence.actions):
                    result = await self.browser.execute_action(action, i)
                    action_results.append({
                        "action": {
                            "type": action.type,
                            "selector": action.selector,
                            "url": action.url,
                            "text": action.text,
                            "timeout": action.timeout,
                            "key": action.key
                        },
                        "success": result,
                        "gui_state_after": await self._quick_capture_gui_state(),
                        "timestamp": datetime.now().isoformat()
                    })
                    if not result:
                        logging.error(f"Cached action {i} failed: {action}")
                        print("✗ Failed to execute cached sequence")
                        return False
                    await asyncio.sleep(0.2)  # Brief pause between actions
                
                # If we get here, all cached actions succeeded
                success = True
                print("✓ Task completed successfully using cached sequence")
                return True
            
            # 2. No cache hit - proceed with normal execution
            while retry_count < max_retries:
                # Get current state and verify URL has changed from last action
                current_state = await self._quick_capture_gui_state()
                current_url = current_state.get("url", "about:blank")
                
                # Log URL state for debugging
                logging.info(f"Previous URL: {last_url}")
                logging.info(f"Current URL: {current_url}")
                
                # Get next actions from Claude
                actions = await self._get_next_actions_from_claude(
                    current_state,
                    request,
                    action_results
                )
                
                if actions is None:
                    logging.error("Failed to get actions from Claude")
                    print("✗ Failed to plan next actions")
                    retry_count += 1
                    if retry_count >= max_retries:
                        print(f"✗ Failed to plan actions after {max_retries} attempts")
                        break
                    continue
                    
                if not actions:  # Empty list means task is complete
                    success = True
                    print("✓ Task completed successfully")
                    break
                
                # Execute each action
                action_failed = False
                for i, action in enumerate(actions):
                    try:
                        # Execute the action using browser manager
                        result = await self.browser.execute_action(action, i)
                        
                        # For navigation actions, verify URL has changed
                        if action.type == "navigate" and result:
                            # Wait briefly for navigation
                            await asyncio.sleep(1)
                            new_state = await self._quick_capture_gui_state()
                            new_url = new_state.get("url", "about:blank")
                            
                            if new_url == last_url:
                                logging.error("URL did not change after navigation")
                                result = False
                            else:
                                last_url = new_url
                        
                        # Capture state after action
                        gui_state_after = await self._quick_capture_gui_state()
                        
                        # Store result
                        action_results.append({
                            "action": {
                                "type": action.type,
                                "selector": action.selector,
                                "url": action.url,
                                "text": action.text,
                                "timeout": action.timeout,
                                "key": action.key
                            },
                            "success": result,
                            "gui_state_after": gui_state_after,
                            "timestamp": datetime.now().isoformat()
                        })
                        
                        if not result:
                            logging.error(f"Action {i} failed: {action}")
                            print("✗ Failed to execute actions")
                            action_failed = True
                            break
                            
                        # Brief pause to let DOM update
                        await asyncio.sleep(0.2)
                        
                    except Exception as e:
                        logging.error(f"Error executing action {i}: {str(e)}")
                        action_failed = True
                        break
                
                if action_failed:
                    retry_count += 1
                    if retry_count >= max_retries:
                        print(f"✗ Failed after {max_retries} attempts")
                        break
                    logging.info(f"Retrying action sequence (attempt {retry_count + 1}/{max_retries})")
                    continue

            # Store sequence if we have results
            if action_results:
                try:
                    await self.cache.store_sequence_with_results(
                        request, 
                        [Action(
                            type=r["action"]["type"],
                            selector=r["action"]["selector"],
                            url=r["action"]["url"],
                            text=r["action"]["text"],
                            timeout=r["action"]["timeout"],
                            key=r["action"]["key"]
                        ) for r in action_results],
                        action_results,
                        user_confirmed=success
                    )
                except Exception as e:
                    logging.error(f"Failed to store sequence: {str(e)}")

        except Exception as e:
            logging.error(f"Error executing request: {str(e)}")
            print("✗ Task failed due to error")
            success = False

        return success

    async def _get_next_actions_from_claude(self, gui_state: dict, request: str, action_history: List[Dict]) -> Optional[List[Action]]:
        """Get next actions from Claude based on current GUI state and history"""
        try:
            current_url = gui_state.get("url", "")
            logging.info(f"Current URL: {current_url}")
            
            # Step 1: Handle Navigation
            if not action_history or not any(r["success"] and r["action"]["type"] == "navigate" for r in action_history):
                # Check if this is a currency pair request
                import re
                pairs_in_request = re.findall(r'([a-zA-Z]{3})[/-]([a-zA-Z]{3})', request.lower())
                if pairs_in_request:
                    # Use currency pair prompt to construct URL
                    pair = f"{pairs_in_request[0][0]}-{pairs_in_request[0][1]}"
                    url = f"https://www.investing.com/currencies/{pair}"
                    if "historical" in request.lower():
                        url += "-historical-data"
                    return [Action(type="navigate", url=url)]
                elif "investing.com" not in current_url:
                    # Use navigation prompt for initial navigation
                    return [Action(type="navigate", url="https://www.investing.com")]
            
            # Step 2: Handle Historical Data Navigation
            if "historical" in request.lower() and "-historical-data" not in current_url and "/currencies/" in current_url:
                current_pair = current_url.split("/currencies/")[-1]
                return [Action(type="navigate", url=f"https://www.investing.com/currencies/{current_pair}-historical-data")]
            
            # Step 3: Handle Date Range Input
            if "historical-data" in current_url:
                # Only proceed with date range if explicitly requested
                date_terms = ["from", "to", "between", "range"]
                if any(term in request.lower() for term in date_terms):
                    return await self._get_next_date_action(action_history, request)
                else:
                    # If just viewing historical data without date range, we're done
                    return []
            
            # If we've completed all necessary actions, return empty list
            if "/currencies/" in current_url:
                if "-historical-data" in current_url:
                    # Check if we need to handle date range
                    if any(term in request.lower() for term in ["date", "range", "from", "to", "between"]):
                        return await self._get_next_date_action(action_history, request)
                    return []  # Historical data view complete
                elif not "historical" in request.lower():
                    return []  # Currency pair view complete
                
            return []

        except Exception as e:
            logging.error(f"Failed to get next actions from Claude: {str(e)}")
            return None

    async def _get_next_date_action(self, action_history: List[Dict], request: str) -> Optional[List[Action]]:
        """Determine the next action needed for date range entry"""
        try:
            # Extract dates from request
            from datetime import datetime
            import re
            
            # Find dates in various formats
            date_pattern = r'(\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|\d{4}[-/]\d{1,2}[-/]\d{1,2})'
            dates = re.findall(date_pattern, request)
            if len(dates) < 2:
                logging.error("Could not find two dates in request")
                return None
                
            # Parse dates to ensure consistent format
            def parse_date(date_str):
                for fmt in ['%m/%d/%Y', '%Y-%m-%d', '%m-%d-%Y']:
                    try:
                        return datetime.strptime(date_str, fmt).strftime('%m/%d/%Y')
                    except ValueError:
                        continue
                return None
                
            start_date = parse_date(dates[0])
            end_date = parse_date(dates[1])
            
            if not start_date or not end_date:
                logging.error("Failed to parse dates")
                return None
            
            # Format the complete date range string
            date_range = f"{start_date} - {end_date}"
            logging.info(f"Formatted date range: {date_range}")
            
            # Determine which action to return based on history
            clicked_date_picker = any(
                r["success"] and r["action"]["type"] == "click" and "date-picker-wrapper" in str(r["action"].get("selector", ""))
                for r in action_history
            )
            
            # For date range, we only need to click and type once since it's a single input
            entered_date_range = any(
                r["success"] and r["action"]["type"] == "type" and "date-picker-wrapper" in str(r["action"].get("selector", ""))
                for r in action_history
            )
            
            # Return appropriate next action
            if not clicked_date_picker:
                # Use a more reliable selector
                return [Action(type="click", selector="div[data-test='date-picker-wrapper']")]
            elif not entered_date_range:
                # Use the same selector for typing
                return [Action(type="type", selector="div[data-test='date-picker-wrapper']", text=date_range)]
            
            return []  # All date actions completed

        except Exception as e:
            logging.error(f"Error determining next date action: {str(e)}")
            return None

    async def _quick_capture_gui_state(self) -> Dict:
        """Capture GUI state quickly without waiting for full page load"""
        try:
            # Get immediately available DOM elements
            state = await self.browser.page.evaluate("""() => {
                const elements = [];
                const addElement = (el) => {
                    if (!el.tagName) return;
                    
                    // Only get essential info for each element
                    elements.push({
                        tag: el.tagName.toLowerCase(),
                        text: el.innerText?.trim()?.substring(0, 50), // Limit text length
                        clickable: (
                            el.tagName === 'BUTTON' ||
                            el.tagName === 'A' ||
                            el.onclick != null ||
                            el.getAttribute('role') === 'button'
                        ),
                        attributes: {
                            type: el.getAttribute('type'),
                            href: el.getAttribute('href'),
                            role: el.getAttribute('role')
                        }
                    });
                };
                
                // Only get interactive elements
                document.querySelectorAll('button, a, input, select, [role="button"], [role="link"]')
                    .forEach(addElement);
                
                return {
                    url: window.location.href,
                    title: document.title,
                    elements: elements
                };
            }""")
            
            return state
            
        except Exception as e:
            logging.error(f"Quick GUI state capture failed: {str(e)}")
            return {}

    def _get_minimal_action_history(self, task_state: TaskState, current_task: str) -> List[dict]:
        """Get minimal relevant action history for the current task"""
        if not task_state.action_history:
            return []
            
        # Only include successful actions
        successful_actions = [h for h in task_state.action_history if h["success"]]
        if not successful_actions:
            return []
            
        # Determine relevant actions based on task type
        relevant_actions = []
        current_task_lower = current_task.lower()
        
        # For navigation-related tasks, include only the last navigation
        if any(term in current_task_lower for term in ["go to", "navigate", "open", "visit"]):
            for action in reversed(successful_actions):
                if action["action"].type == "navigate":
                    relevant_actions.append(self._clean_action_history(action))
                    break
                    
        # For data entry tasks, include last form interaction
        elif any(term in current_task_lower for term in ["type", "enter", "fill", "input"]):
            for action in reversed(successful_actions):
                if action["action"].type in ["type", "click"]:
                    relevant_actions.append(self._clean_action_history(action))
                    if len(relevant_actions) >= 2:  # Include at most 2 form actions
                        break
                        
        # For sequential tasks, include last 2 relevant actions
        else:
            relevant_actions = [self._clean_action_history(action) 
                              for action in successful_actions[-2:]]
        
        return relevant_actions

    def _clean_action_history(self, action_record: dict) -> dict:
        """Remove unnecessary metadata from action history"""
        action = action_record["action"]
        return {
            "type": action.type,
            "selector": action.selector if hasattr(action, "selector") else None,
            "url": action.url if hasattr(action, "url") else None,
            "text": action.text if hasattr(action, "text") else None
        }

    def _estimate_tokens(self, context: dict) -> int:
        """More accurate token count estimation"""
        try:
            # Rough token estimation rules
            json_str = json.dumps(context)
            
            # Count words (roughly 1.3 tokens per word)
            word_count = len(json_str.split()) * 1.3
            
            # Count special characters (roughly 1 token per 2-3 special chars)
            special_chars = sum(1 for c in json_str if not c.isalnum() and not c.isspace())
            special_char_tokens = special_chars / 2.5
            
            # Count numbers (roughly 1 token per 2 digits)
            number_chars = sum(1 for c in json_str if c.isdigit())
            number_tokens = number_chars / 2
            
            return int(word_count + special_char_tokens + number_tokens)
        except Exception:
            # Fallback to simple character-based estimation
            return len(json_str) // 4

    class RateLimitState:
        """Track rate limit state and backoff"""
        def __init__(self):
            self.last_request_time = 0
            self.consecutive_failures = 0
            self.backoff_until = 0
            self.current_token_count = 0
            self.token_reset_time = 0
            self.MAX_TOKENS_PER_MINUTE = 35000  # Buffer below actual 40k limit

        def should_backoff(self) -> bool:
            """Check if we should still be backing off"""
            return time.time() < self.backoff_until

        def update_backoff(self, status_code: int):
            """Update backoff state based on response"""
            if status_code == 429:  # Rate limit exceeded
                self.consecutive_failures += 1
                backoff_seconds = min(60 * (2 ** self.consecutive_failures), 300)  # Max 5 min
                self.backoff_until = time.time() + backoff_seconds
            else:
                self.consecutive_failures = 0
                self.backoff_until = 0

        def can_make_request(self, estimated_tokens: int) -> bool:
            """Check if we can make a request with given token count"""
            current_time = time.time()
            
            # Reset token count if minute has passed
            if current_time >= self.token_reset_time:
                self.current_token_count = 0
                self.token_reset_time = current_time + 60
            
            # Check if adding these tokens would exceed limit
            return (self.current_token_count + estimated_tokens) <= self.MAX_TOKENS_PER_MINUTE

        def record_request(self, token_count: int):
            """Record a successful request"""
            self.current_token_count += token_count
            self.last_request_time = time.time()

    async def _verify_page_load(self, expected_url: str = None, max_attempts: int = 3) -> bool:
        """Enhanced page load verification with human feedback"""
        try:
            # First try automatic verification
            for attempt in range(max_attempts):
                # Wait for critical states
                await self.browser.page.wait_for_load_state("domcontentloaded")
                try:
                    await self.browser.page.wait_for_load_state("networkidle", timeout=5000)
                except Exception:
                    logger.warning("Network not fully idle, continuing with verification")
                
                # Verify URL if provided
                if expected_url:
                    current_url = self.browser.page.url
                    if not self._urls_match(current_url, expected_url):
                        logger.warning(f"URL mismatch. Expected: {expected_url}, Got: {current_url}")
                        if attempt == max_attempts - 1:
                            return await self._get_human_verification("I notice the URL is different than expected. Has the page loaded correctly?")
                
                # Check for loading indicators
                if await self._check_loading_indicators():
                    if attempt == max_attempts - 1:
                        return await self._get_human_verification("I still see loading indicators. Has the page finished loading?")
                    continue
                
                # Handle popups
                await self._handle_conditional_popups()
                
                # If we get here, automatic verification passed
                return True
                
            # If we exhausted attempts, ask human
            return await self._get_human_verification("I'm having trouble verifying if the page has loaded correctly. Can you confirm?")
            
        except Exception as e:
            logger.error(f"Page load verification failed: {str(e)}")
            return await self._get_human_verification("An error occurred during verification. Has the page loaded correctly?")

    async def _check_loading_indicators(self) -> bool:
        """Check for presence of loading indicators"""
        loading_selectors = [
            ".loading-spinner",
            "[role='progressbar']",
            ".loader",
            "#loading"
        ]
        for selector in loading_selectors:
            try:
                is_visible = await self.browser.page.locator(selector).is_visible()
                if is_visible:
                    logger.warning(f"Loading indicator still present: {selector}")
                    return True
            except Exception:
                continue
        return False

    async def _get_human_verification(self, question: str) -> bool:
        """Get human verification and learn from response"""
        response = input(f"{question} (yes/no): ")
        is_success = response.lower() == 'yes'
        
        if is_success:
            # Learn from successful state
            await self._learn_from_success()
        
        return is_success

    async def _learn_from_success(self):
        """Learn from successful page state"""
        try:
            # Capture successful state indicators
            current_url = self.browser.page.url
            
            # Get visible elements that might indicate success
            success_indicators = await self._capture_success_indicators()
            
            # Store learned patterns
            await self._update_verification_patterns(current_url, success_indicators)
            
        except Exception as e:
            logger.error(f"Failed to learn from success: {str(e)}")

    async def _capture_success_indicators(self) -> dict:
        """Capture indicators of successful page load"""
        try:
            indicators = {
                "url": self.browser.page.url,
                "title": await self.browser.page.title(),
                "visible_elements": [],
                "network_state": "idle" if await self._is_network_idle() else "active"
            }
            
            # Capture visible important elements
            important_selectors = [
                "nav",
                "header",
                "main",
                "#content",
                ".main-content",
                "article"
            ]
            
            for selector in important_selectors:
                try:
                    element = self.browser.page.locator(selector)
                    if await element.is_visible():
                        indicators["visible_elements"].append(selector)
                except Exception:
                    continue
            
            return indicators
            
        except Exception as e:
            logger.error(f"Failed to capture success indicators: {str(e)}")
            return {}

    async def _is_network_idle(self) -> bool:
        """Check if network is idle"""
        try:
            await self.browser.page.wait_for_load_state("networkidle", timeout=2000)
            return True
        except Exception:
                return False

    async def _update_verification_patterns(self, url: str, indicators: dict):
        """Update verification patterns based on successful state"""
        try:
            # Parse URL to get domain
            from urllib.parse import urlparse
            domain = urlparse(url).netloc
            
            # Load existing patterns
            patterns = await self._load_verification_patterns()
            
            # Update patterns for this domain
            if domain not in patterns:
                patterns[domain] = []
            
            # Add new pattern
            new_pattern = {
                "url_pattern": url,
                "required_elements": indicators.get("visible_elements", []),
                "network_state": indicators.get("network_state"),
                "success_count": 1
            }
            
            # Check if similar pattern exists and update it
            pattern_updated = False
            for pattern in patterns[domain]:
                if self._patterns_match(pattern, new_pattern):
                    pattern["success_count"] += 1
                    pattern["required_elements"] = list(set(pattern["required_elements"] + new_pattern["required_elements"]))
                    pattern_updated = True
                    break
            
            if not pattern_updated:
                patterns[domain].append(new_pattern)
            
            # Save updated patterns
            await self._save_verification_patterns(patterns)
            
        except Exception as e:
            logger.error(f"Failed to update verification patterns: {str(e)}")

    def _patterns_match(self, pattern1: dict, pattern2: dict) -> bool:
        """Check if two patterns are similar enough to be merged"""
        # Compare URL patterns
        url1 = pattern1.get("url_pattern", "")
        url2 = pattern2.get("url_pattern", "")
        
        # If URLs are from same section of site
        return self._urls_match(url1, url2) or self._url_paths_similar(url1, url2)

    def _url_paths_similar(self, url1: str, url2: str) -> bool:
        """Check if URL paths are similar enough"""
        from urllib.parse import urlparse
        
        def get_path_parts(url):
            return urlparse(url).path.strip("/").split("/")
            
        parts1 = get_path_parts(url1)
        parts2 = get_path_parts(url2)
        
        # If paths have different lengths, check if one is a subset of the other
        if len(parts1) != len(parts2):
            shorter = parts1 if len(parts1) < len(parts2) else parts2
            longer = parts2 if len(parts1) < len(parts2) else parts1
            return all(part in longer for part in shorter)
        
        # If same length, check if most parts match
        matching_parts = sum(1 for p1, p2 in zip(parts1, parts2) if p1 == p2)
        return matching_parts >= len(parts1) * 0.7  # 70% similarity threshold

    async def _handle_conditional_popups(self):
        """Handle popups that appear after user interaction"""
        try:
            # Simulate mouse movement to trigger popups
            await self.browser.page.mouse.move(100, 100)
            await asyncio.sleep(1)  # Brief wait for popup
            
            # Common popup selectors
            popup_selectors = {
                "subscribe": [
                    ".newsletter-popup",
                    "#subscribe-popup",
                    "[data-testid='subscription-wall']"
                ],
                "cookie": [
                    "#onetrust-banner-sdk",
                    ".cookie-notice",
                    "#cookie-law-info-bar"
                ],
                "ad": [
                    "#ad-popup",
                    ".advertisement-overlay",
                    "[data-ad-container]"
                ]
            }
            
            for popup_type, selectors in popup_selectors.items():
                for selector in selectors:
                    try:
                        popup = self.browser.page.locator(selector)
                        if await popup.is_visible():
                            logger.info(f"Found {popup_type} popup, attempting to close")
                            close_button = popup.locator("button, .close, .dismiss")
                            await close_button.click(timeout=2000)
                    except Exception:
                        continue
                        
        except Exception as e:
            logger.warning(f"Error handling conditional popups: {str(e)}")

    def _chunk_gui_state(self, gui_state: dict) -> List[dict]:
        """Split GUI state into manageable chunks based on viewport position"""
        try:
            if not gui_state:
                return []

            # Extract elements list from GUI state
            elements = gui_state.get('elements', [])
            if not elements:
                return [gui_state]  # Return original if no elements

            # Get viewport dimensions
            viewport = gui_state.get('viewport', {})
            viewport_height = viewport.get('height', 0)
            if not viewport_height:
                return [gui_state]  # Return original if no viewport info

            # Calculate chunk boundaries (thirds of viewport)
            chunk_height = viewport_height / 3
            chunks = {
                'top': {'min': 0, 'max': chunk_height},
                'middle': {'min': chunk_height, 'max': chunk_height * 2},
                'bottom': {'min': chunk_height * 2, 'max': viewport_height}
            }

            # Initialize chunks with base GUI state (excluding elements)
            base_state = {k: v for k, v in gui_state.items() if k != 'elements'}
            chunked_states = {
                'top': {**base_state, 'elements': []},
                'middle': {**base_state, 'elements': []},
                'bottom': {**base_state, 'elements': []}
            }

            # Filter and distribute elements to chunks
            for element in elements:
                # Skip non-interactive elements
                if not self._is_interactive_element(element):
                    continue

                # Get element position
                position = element.get('position', {})
                top = position.get('y', 0)
                height = position.get('height', 0)
                element_center = top + (height / 2)

                # Determine which chunk this element belongs to
                for chunk_name, bounds in chunks.items():
                    if bounds['min'] <= element_center < bounds['max']:
                        # Clean element data before adding
                        clean_element = self._clean_element_data(element)
                        chunked_states[chunk_name]['elements'].append(clean_element)
                        break

            # Convert to list and remove empty chunks
            return [chunk for chunk in chunked_states.values() if chunk['elements']]

        except Exception as e:
            logger.error(f"Failed to chunk GUI state: {str(e)}")
            return [gui_state]  # Return original state as fallback

    def _is_interactive_element(self, element: dict) -> bool:
        """Determine if an element is interactive"""
        interactive_tags = {'a', 'button', 'input', 'select', 'textarea'}
        interactive_roles = {'button', 'link', 'textbox', 'combobox', 'checkbox', 'radio'}
        
        tag = element.get('tag', '').lower()
        role = element.get('role', '').lower()
        
        # Check if element is clickable
        is_clickable = element.get('clickable', False)
        has_click_handler = bool(element.get('listeners', {}).get('click'))
        
        return (
            tag in interactive_tags or
            role in interactive_roles or
            is_clickable or
            has_click_handler
        )

    def _clean_element_data(self, element: dict) -> dict:
        """Remove non-essential data from element"""
        essential_keys = {
            'tag', 'role', 'text', 'id', 'name', 'value',
            'href', 'src', 'alt', 'title', 'aria-label',
            'position', 'clickable', 'visible', 'selector'
        }
        
        return {k: v for k, v in element.items() if k in essential_keys}

    def _reduce_context(self, context: dict) -> dict:
        """Reduce context size while maintaining critical information"""
        try:
            # Start with a clean reduced context
            reduced = {
                "task": context["task"],
                "gui_state": self._reduce_gui_state(context.get("gui_state", {})),
                "action_history": context.get("action_history", [])[:2]  # Keep only last 2 actions
            }
            
            return reduced
        except Exception as e:
            logger.error(f"Context reduction failed: {str(e)}")
            return context

    def _reduce_gui_state(self, gui_state: dict) -> dict:
        """Reduce GUI state size by removing redundant info and using pattern references"""
        if not gui_state:
            return {}
            
        try:
            # Keep base state info but clean elements
            reduced_state = {
                "url": gui_state.get("url"),
                "title": gui_state.get("title"),
                "viewport": gui_state.get("viewport"),
                "elements": []
            }
            
            # Process elements
            elements = gui_state.get("elements", [])
            seen_patterns = set()  # Track duplicate patterns
            
            for element in elements:
                # Skip non-interactive elements
                if not self._is_interactive_element(element):
                    continue
                    
                # Generate pattern ID for this element
                pattern_id = self._get_element_pattern_id(element)
                
                # Skip if we've seen this pattern before
                if pattern_id in seen_patterns:
                    continue
                    
                seen_patterns.add(pattern_id)
                
                # Add reduced element with pattern reference
                reduced_element = {
                    "pattern_id": pattern_id,
                    "selector": element.get("selector"),
                    "position": element.get("position"),
                    "visible": element.get("visible", True)
                }
                
                # Only include text if it's short and meaningful
                text = element.get("text", "").strip()
                if text and len(text) < 100 and not text.startswith("data:"):
                    reduced_element["text"] = text
                
                reduced_state["elements"].append(reduced_element)
            
            return reduced_state
            
        except Exception as e:
            logger.error(f"GUI state reduction failed: {str(e)}")
            return gui_state

    def _get_element_pattern_id(self, element: dict) -> str:
        """Generate a unique pattern ID for an element based on its characteristics"""
        try:
            # Extract key characteristics
            tag = element.get("tag", "").lower()
            role = element.get("role", "").lower()
            classes = element.get("class", [])
            
            # Build pattern components
            pattern_parts = []
            
            if tag:
                pattern_parts.append(f"tag:{tag}")
            if role:
                pattern_parts.append(f"role:{role}")
                
            # Add common UI pattern identifiers
            if any(cls.lower() for cls in classes if "btn" in cls.lower()):
                pattern_parts.append("type:button")
            elif any(cls.lower() for cls in classes if "input" in cls.lower()):
                pattern_parts.append("type:input")
            elif any(cls.lower() for cls in classes if "link" in cls.lower()):
                pattern_parts.append("type:link")
                
            # Add position-based pattern
            position = element.get("position", {})
            if position:
                x = position.get("x", 0)
                y = position.get("y", 0)
                if x < 100:
                    pattern_parts.append("pos:left")
                elif x > 500:
                    pattern_parts.append("pos:right")
                if y < 100:
                    pattern_parts.append("pos:top")
                elif y > 500:
                    pattern_parts.append("pos:bottom")
            
            # Generate unique ID
            return hashlib.md5("|".join(pattern_parts).encode()).hexdigest()[:8]
            
        except Exception:
            return "unknown"

    def _urls_match(self, url1: str, url2: str) -> bool:
        """Compare URLs ignoring minor differences"""
        from urllib.parse import urlparse
        
        def normalize_url(url):
            parsed = urlparse(url)
            return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            
        return normalize_url(url1) == normalize_url(url2)

    async def _is_task_complete(self, task: str, gui_state: dict, task_state: TaskState) -> bool:
        """Check if task is complete by asking Claude"""
        try:
            verification = await self.claude.plan_actions(
                f"Verify if this task is complete: {task}\n"
                f"Current GUI state:\n{json.dumps(gui_state, indent=2)}",
                gui_state,
                action_history=task_state.action_history
            )
            
            # Empty response means task is complete
            return not verification
            
        except Exception as e:
            logger.error(f"Task completion check failed: {str(e)}")
            return False

    async def _verify_completion(self, task: str, task_state: TaskState) -> bool:
        """Get final verification from user and update cache if successful"""
        user_verification = input("Did I complete the task as expected? (yes/no): ")
        
        if user_verification.lower() == 'yes':
            # Store successful sequence if we created one
            if task_state.action_history and not await self.cache.get_similar_task(task):
                actions = [h["action"] for h in task_state.action_history if h["success"]]
                await self.cache.store_sequence(task, actions)
                await self.cache.update_stats(task, 0.0, True)
            task_state.goal_achieved = True
            print("What would you like me to do next?")
            return True
        else:
            print("Can you clarify your request again for me?")
            return False
            
    async def _execute_sequence(self, sequence: Union[ActionSequence, List[Action]], task_state: TaskState) -> bool:
        """Execute a sequence of actions"""
        try:
            actions = sequence.actions if isinstance(sequence, ActionSequence) else sequence
            task_state.total_steps = len(actions)
            
            # Track state for rollback
            successful_actions = []
            
            for i, action in enumerate(actions):
                task_state.current_step = i + 1
                
                # After navigation actions, add preparatory actions
                if action.type == 'navigate':
                    success = await self.browser.execute_action(action, i)
                    if not success:
                        logger.error(f"Navigation failed: {action}")
                        return False
                        
                    # Add preparatory actions after navigation
                    await self._execute_preparatory_actions()
                else:
                    # Execute regular action
                    success = await self.browser.execute_action(action, i)
                if not success:
                        logger.error(f"Action {i + 1} failed: {action}")
                        return False
                
                # Record successful action
                successful_actions.append(action)
                task_state.action_history.append({
                    "action": action,
                    "timestamp": datetime.now().isoformat(),
                    "success": success
                })
                
                # Verify action result if verification specified
                if hasattr(action, 'verification') and action.verification:
                    try:
                        verified = await self._verify_action(action)
                        if not verified:
                            logger.error(f"Action verification failed: {action}")
                            return False
                    except Exception as e:
                        logger.error(f"Verification failed: {str(e)}")
                    return False
                
                # Allow time for page updates
                await asyncio.sleep(1)
            
            return True
            
        except Exception as e:
            logger.error(f"Action execution failed: {e}")
            return False
            
    async def _execute_preparatory_actions(self):
        """Execute actions to stabilize page state after navigation"""
        try:
            # Wait for initial load
            await asyncio.sleep(2)
            
            # Scroll actions to trigger lazy loading
            await self._perform_scroll_actions()
            
            # Move cursor to trigger hover states
            await self._perform_cursor_movements()
            
            # Click in blank areas to trigger popups
            await self._perform_blank_clicks()
            
            # Handle any popups that appeared
            await self._handle_conditional_popups()
            
        except Exception as e:
            logger.warning(f"Preparatory actions failed: {str(e)}")

    async def _perform_scroll_actions(self):
        """Perform scroll actions to trigger lazy loading"""
        try:
            # Get page dimensions
            dimensions = await self.browser.page.evaluate("""() => {
                return {
                    height: document.documentElement.scrollHeight,
                    width: document.documentElement.scrollWidth
                }
            }""")
            
            # Scroll points (25%, 50%, 75% of page)
            scroll_points = [
                dimensions['height'] * 0.25,
                dimensions['height'] * 0.50,
                dimensions['height'] * 0.75
            ]
            
            for scroll_y in scroll_points:
                await self.browser.page.evaluate(f"window.scrollTo(0, {scroll_y})")
                await asyncio.sleep(0.5)
            
            # Scroll back to top
            await self.browser.page.evaluate("window.scrollTo(0, 0)")
            await asyncio.sleep(0.5)
            
        except Exception as e:
            logger.warning(f"Scroll actions failed: {str(e)}")

    async def _perform_cursor_movements(self):
        """Move cursor to trigger hover states and popups"""
        try:
            # Get viewport dimensions
            viewport = await self.browser.page.viewport_size
            if not viewport:
                return
                
            # Move cursor to different areas
            movements = [
                (100, 100),  # Top left
                (viewport['width'] - 100, 100),  # Top right
                (viewport['width'] // 2, viewport['height'] // 2),  # Center
                (100, viewport['height'] - 100),  # Bottom left
                (viewport['width'] - 100, viewport['height'] - 100)  # Bottom right
            ]
            
            for x, y in movements:
                await self.browser.page.mouse.move(x, y)
                await asyncio.sleep(0.5)
            
        except Exception as e:
            logger.warning(f"Cursor movements failed: {str(e)}")

    async def _perform_blank_clicks(self):
        """Click in blank areas to trigger popups"""
        try:
            # Get viewport dimensions
            viewport = await self.browser.page.viewport_size
            if not viewport:
                return
                
            # Try to find and click blank areas
            blank_areas = [
                (viewport['width'] // 2, 50),  # Top center
                (viewport['width'] // 2, viewport['height'] - 50),  # Bottom center
                (50, viewport['height'] // 2),  # Left center
                (viewport['width'] - 50, viewport['height'] // 2)  # Right center
            ]
            
            for x, y in blank_areas:
                try:
                    # Check if point is clickable (not over an element)
                    element = await self.browser.page.evaluate(f"""() => {{
                        let element = document.elementFromPoint({x}, {y});
                        return element ? element.tagName : null;
                    }}""")
                    
                    if not element or element.lower() in ['body', 'html']:
                        await self.browser.page.mouse.click(x, y)
                        await asyncio.sleep(0.5)
                        
                        # Check for and handle any popups that appeared
                        await self._handle_conditional_popups()
                        
                except Exception:
                    continue
            
        except Exception as e:
            logger.warning(f"Blank clicks failed: {str(e)}")

    async def _verify_action(self, action: Action) -> bool:
        """Verify action result based on verification criteria"""
        try:
            if not action.verification:
                return True
                
            if action.verification == "is_visible":
                element = await self.browser.page.wait_for_selector(
                    action.selector,
                    state="visible",
                    timeout=5000
                )
                return bool(element)
                
            # Add more verification types as needed
            
            return True
            
        except Exception as e:
            logger.error(f"Action verification failed: {str(e)}")
            return False
            
    async def _rollback_action(self, action: Action) -> None:
        """Attempt to rollback an action"""
        try:
            if action.type == "navigate":
                await self.browser.page.go_back()
            elif action.type == "type":
                # Clear typed text
                await self.browser.page.fill(action.selector, "")
            elif action.type == "click":
                # Can't really rollback a click, but can log it
                logger.info(f"Cannot rollback click action: {action}")
            # Add more rollback handlers as needed
            
        except Exception as e:
            logger.error(f"Rollback failed for action {action}: {str(e)}")
            raise
            
    async def _capture_gui_state(self) -> Dict:
        """Capture the current state of the GUI"""
        page_state = await self.browser.get_active_page()
        return page_state

    async def _find_partial_matches(self, task: str) -> List[ActionSequence]:
        """Find cached sequences that might be part of completing this task"""
        partial_matches = []
        
        # Common task components
        navigation_tasks = [
            "go to",
            "navigate to",
            "open",
            "visit"
        ]
        
        # Extract target from task
        task_parts = task.lower().split()
        
        # Look for navigation sequences first
        for nav in navigation_tasks:
            if nav in task.lower():
                nav_target = task[task.lower().index(nav) + len(nav):].strip()
                nav_sequence = await self.cache.get_similar_task(f"{nav} {nav_target}")
                if nav_sequence and nav_sequence.success_rate > 0.8:
                    partial_matches.append(nav_sequence)
        
        # Look for known sub-tasks
        known_tasks = {
            "gbp/usd": ["currency", "pair", "gbp", "usd"],
            "historical data": ["historical", "history", "past"],
            "news": ["news", "article", "story"],
            "technical analysis": ["technical", "analysis", "chart"]
        }
        
        for key, keywords in known_tasks.items():
            if any(word in task_parts for word in keywords):
                cached = await self.cache.get_similar_task(f"find {key}")
                if cached and cached.success_rate > 0.8:
                    partial_matches.append(cached)
        
        return partial_matches 

    def _serialize_for_json(self, data):
        """Recursively convert data to JSON-serializable format"""
        if isinstance(data, dict):
            return {key: self._serialize_for_json(value) for key, value in data.items()}
        elif isinstance(data, list):
            return [self._serialize_for_json(item) for item in data]
        elif isinstance(data, datetime):
            return data.isoformat()
        elif hasattr(data, '__dict__'):  # Handle objects
            return self._serialize_for_json(data.__dict__)
        return data

    def _serialize_timestamp(self, timestamp) -> str:
        """Convert timestamp to string format safely"""
        if isinstance(timestamp, datetime):
            return timestamp.isoformat()
        elif isinstance(timestamp, str):
            return timestamp
        else:
            return datetime.now().isoformat() 
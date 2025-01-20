from typing import Dict, Optional
import logging
import random
import asyncio
from playwright.async_api import Page, ElementHandle
from config.settings import config

logger = logging.getLogger(__name__)

class ActionExecutor:
    """Executes browser actions with human-like patterns"""
    
    def __init__(self):
        self.typing_speeds = {
            'slow': {'min': 100, 'max': 300},
            'normal': {'min': 50, 'max': 150},
            'fast': {'min': 30, 'max': 100}
        }
        
    async def execute_action(self, action: Dict) -> Dict:
        """
        Execute a single action with human-like behavior.
        
        Args:
            action: Dictionary containing action details
            
        Returns:
            Dict containing action result
            
        Raises:
            Exception: If action execution fails
        """
        try:
            action_type = action["type"]
            selector = action.get("selector")
            value = action.get("value") or action.get("text")
            url = action.get("url")
            key = action.get("key")
            
            logger.debug(f"Executing {action_type} action")
            
            # Wait for page to be ready before any action
            if action_type != "navigate":
                try:
                    await self.page.wait_for_load_state('domcontentloaded', timeout=5000)
                except Exception as e:
                    logger.warning(f"Page not fully loaded, but proceeding: {str(e)}")
            
            result = None
            if action_type == "click":
                result = await self._execute_click(selector)
            elif action_type == "type":
                result = await self._execute_type(selector, value)
            elif action_type == "press":
                result = await self._execute_keypress(key)
            elif action_type == "wait":
                timeout = value if value else 5000
                result = await self._execute_wait(int(timeout))
            elif action_type == "navigate":
                result = await self.page.goto(url, wait_until='domcontentloaded')
                if result:
                    try:
                        await self.page.wait_for_load_state('networkidle', timeout=5000)
                    except Exception as e:
                        logger.warning(f"Network not fully idle: {str(e)}")
            else:
                raise ValueError(f"Unsupported action type: {action_type}")
                
            # Wait for any animations to complete
            try:
                await self.page.wait_for_function(
                    '() => !document.querySelector(":active, :focus, [aria-busy=true], .loading, .animating")',
                    timeout=2000
                )
            except Exception as e:
                logger.warning(f"Some elements still active/animating: {str(e)}")
                
            return {
                "status": "success",
                "action": action,
                "result": result
            }
            
        except Exception as e:
            logger.error(f"Action execution failed: {str(e)}")
            return {
                "status": "error",
                "action": action,
                "error": str(e)
            }
            
    async def _execute_click(self, selector: str) -> Dict:
        """Execute a click with human-like mouse movement"""
        try:
            # Wait for element with retry
            element = await self._wait_for_element_with_retry(selector)
            if not element:
                raise ValueError(f"Element not found: {selector}")
                
            # Ensure element is visible and clickable
            await element.wait_for_element_state('visible')
            await element.scroll_into_view_if_needed()
            
            # Get element center position
            box = await element.bounding_box()
            if not box:
                raise ValueError("Could not get element position")
                
            center_x = box["x"] + box["width"] / 2
            center_y = box["y"] + box["height"] / 2
            
            # Move mouse and click with human-like behavior
            await self._human_like_mouse_move(center_x, center_y)
            await element.click(delay=random.randint(50, 150))
            
            return {"clicked": True}
            
        except Exception as e:
            logger.error(f"Click failed: {str(e)}")
            raise
            
    async def _execute_type(self, selector: str, text: str) -> Dict:
        """Execute typing with human-like timing"""
        try:
            # Click element first
            await self._execute_click(selector)
            
            # Random initial pause
            if random.random() < 0.3:
                await self._random_delay(500, 1200)
            
            chars_typed = 0
            for i, char in enumerate(text):
                # Pause at natural breakpoints
                if char in ['.', ',', '!', '?', '\n']:
                    await self._random_delay(300, 800)
                
                # Simulate typo
                if random.random() < 0.05:
                    wrong_char = chr(ord(char) + random.randint(-1, 1))
                    await self.page.keyboard.type(wrong_char)
                    await self._random_delay(50, 150)
                    await self.page.keyboard.press('Backspace')
                    await self._random_delay(50, 150)
                
                # Type correct character
                await self.page.keyboard.type(char)
                chars_typed += 1
                
                # Variable delays between characters
                speed = self._get_typing_speed(char)
                await self._random_delay(
                    self.typing_speeds[speed]['min'],
                    self.typing_speeds[speed]['max']
                )
            
            return {"chars_typed": chars_typed}
            
        except Exception as e:
            logger.error(f"Typing failed: {str(e)}")
            raise
            
    async def _execute_keypress(self, key: str) -> Dict:
        """Execute a single keypress"""
        try:
            await self.page.keyboard.press(key)
            return {"key_pressed": key}
        except Exception as e:
            logger.error(f"Keypress failed: {str(e)}")
            raise
            
    async def _execute_wait(self, duration: int) -> Dict:
        """Execute a wait with natural movements"""
        try:
            end_time = asyncio.get_event_loop().time() + (duration / 1000)
            
            while asyncio.get_event_loop().time() < end_time:
                # Occasional mouse movement
                if random.random() < 0.3:
                    current_pos = await self.page.mouse.position()
                    await self.page.mouse.move(
                        current_pos["x"] + random.uniform(-50, 50),
                        current_pos["y"] + random.uniform(-50, 50)
                    )
                
                await self._random_delay(300, 800)
                
            return {"waited": duration}
            
        except Exception as e:
            logger.error(f"Wait failed: {str(e)}")
            raise
            
    async def _wait_for_element(self, selector: str) -> Optional[ElementHandle]:
        """Wait for element to be ready"""
        try:
            element = await self.page.wait_for_selector(
                selector,
                state="visible",
                timeout=config.safety.action_timeout
            )
            
            if not element:
                return None
                
            # Wait for element to be enabled
            is_enabled = await element.is_enabled()
            if not is_enabled:
                await self.page.wait_for_selector(
                    selector,
                    state="enabled",
                    timeout=config.safety.action_timeout
                )
                
            return element
            
        except Exception as e:
            logger.error(f"Wait for element failed: {str(e)}")
            return None
            
    def _generate_movement_curve(self, 
                               start_x: float, 
                               start_y: float,
                               end_x: float,
                               end_y: float,
                               control_points: int = 3) -> list:
        """Generate natural mouse movement curve using bezier"""
        points = []
        
        # Generate control points
        controls = []
        for _ in range(control_points):
            controls.append({
                'x': random.uniform(min(start_x, end_x), max(start_x, end_x)),
                'y': random.uniform(min(start_y, end_y), max(start_y, end_y))
            })
        
        # Generate points along curve
        steps = random.randint(25, 35)
        for i in range(steps + 1):
            t = i / steps
            point = self._bezier_point(t, start_x, start_y, end_x, end_y, controls)
            points.append(point)
        
        return points
        
    def _bezier_point(self,
                     t: float,
                     x1: float,
                     y1: float,
                     x2: float,
                     y2: float,
                     controls: list) -> Dict:
        """Calculate point along bezier curve"""
        # Start point
        x = (1 - t) * x1
        y = (1 - t) * y1
        
        # Control points
        for i, control in enumerate(controls, 1):
            coef = len(controls) + 1
            x += coef * (t ** i) * (1 - t) ** (len(controls) - i) * control['x']
            y += coef * (t ** i) * (1 - t) ** (len(controls) - i) * control['y']
        
        # End point
        x += (t ** (len(controls) + 1)) * x2
        y += (t ** (len(controls) + 1)) * y2
        
        return {'x': x, 'y': y}
        
    def _get_typing_speed(self, char: str) -> str:
        """Determine typing speed based on character"""
        if char in [' ', '\n', '\t']:
            return random.choice(['normal', 'fast'])
        if char in ['.', ',', '!', '?']:
            return 'slow'
        return 'normal'
        
    async def _random_delay(self, min_ms: int, max_ms: int):
        """Add randomized delay"""
        delay = random.uniform(min_ms, max_ms)
        await asyncio.sleep(delay / 1000) 

    async def _wait_for_element_with_retry(self, selector: str, max_retries: int = 3) -> Optional[ElementHandle]:
        """Wait for element with retries"""
        for attempt in range(max_retries):
            try:
                element = await self.page.wait_for_selector(
                    selector,
                    state='visible',
                    timeout=5000
                )
                if element:
                    return element
            except Exception as e:
                if attempt == max_retries - 1:
                    logger.error(f"Failed to find element after {max_retries} attempts: {str(e)}")
                    return None
                logger.warning(f"Retry {attempt + 1}/{max_retries} finding element: {str(e)}")
                await asyncio.sleep(1)
        return None

    async def _human_like_mouse_move(self, target_x: float, target_y: float):
        """Move mouse in a human-like way"""
        current_x, current_y = 0, 0  # Get current position
        
        # Generate smooth curve points
        points = self._generate_movement_curve(current_x, current_y, target_x, target_y)
        
        # Move through points with variable speed
        for point in points:
            await self.page.mouse.move(
                point["x"],
                point["y"],
                steps=random.randint(1, 5)
            )
            await self._random_delay(10, 30) 
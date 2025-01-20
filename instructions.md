---

# LAM (Large Action Model) Agent Development Document

## Table of Contents

1. **Project Setup**
2. **High-Level Architecture**
3. **Step-by-Step Implementation**
   - 3.1. Project Dependencies
   - 3.2. Environment Configuration
   - 3.3. GUI State Representation
   - 3.4. Prompt Construction
   - 3.5. Claude Integration
   - 3.6. Action Execution with Playwright
   - 3.7. Safety Mechanisms
   - 3.8. Anti-Detection Patterns
   - 3.9. Rate Limiting & Caching
   - 3.10. Configuration Management
   - 3.11. Checkpoints & Rollbacks
   - 3.12. Error Reporting
4. **Testing & Iteration**
5. **Future Enhancements**

---

## 1. Project Setup

**Directory Structure**:
```
zigral/
  ├─ src/
  │  ├─ state/
  │  │  ├─ gui_observer.py      # Captures GUI state
  │  │  └─ state_encoder.py     # Encodes state for LLM
  │  ├─ actions/
  │  │  ├─ action_executor.py   # Playwright-based execution
  │  │  └─ action_parser.py     # Parses LLM output
  │  ├─ safety/
  │  │  ├─ action_validator.py  # Validates proposed actions
  │  │  └─ user_confirm.py      # Handles user confirmation
  │  ├─ llm/
  │  │  ├─ interface.py         # Claude integration
  │  │  └─ prompts.py          # Prompt engineering
  │  └─ main.py
  ├─ tests/
  └─ requirements.txt
```

---

## 2. High-Level Architecture

1. **User Input**: The user provides a high-level goal (e.g., "Create a new Google Sheet and enter 'Hello' in cell A1")
2. **State Capture**: The system observes and encodes the current GUI state
3. **LLM Planning**: Claude analyzes the state and goal to propose actions
4. **Safety Check**: User reviews and confirms proposed actions
5. **Execution**: Playwright executes approved actions with human-like patterns
6. **Loop**: Process repeats until goal is achieved or user stops

---

## 3. Step-by-Step Implementation

### 3.1. Project Dependencies

```txt
# requirements.txt

# Core Dependencies
anthropic==0.8.0           # Claude API integration
playwright==1.40.0         # Browser automation
pydantic==2.5.2           # Data validation
python-dotenv==1.0.0      # Environment management

# Vision & ML
torch==2.2.0              # Deep learning support
torchvision==0.17.0       # Image processing
transformers==4.37.0      # Model implementations
pillow==10.2.0           # Image handling
opencv-python==4.9.0.80   # Computer vision operations

# Database & Caching
sqlite3                   # Built into Python
redis==5.0.1             # Fast caching (optional)
sqlalchemy==2.0.25       # Database ORM

# Monitoring & Logging
prometheus-client==0.19.0 # Metrics collection
opentelemetry-api==1.21.0 # Distributed tracing
structlog==24.1.0        # Structured logging

# Testing & Development
pytest==8.0.0
pytest-asyncio==0.23.5   # Async test support
pytest-cov==4.1.0        # Coverage reporting
black==24.1.1            # Code formatting
mypy==1.8.0              # Type checking
```

### 3.2. Environment Configuration

```python
# config/settings.py
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
    
class CacheConfig(BaseSettings):
    """Caching configuration"""
    action_cache_size: int = 1000
    feature_cache_size: int = 100
    cache_ttl: int = 3600  # 1 hour
    use_redis: bool = False
    redis_url: Optional[str] = None

class Config(BaseSettings):
    """Main configuration"""
    vision: VisionConfig
    model: ModelConfig
    cache: CacheConfig
    browser: BrowserConfig
    safety: SafetyConfig
    api: APIConfig
    performance: PerformanceConfig
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
```

### 3.3. GUI State Representation

```python
# state/gui_observer.py
from playwright.sync_api import Page
from pydantic import BaseModel

class GUIElement(BaseModel):
    element_type: str  # button, input, text, etc.
    selector: str     # CSS or XPath selector
    text: str | None  # Visible text if any
    location: dict    # x, y coordinates
    attributes: dict  # class, id, etc.

async def capture_gui_state(page: Page) -> list[GUIElement]:
    """
    Captures current GUI state using Playwright
    Returns list of interactive elements
    """
    elements = []
    # Implementation details...
    return elements
```

### 3.4. Prompt Construction

The prompt should be structured to encourage precise, actionable outputs:

```python
PROMPT_TEMPLATE = """You are a GUI automation expert. Given a user goal and current interface state, propose specific actions that can be executed by Playwright.

User Goal: {user_goal}

Current GUI State:
{gui_state}

Previous Actions (if any):
{action_history}

Output ONLY a JSON list of actions in this format:
[
  {{
    "action_type": "click" | "type" | "press" | "wait",
    "selector": "CSS or XPath selector",
    "value": "text to type if needed",
    "description": "Human-readable description of this action"
  }}
]

Each action must be executable by Playwright. Do not include any explanation text outside the JSON."""
```

### 3.5. Claude Integration

```python
# llm/interface.py
import os
import json
from typing import List, Dict
from anthropic import Anthropic, HUMAN_PROMPT, AI_PROMPT

class ClaudeInterface:
    def __init__(self):
        self.client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        self.action_history = []

    async def get_next_actions(self, goal: str, gui_state: List[Dict]) -> List[Dict]:
        """
        Get next actions from Claude based on current state and goal
        """
        prompt = self._build_prompt(goal, gui_state)
        
        try:
            response = await self.client.completions.create(
                model="claude-3-sonnet-20240229",
                prompt=f"{HUMAN_PROMPT} {prompt}{AI_PROMPT}",
                max_tokens_to_sample=1024,
        temperature=0.7,
                top_p=0.9,
            )

            actions = self._parse_response(response.completion)
            if actions:
                self.action_history.extend(actions)
            return actions

        except Exception as e:
            print(f"Error getting actions from Claude: {str(e)}")
            return []

    def _build_prompt(self, goal: str, gui_state: List[Dict]) -> str:
        """
        Build a prompt that includes:
        1. The current goal
        2. GUI state
        3. Action history for context
        4. Specific  for Playwright actions
        """
        return PROMPT_TEMPLATE.format(
            user_goal=goal,
            gui_state=json.dumps(gui_state, indent=2),
            action_history=json.dumps(self.action_history[-5:], indent=2) if self.action_history else "[]"
        )

    def _parse_response(self, response: str) -> List[Dict]:
        """
        Parse and validate Claude's response into actionable steps
        """
        try:
            # Extract JSON from response (in case there's additional text)
            json_str = response.strip()
            if "```json" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0]
            elif "```" in json_str:
                json_str = json_str.split("```")[1].split("```")[0]
            
            actions = json.loads(json_str)
            
            # Validate each action has required fields
            for action in actions:
                if not all(k in action for k in ["action_type", "selector", "description"]):
                    print(f"Invalid action format: {action}")
                    continue
                    
                # Validate action_type is supported
                if action["action_type"] not in ["click", "type", "press", "wait"]:
                    print(f"Unsupported action type: {action['action_type']}")
                    continue

            return actions

        except json.JSONDecodeError:
            print("Failed to parse JSON from Claude's response:")
            print(response)
            return []
        except Exception as e:
            print(f"Error parsing Claude's response: {str(e)}")
        return []
```

### 3.6. Parsing LLM Responses

```python
# llm/response_parser.py
from typing import List, Dict, Optional
from pydantic import BaseModel, Field

class Action(BaseModel):
    """Validated action model for LLM responses"""
    action_type: str = Field(..., regex="^(click|type|press|wait)$")
    selector: str
    value: Optional[str] = None
    description: str

class ResponseParser:
    def __init__(self):
        self.supported_actions = ["click", "type", "press", "wait"]

    def parse_response(self, response: str) -> List[Dict]:
        """
        Parse and validate Claude's response into structured actions
        Handles multiple response formats and validates against schema
        """
        try:
            # Clean and extract JSON
            json_str = self._extract_json(response)
            if not json_str:
                return []

            # Parse JSON into raw actions
            raw_actions = json.loads(json_str)
            if not isinstance(raw_actions, list):
                print("Response is not a list of actions")
                return []

            # Validate and convert each action
            validated_actions = []
            for raw_action in raw_actions:
                try:
                    action = Action(**raw_action)
                    validated_actions.append(action.dict())
                except Exception as e:
                    print(f"Invalid action format: {raw_action}")
                    print(f"Error: {str(e)}")
                    continue

            return validated_actions

        except Exception as e:
            print(f"Error parsing response: {str(e)}")
            return []

    def _extract_json(self, response: str) -> Optional[str]:
        """
        Extract JSON from various response formats:
        1. Pure JSON
        2. Markdown code blocks
        3. Mixed text with JSON
        """
        response = response.strip()

        # Try to extract from markdown code block
        if "```json" in response:
            try:
                return response.split("```json")[1].split("```")[0].strip()
            except IndexError:
                pass

        # Try to extract from generic code block
        if "```" in response:
            try:
                return response.split("```")[1].strip()
            except IndexError:
                pass

        # Try to find JSON array pattern
        import re
        json_pattern = r'\[[\s\S]*\]'
        match = re.search(json_pattern, response)
        if match:
            return match.group(0)

        # If no patterns match, return the original string
        # (will be validated as JSON later)
        return response

    def validate_action_sequence(self, actions: List[Dict]) -> bool:
        """
        Validate that the sequence of actions makes logical sense
        e.g., can't type into an element without clicking it first
        """
        last_clicked = None
        
        for action in actions:
            if action["action_type"] == "type" and last_clicked != action["selector"]:
                print(f"Warning: Typing into {action['selector']} without clicking first")
                return False
                
            if action["action_type"] == "click":
                last_clicked = action["selector"]
                
        return True

    def enrich_actions(self, actions: List[Dict]) -> List[Dict]:
        """
        Add additional metadata and safety checks to actions
        """
        enriched = []
        for action in actions:
            # Add timing constraints
            if action["action_type"] == "type":
                action["min_delay"] = 50  # ms between keystrokes
                action["max_delay"] = 150
            elif action["action_type"] == "click":
                action["move_duration"] = random.randint(300, 800)  # ms for mouse movement

            # Add verification steps
            action["verify"] = {
                "timeout": 5000,  # ms to wait for element
                "visible": True,  # element must be visible
                "enabled": True,  # element must be enabled
            }

            enriched.append(action)

        return enriched

### 3.7. Action Execution with Playwright

```python
# actions/action_executor.py
from playwright.sync_api import Page
import random
import math
from typing import Dict, List

class ActionExecutor:
    def __init__(self, page: Page):
        self.page = page
        
        # Realistic typing speed variations
        self.typing_speeds = {
            'slow': {'min': 100, 'max': 300},    # ~40 WPM
            'normal': {'min': 50, 'max': 150},   # ~60 WPM
            'fast': {'min': 30, 'max': 100}      # ~80 WPM
        }
        self.current_speed = 'normal'
        
        # Natural mouse movement delays
        self.mouse_move_delays = {
            'start': {'min': 100, 'max': 300},      # Initial movement
            'acceleration': {'min': 200, 'max': 400},# Mid-movement
            'precision': {'min': 300, 'max': 600}    # Near target
        }

    async def execute_action(self, action: dict):
        """Execute a single action with human-like timing"""
        # Randomize speed for this action sequence
        self.current_speed = random.choice(['slow', 'normal', 'normal', 'fast'])
        
        if action["action_type"] == "click":
            await self._humanized_click(action["selector"])
        elif action["action_type"] == "type":
            await self._humanized_type(action["selector"], action["value"])
        elif action["action_type"] == "press":
            await self._humanized_keypress(action["value"])
        elif action["action_type"] == "wait":
            await self._natural_wait(action.get("duration", random.randint(1000, 3000)))

    async def _humanized_type(self, selector: str, text: str):
        """Human-like typing with variable speeds and occasional mistakes"""
        await self.page.click(selector)
        
        # Occasional initial pause before typing
        if random.random() < 0.3:  # 30% chance
            await self._random_delay({'min': 500, 'max': 1200})
        
        for i, char in enumerate(text):
            # Simulate thinking pause at natural breakpoints
            if char in ['.', ',', '!', '?', '\n']:
                await self._random_delay({'min': 300, 'max': 800})
            
            # Simulate typo
            if random.random() < 0.05:  # 5% chance of typo
                wrong_char = chr(ord(char) + random.randint(-1, 1))
                await self.page.keyboard.type(wrong_char)
                await self._random_delay(self.typing_speeds[self.current_speed])
                await self.page.keyboard.press('Backspace')
                await self._random_delay(self.typing_speeds[self.current_speed])
            
            # Type the correct character
            await self.page.keyboard.type(char)
            
            # Variable delays between characters
            speed = self._get_typing_speed(char)
            await self._random_delay(self.typing_speeds[speed])

    async def _humanized_click(self, selector: str):
        """Natural mouse movement and clicking"""
        element = await self.page.wait_for_selector(selector)
        box = await element.bounding_box()
        
        # Random starting position
        start_x = random.randint(0, self.page.viewport_size['width'])
        start_y = random.randint(0, self.page.viewport_size['height'])
        
        # Target position (within element with natural randomness)
        target_x = box['x'] + box['width'] * random.uniform(0.2, 0.8)
        target_y = box['y'] + box['height'] * random.uniform(0.2, 0.8)
        
        # Generate natural movement curve
        points = self._generate_bezier_curve(
            start_x, start_y, target_x, target_y,
            control_points=random.randint(2, 4)
        )
        
        # Move along curve with variable speeds
        for i, point in enumerate(points):
            await self.page.mouse.move(point['x'], point['y'])
            delay = self._get_movement_delay(point, points[-1])
            await self._random_delay(delay)
            
            # Occasionally simulate user uncertainty
            if random.random() < 0.1:  # 10% chance
                await self._simulate_uncertainty(point, target_x, target_y)
        
        # Slight pause before clicking
        await self._random_delay({'min': 50, 'max': 150})
        
        # Randomize click duration
        await self.page.mouse.down()
        await self._random_delay({'min': 20, 'max': 80})
        await self.page.mouse.up()

    async def _simulate_uncertainty(self, point: Dict, target_x: float, target_y: float):
        """Simulate user uncertainty in movement"""
        # Generate small circular motion
        radius = random.uniform(10, 30)
        steps = random.randint(3, 8)
        
        for i in range(steps):
            angle = (i / steps) * 2 * math.pi
            x = point['x'] + radius * math.cos(angle)
            y = point['y'] + radius * math.sin(angle)
            await self.page.mouse.move(x, y)
            await self._random_delay({'min': 100, 'max': 200})

    def _generate_bezier_curve(self, x1: float, y1: float, x2: float, y2: float, control_points: int = 3) -> List[Dict]:
        """Generate natural mouse movement curve using bezier"""
        points = []
        # Generate control points for the curve
        controls = []
        for _ in range(control_points):
            controls.append({
                'x': random.uniform(min(x1, x2), max(x1, x2)),
                'y': random.uniform(min(y1, y2), max(y1, y2))
            })
        
        # Generate points along the curve
        steps = random.randint(25, 35)  # Variable number of steps
        for i in range(steps + 1):
            t = i / steps
            point = self._bezier_point(t, x1, y1, x2, y2, controls)
            points.append(point)
        
        return points

    def _bezier_point(self, t: float, x1: float, y1: float, x2: float, y2: float, controls: List[Dict]) -> Dict:
        """Calculate point along bezier curve"""
        # Implementation of bezier curve calculation
        # Returns {'x': x, 'y': y}
        pass

    def _get_movement_delay(self, current_point: Dict, target_point: Dict) -> Dict:
        """Calculate delay based on distance to target"""
        distance = math.sqrt(
            (current_point['x'] - target_point['x'])**2 +
            (current_point['y'] - target_point['y'])**2
        )
        
        if distance < 100:
            return self.mouse_move_delays['precision']
        elif distance < 500:
            return self.mouse_move_delays['acceleration']
        return self.mouse_move_delays['start']

    def _get_typing_speed(self, char: str) -> str:
        """Determine typing speed based on character context"""
        if char in [' ', '\n', '\t']:
            return random.choice(['normal', 'fast'])  # Faster on spaces
        if char in ['.', ',', '!', '?']:
            return 'slow'  # Slower on punctuation
        return self.current_speed

    async def _random_delay(self, delay_range: Dict):
        """Add randomized delay within range"""
        delay = random.uniform(delay_range['min'], delay_range['max'])
        await self.page.wait_for_timeout(delay)

    async def _natural_wait(self, duration: int):
        """Natural waiting period with small movements"""
        end_time = time.time() + (duration / 1000)
        
        while time.time() < end_time:
            if random.random() < 0.3:  # 30% chance of movement
                # Small mouse movement
                current_pos = await self.page.mouse.position()
                await self.page.mouse.move(
                    current_pos['x'] + random.uniform(-50, 50),
                    current_pos['y'] + random.uniform(-50, 50)
                )
            
            await self._random_delay({'min': 300, 'max': 800})
```

### 3.8. Safety Mechanisms

```python
# safety/user_confirm.py
from typing import List, Dict
import asyncio

class SafetyManager:
    def __init__(self):
        self.stop_requested = False
        self._setup_signal_handlers()

    def _setup_signal_handlers(self):
        """Setup Ctrl+C handler for emergency stop"""
        import signal
        signal.signal(signal.SIGINT, self._emergency_stop)

    async def confirm_actions(self, actions: List[Dict]) -> bool:
        """
        Present actions to user for confirmation
        Returns True if approved, False if rejected
        """
        print("\nProposed Actions:")
        for i, action in enumerate(actions, 1):
            print(f"{i}. {action['description']}")
        
        response = input("\nExecute these actions? (y/n/edit): ").lower()
        if response == 'y':
            return True
        elif response == 'edit':
            return await self._handle_edit(actions)
        return False

    def _emergency_stop(self, *args):
        """Handle emergency stop (Ctrl+C)"""
        self.stop_requested = True
        print("\nEmergency stop requested!")
        raise KeyboardInterrupt()

    async def handle_failure(self, action: Dict, error: Exception) -> str:
        """
        Handle action failure by asking user how to proceed
        Returns: 'retry', 'skip', or 'stop'
        """
        print(f"\nAction failed: {action['description']}")
        print(f"Error: {str(error)}")
        
        response = input("\nHow would you like to proceed? (retry/skip/stop): ")
        return response.lower()
```

### 3.8. Anti-Detection Patterns

```python
# actions/browser_setup.py
from playwright.sync_api import async_playwright
import random

def _generate_hardware_profile():
    """Generate consistent hardware-like properties"""
    return {
        'device_memory': random.choice([4, 8, 16, 32]),
        'hardware_concurrency': random.randint(4, 16),
        'platform': random.choice(['Win32', 'MacIntel', 'Linux x86_64']),
        'gpu_vendor': random.choice([
            'Intel Inc.',
            'NVIDIA Corporation',
            'AMD Radeon'
        ]),
        'gpu_renderer': random.choice([
            'Intel Iris OpenGL Engine',
            'NVIDIA GeForce GTX',
            'AMD Radeon Pro'
        ])
    }

async def setup_browser():
    """Setup browser with comprehensive anti-detection measures"""
    # Generate consistent profile for this session
    hw_profile = _generate_hardware_profile()
    
    browser = await playwright.chromium.launch(
        headless=False,  # Always use headed mode for Google
        args=[
            '--disable-blink-features=AutomationControlled',
            '--disable-automation',
            '--disable-infobars',
            '--disable-dev-shm-usage',
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-accelerated-2d-canvas',
            '--disable-canvas-aa',
            '--disable-2d-canvas-clip-aa',
            '--disable-features=IsolateOrigins,site-per-process',
            # Randomize window size slightly
            f'--window-size={1920 + random.randint(-50, 50)},{1080 + random.randint(-30, 30)}',
        ]
    )

    # Create context with natural browser characteristics
    context = await browser.new_context(
        viewport={'width': 1920, 'height': 1080},
        user_agent=random.choice([
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        ]),
        has_touch=True,
        locale=random.choice(['en-US', 'en-GB', 'en-CA']),
        timezone_id=random.choice([
            'America/Los_Angeles',
            'America/New_York',
            'America/Chicago',
            'Europe/London'
        ]),
        geolocation={
            'latitude': random.uniform(25, 50),
            'longitude': random.uniform(-130, -70)
        },
        permissions=['geolocation'],
        color_scheme=random.choice(['light', 'dark']),
        reduced_motion='no-preference',
        forced_colors='none',
        device_scale_factor=random.choice([1, 1.25, 1.5, 2]),
        is_mobile=False,
        has_touch=True,
        javascript_enabled=True,
        bypass_csp=False
    )

    # Add sophisticated fingerprint evasion
    await context.add_init_script(f"""
        // Override fingerprinting APIs
        const overrides = {hw_profile};
        
        // Override navigator properties
        Object.defineProperties(navigator, {{
            webdriver: {{ get: () => undefined }},
            deviceMemory: {{ get: () => overrides.device_memory }},
            hardwareConcurrency: {{ get: () => overrides.hardware_concurrency }},
            platform: {{ get: () => overrides.platform }},
            plugins: {{
                get: () => [
                    {{ name: 'Chrome PDF Plugin' }},
                    {{ name: 'Chrome PDF Viewer' }},
                    {{ name: 'Native Client' }}
                ]
            }},
            languages: {{
                get: () => ['en-US', 'en']
            }}
        }});

        // Override WebGL fingerprinting
        const getParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(parameter) {{
            if (parameter === 37445) {{ // UNMASKED_VENDOR_WEBGL
                return overrides.gpu_vendor;
            }}
            if (parameter === 37446) {{ // UNMASKED_RENDERER_WEBGL
                return overrides.gpu_renderer;
            }}
            return getParameter.apply(this, arguments);
        }};

        // Override permissions API
        const originalQuery = Permissions.prototype.query;
        Permissions.prototype.query = function(params) {{
            return Promise.resolve({{
                state: "granted",
                onchange: null
            }});
        }};

        // Mask automation flags
        delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
        delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
        delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;
    """)

    # Add random mouse movements and scrolls for initial page load
    page = await context.new_page()
    await page.evaluate("""
        () => {
            // Simulate natural scroll behavior
            const scroll = () => {
                window.scrollBy({
                    top: Math.random() * 100,
                    behavior: 'smooth'
                });
            };
            setInterval(scroll, Math.random() * 2000 + 1000);
        }
    """)

    return context
```

### 3.9. Rate Limiting & Caching

```python
# llm/rate_limiter.py
from datetime import datetime
import sqlite3
import hashlib
from typing import Dict, List, Optional

class RateLimiter:
    def __init__(self, rate: int = 5, burst: int = 10):
        self.rate = rate
        self.burst = burst
        self.tokens = burst
        self.last_update = datetime.now()
        
    async def acquire(self):
        now = datetime.now()
        time_passed = (now - self.last_update).total_seconds()
        self.tokens = min(self.burst, self.tokens + time_passed * self.rate)
        
        if self.tokens < 1:
            return False
            
        self.tokens -= 1
        self.last_update = now
        return True

class ActionCache:
    def __init__(self, db_path: str = "action_cache.db"):
        self.conn = sqlite3.connect(db_path)
        self._init_db()
        
    def _init_db(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS action_sequences (
                hash TEXT PRIMARY KEY,
                goal TEXT,
                initial_state TEXT,
                actions TEXT,
                success_rate REAL,
                avg_execution_time REAL,
                last_used TIMESTAMP,
                use_count INTEGER
            )
        """)
        
    def get_cached_actions(self, goal: str, state: Dict) -> Optional[List[Dict]]:
        hash_key = self._compute_hash(goal, state)
        row = self.conn.execute(
            "SELECT actions FROM action_sequences WHERE hash = ?",
            (hash_key,)
        ).fetchone()
        
        if row:
            self._update_stats(hash_key)
            return json.loads(row[0])
        return None
        
    def cache_actions(self, goal: str, state: Dict, actions: List[Dict], 
                     execution_time: float, success: bool):
        hash_key = self._compute_hash(goal, state)
        self.conn.execute("""
            INSERT OR REPLACE INTO action_sequences 
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'), 1)
        """, (
            hash_key, goal, json.dumps(state), json.dumps(actions),
            1.0 if success else 0.0, execution_time
        ))
        self.conn.commit()
        
    def _compute_hash(self, goal: str, state: Dict) -> str:
        content = json.dumps({"goal": goal, "state": state}, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()
```

### 3.10. Configuration Management

```python
# config/settings.py
from pydantic import BaseSettings, Field
from typing import Dict, Optional

class BrowserConfig(BaseSettings):
    user_agent: str = Field(...)
    viewport: Dict[str, int] = {"width": 1920, "height": 1080}
    locale: str = "en-US"
    timezone: str = "America/Los_Angeles"
    headless: bool = False

class SafetyConfig(BaseSettings):
    require_confirmation: bool = True
    max_retries: int = 3
    action_timeout: int = 30000  # ms
    emergency_stop_enabled: bool = True

class APIConfig(BaseSettings):
    anthropic_api_key: str = Field(..., env="ANTHROPIC_API_KEY")
    rate_limit: int = 5
    burst_limit: int = 10
    timeout: int = 30

class PerformanceConfig(BaseSettings):
    log_timing: bool = True
    resource_monitoring: bool = True
    action_profiling: bool = True

class Config(BaseSettings):
    browser: BrowserConfig
    safety: SafetyConfig
    api: APIConfig
    performance: PerformanceConfig
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
```

### 3.11. Checkpoints & Rollbacks

```python
# state/checkpoint.py
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional
import json
import os

@dataclass
class Checkpoint:
    id: str
    timestamp: datetime
    description: str
    gui_state: Dict
    action_history: List[Dict]
    browser_state: Dict
    version: str

class CheckpointManager:
    def __init__(self, checkpoint_dir: str = "checkpoints"):
        self.checkpoint_dir = checkpoint_dir
        os.makedirs(checkpoint_dir, exist_ok=True)
        
    def create_checkpoint(self, description: str, 
                         gui_state: Dict,
                         action_history: List[Dict],
                         browser_state: Dict,
                         version: str) -> Checkpoint:
        """Create a new checkpoint"""
        checkpoint = Checkpoint(
            id=self._generate_id(),
            timestamp=datetime.now(),
            description=description,
            gui_state=gui_state,
            action_history=action_history,
            browser_state=browser_state,
            version=version
        )
        
        self._save_checkpoint(checkpoint)
        return checkpoint
        
    def rollback(self, checkpoint_id: str) -> Optional[Checkpoint]:
        """Rollback to a specific checkpoint"""
        checkpoint = self._load_checkpoint(checkpoint_id)
        if not checkpoint:
            return None
            
        # Restore state
        return checkpoint
        
    def list_checkpoints(self) -> List[Dict]:
        """List all available checkpoints"""
        checkpoints = []
        for filename in os.listdir(self.checkpoint_dir):
            if filename.endswith(".json"):
                checkpoint = self._load_checkpoint(filename[:-5])
                if checkpoint:
                    checkpoints.append({
                        "id": checkpoint.id,
                        "timestamp": checkpoint.timestamp,
                        "description": checkpoint.description,
                        "version": checkpoint.version
                    })
        return checkpoints
        
    def _generate_id(self) -> str:
        return datetime.now().strftime("%Y%m%d_%H%M%S")
        
    def _save_checkpoint(self, checkpoint: Checkpoint):
        path = os.path.join(self.checkpoint_dir, f"{checkpoint.id}.json")
        with open(path, "w") as f:
            json.dump(checkpoint.__dict__, f, default=str)
            
    def _load_checkpoint(self, checkpoint_id: str) -> Optional[Checkpoint]:
        path = os.path.join(self.checkpoint_dir, f"{checkpoint_id}.json")
        try:
            with open(path) as f:
                data = json.load(f)
                return Checkpoint(**data)
        except:
            return None
```

### 3.12. Error Reporting

```python
# monitoring/error_reporting.py
import logging
import traceback
from datetime import datetime
from typing import Dict, Optional
import json

class ErrorReporter:
    def __init__(self, log_file: str = "errors.log"):
        self.logger = logging.getLogger("error_reporter")
        handler = logging.FileHandler(log_file)
        handler.setFormatter(
            logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        )
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.DEBUG)
        
    def report_error(self, 
                    error: Exception,
                    context: Dict,
                    severity: str = "ERROR",
                    stack_trace: bool = True):
        """Report an error with context"""
        error_data = {
            "timestamp": datetime.now().isoformat(),
            "type": type(error).__name__,
            "message": str(error),
            "severity": severity,
            "context": context
        }
        
        if stack_trace:
            error_data["stack_trace"] = traceback.format_exc()
            
        self.logger.error(json.dumps(error_data))
        
    def report_warning(self, message: str, context: Dict):
        """Report a warning"""
        self.logger.warning(json.dumps({
            "timestamp": datetime.now().isoformat(),
            "message": message,
            "context": context
        }))

class PerformanceMonitor:
    def __init__(self):
        self.logger = logging.getLogger("performance")
        self.metrics = {}
        
    def start_operation(self, operation_name: str):
        """Start timing an operation"""
        self.metrics[operation_name] = {
            "start_time": datetime.now(),
            "steps": []
        }
        
    def log_step(self, operation_name: str, step_name: str):
        """Log a step within an operation"""
        if operation_name in self.metrics:
            self.metrics[operation_name]["steps"].append({
                "name": step_name,
                "timestamp": datetime.now()
            })
            
    def end_operation(self, operation_name: str):
        """End timing an operation and log results"""
        if operation_name in self.metrics:
            start_time = self.metrics[operation_name]["start_time"]
            duration = (datetime.now() - start_time).total_seconds()
            
            self.logger.info(json.dumps({
                "operation": operation_name,
                "duration": duration,
                "steps": self.metrics[operation_name]["steps"]
            }))
            
            del self.metrics[operation_name]
```

### 3.13. Vision Processing

```python
# vision/processor.py
from dataclasses import dataclass
from typing import List, Dict, Optional
import torch
import torchvision
from PIL import Image

@dataclass
class UIElement:
    element_type: str
    confidence: float
    bounding_box: Dict[str, int]
    attributes: Dict[str, str]
    text_content: Optional[str]
    children: List['UIElement']

class FeatureCompressor:
    def __init__(self, compression_ratio: float = 0.5):
        self.compression_ratio = compression_ratio
        self.conv_layers = torch.nn.Sequential(
            torch.nn.Conv2d(3, 16, kernel_size=3, padding=1),
            torch.nn.ReLU(),
            torch.nn.MaxPool2d(2),
            torch.nn.Conv2d(16, 32, kernel_size=3, padding=1),
            torch.nn.ReLU(),
            torch.nn.MaxPool2d(2)
        )
        
    def compress(self, image: Image) -> torch.Tensor:
        """Compress image while preserving UI element features"""
        tensor = torchvision.transforms.ToTensor()(image)
        compressed = self.conv_layers(tensor.unsqueeze(0))
        return compressed

class UIElementDetector:
    def __init__(self, min_confidence: float = 0.7):
        self.min_confidence = min_confidence
        # Initialize detection model (e.g., DETR, Mask R-CNN)
        
    def detect_elements(self, features: torch.Tensor) -> List[UIElement]:
        """Detect UI elements from compressed features"""
        # Implementation using detection model
        pass

class VisualProcessor:
    def __init__(self, config: VisionConfig):
        self.config = config
        self.compressor = FeatureCompressor(config.compression_ratio)
        self.detector = UIElementDetector(config.min_confidence)
        self.feature_cache = {}
        
    async def process_screenshot(self, screenshot: Image) -> List[UIElement]:
        """Process screenshot and return detected UI elements"""
        features = self.compressor.compress(screenshot)
        elements = self.detector.detect_elements(features)
        return elements
```

### 3.14. Action Curriculum

```python
# actions/curriculum.py
from enum import Enum
from typing import List, Dict, Optional
from dataclasses import dataclass

class ActionComplexity(Enum):
    BASIC = 1       # Single clicks, simple typing
    INTERMEDIATE = 2 # Multi-step actions
    COMPLEX = 3     # Workflows requiring state tracking
    ADVANCED = 4    # Error handling, recovery

@dataclass
class ActionTemplate:
    name: str
    complexity: ActionComplexity
    prerequisites: List[str]
    validation_rules: List[str]
    timeout: int  # milliseconds

class ActionCurriculum:
    def __init__(self):
        self.stages = {
            ActionComplexity.BASIC: [
                ActionTemplate(
                    name="click",
                    complexity=ActionComplexity.BASIC,
                    prerequisites=[],
                    validation_rules=["element_visible", "element_enabled"],
                    timeout=5000
                ),
                ActionTemplate(
                    name="type",
                    complexity=ActionComplexity.BASIC,
                    prerequisites=["click"],
                    validation_rules=["element_editable"],
                    timeout=10000
                )
            ],
            ActionComplexity.INTERMEDIATE: [
                ActionTemplate(
                    name="drag_and_drop",
                    complexity=ActionComplexity.INTERMEDIATE,
                    prerequisites=["click"],
                    validation_rules=["element_draggable", "target_valid"],
                    timeout=15000
                )
            ],
            # Add more stages...
        }
        
    def get_action_template(self, action_name: str) -> Optional[ActionTemplate]:
        """Get template for specific action"""
        for templates in self.stages.values():
            for template in templates:
                if template.name == action_name:
                    return template
        return None
```

### 3.15. Agent Architecture

```python
# llm/agent_manager.py
from typing import Dict, List, Optional
from dataclasses import dataclass
from anthropic import Anthropic

@dataclass
class AgentCapability:
    name: str
    description: str
    required_model: str
    max_input_tokens: int
    typical_latency: float  # milliseconds

class BaseAgent:
    def __init__(self, model: str, capabilities: List[AgentCapability]):
        self.client = Anthropic()
        self.model = model
        self.capabilities = capabilities
        
    async def process(self, task: Dict) -> Dict:
        """Process a task within agent's capabilities"""
        pass

class MainAgent(BaseAgent):
    """Handles complex reasoning and coordination"""
    def __init__(self):
        super().__init__(
            model="claude-3-sonnet-20240229",
            capabilities=[
                AgentCapability(
                    name="task_planning",
                    description="Break down complex tasks",
                    required_model="claude-3-sonnet-20240229",
                    max_input_tokens=200000,
                    typical_latency=2000
                )
            ]
        )

class FastAgent(BaseAgent):
    """Handles quick, simple tasks"""
    def __init__(self):
        super().__init__(
            model="claude-3-haiku-20240307",
            capabilities=[
                AgentCapability(
                    name="action_validation",
                    description="Quick validation of simple actions",
                    required_model="claude-3-haiku-20240307",
                    max_input_tokens=20000,
                    typical_latency=200
                )
            ]
        )

class VisionAgent(BaseAgent):
    """Handles complex visual tasks"""
    def __init__(self):
        super().__init__(
            model="claude-3-opus-20240229",
            capabilities=[
                AgentCapability(
                    name="visual_analysis",
                    description="Complex UI understanding",
                    required_model="claude-3-opus-20240229",
                    max_input_tokens=400000,
                    typical_latency=3000
                )
            ]
        )

class AgentManager:
    def __init__(self):
        self.main_agent = MainAgent()
        self.fast_agent = FastAgent()
        self.vision_agent = VisionAgent()
        
    async def route_task(self, task: Dict) -> Dict:
        """Route task to appropriate agent based on requirements"""
        if task.get("requires_vision"):
            return await self.vision_agent.process(task)
        elif task.get("is_simple"):
            return await self.fast_agent.process(task)
        else:
            return await self.main_agent.process(task)
```

---

## 4. Testing & Iteration

### 4.1. Test Structure

The test suite is organized into several key files:

```
zigral/tests/
  ├─ test_action_store.py    # Tests for action chain storage and retrieval
  ├─ test_basic.py          # Core functionality tests
  ├─ test_config.py         # Configuration and environment tests
  └─ test_claude_interface.py # Claude API integration tests
```

### 4.2. Key Test Cases

1. **Action Store Tests**
   - `test_action_store_init`: Verifies proper initialization and logging
   - `test_save_action_chain`: Tests saving action sequences
   - `test_load_action_chain`: Validates loading saved actions
   - `test_load_nonexistent_chain`: Handles missing action chains
   - `test_list_chains`: Tests listing available action chains

2. **Basic Functionality Tests**
   - `test_browser_setup`: Validates browser initialization
   - `test_action_executor`: Tests basic action execution
   - `test_safety_manager`: Verifies safety confirmations
   - `test_claude_interface`: Tests Claude API integration
   - `test_complex_action_sequence`: Tests multi-step action sequences
   - `test_error_handling`: Validates error recovery
   - `test_state_management`: Tests GUI state capture and encoding

3. **Configuration Tests**
   - `test_config_loads_env_file`: Validates .env file loading
   - `test_config_uses_defaults_without_env_file`: Tests default values
   - `test_config_raises_error_without_api_key`: Validates API key requirement
   - `test_config_setup_logging`: Tests logging configuration

4. **Claude Interface Tests**
   - `test_get_next_actions_success`: Tests successful API responses
   - `test_get_next_actions_invalid_response`: Handles invalid responses
   - `test_get_next_actions_unexpected_content_type`: Tests error handling
   - `test_get_recovery_actions`: Validates recovery suggestions
   - `test_validate_action`: Tests action validation

### 4.3. Testing Guidelines

1. **Mock Usage**
   - Use `AsyncMock` for async functions and classes
   - Mock external services (Playwright, Claude API)
   - Properly mock loggers with debug/info/error methods

2. **Test Mode**
   - Set `is_test=True` for deterministic behavior
   - Disable human-like variations in test mode
   - Use fixed delays instead of random ones

3. **Environment Handling**
   - Create temporary .env files for testing
   - Mock environment variables appropriately
   - Test both with and without configuration files

4. **Assertions**
   - Verify exact character-by-character typing
   - Check proper logging calls and levels
   - Validate action sequences and timing
   - Assert proper error handling and recovery

---

## 5. Future Enhancements

1. **Advanced State Tracking**:
   - Visual state comparison
   - DOM change detection
   - Action verification

2. **Improved Safety**:
   - Action dry-run simulation
   - Automatic state rollback
   - Enhanced error recovery

3. **Anti-Detection**:
   - Browser fingerprint randomization
   - Proxy rotation
   - Session persistence

4. **User Experience**:
   - GUI for action confirmation
   - Progress visualization
   - Action history review

# Testing Methodology Guide

## Handling Async Mocks and Side Effects

### Understanding AsyncMock Side Effects
When using `AsyncMock` with side effects in tests, remember:
- Side effects specified as a list are consumed sequentially
- Each call to the mock returns the next item in the list
- Once the list is exhausted, subsequent calls raise `StopIteration`

Example:
```python
button.evaluate = AsyncMock(side_effect=[
    {"tagName": "BUTTON"},      # First call returns this
    {"id": "submit", "class": "primary"}  # Second call returns this
])
```

### Best Practices for Element Evaluation
When testing Playwright element evaluation:
1. Order your evaluate calls to match the side effect sequence
2. Keep track of how many times each mock will be called
3. Handle both direct returns and dictionary returns:
```python
tag_name = tag_info.get("tagName") if isinstance(tag_info, dict) else tag_info
```

## Test Mode Implementation

### Separating Test and Production Behavior
When implementing features that need different behavior in tests:

1. Use explicit flags to control behavior:
```python
self.is_test = False
self.simulate_typos = True
```

2. Check test mode early and provide direct paths:
```python
if self.is_test:
    await self.page.keyboard.type(text)
    return
```

3. Disable randomization and delays in test mode:
```python
if not self.is_test:
    await self._humanized_click(selector)
    # ... other human-like behaviors
```

### Testing Human-Like Interactions
For features that simulate human behavior:

1. Make randomization controllable:
- Use flags to disable random delays
- Provide deterministic paths for tests
- Keep human-like behavior only in production

2. Separate concerns:
- Core functionality should be testable without randomization
- Human-like behaviors should be optional layers

## Error Handling and Logging

### Structured Error Handling
Implement robust error handling in both test and production code:
```python
try:
    # Core functionality
except Exception as e:
    logger.warning(f"Error processing element: {str(e)}")
    continue
```

### Logging for Debugging
Use descriptive logging to track test execution:
```python
logger.debug(f"Typing '{text}' into {selector}")
logger.info(f"Captured {len(elements)} interactive elements")
```

## Test Organization

### Test Structure
Organize tests by functionality:
1. Basic functionality tests
2. Complex interaction tests
3. Error handling tests
4. State management tests

### Mock Setup
Keep mock setup clean and explicit:
```python
mock_page = AsyncMock()
mock_page.keyboard = AsyncMock()
mock_page.mouse = AsyncMock()
```

## Common Pitfalls and Solutions

### AsyncMock Side Effects
- **Problem**: Side effects not being consumed in the expected order
- **Solution**: Ensure evaluate calls match the sequence of side effects

### Randomization in Tests
- **Problem**: Non-deterministic behavior in tests
- **Solution**: Implement test mode to bypass randomization

### Element Type Determination
- **Problem**: Incorrect element type detection
- **Solution**: Handle both string and dictionary responses from evaluate calls

## Maintenance Tips

1. Keep test mode flags at the class level
2. Document expected mock behavior
3. Use clear logging for debugging
4. Separate human-like behavior from core functionality
5. Handle edge cases explicitly

## Playwright-Specific Testing Patterns

### Element Handling
1. **Selector Stability**:
```python
# Prefer role-based selectors
await page.get_by_role("button", name="Submit")  # More stable
# Instead of
await page.query_selector(".submit-btn")  # More fragile
```

2. **Wait Strategies**:
```python
# Explicit waiting in tests
await page.wait_for_selector("[name='q']", state="visible")
await page.wait_for_selector("[name='btnK']", state="attached")
```

3. **Element State Verification**:
```python
# Verify element states comprehensively
element = await page.query_selector("button")
assert await element.is_visible()
assert await element.is_enabled()
```

### Async Testing Best Practices

1. **Proper Test Isolation**:
```python
@pytest.mark.asyncio
async def test_async_function():
    # Setup
    async with AsyncPlaywright() as p:
        browser = await p.chromium.launch()
        # Test
        await browser.close()
```

2. **Mock Cleanup**:
```python
@pytest.fixture
async def mock_page():
    page = AsyncMock()
    yield page
    # Clean up any lingering mock side effects
    page.reset_mock()
```

3. **Handling Multiple Async Operations**:
```python
async def test_parallel_actions():
    async with asyncio.TaskGroup() as tg:
        task1 = tg.create_task(action1())
        task2 = tg.create_task(action2())
    # Both tasks complete here
```

### Test Data Management

1. **Fixture Organization**:
```python
@pytest.fixture
def test_actions():
    return [
        {
            "action_type": "type",
            "selector": "[name='q']",
            "value": "test query",
            "description": "Type search query"
        }
    ]
```

2. **Environment Isolation**:
```python
@pytest.fixture(autouse=True)
def test_env():
    # Setup test environment
    os.environ["TEST_MODE"] = "true"
    yield
    # Cleanup
    os.environ.pop("TEST_MODE")
```

### Performance Testing

1. **Timing Verification**:
```python
@pytest.mark.asyncio
async def test_action_timing():
    start_time = time.time()
    await executor.execute_action(action)
    duration = time.time() - start_time
    
    if executor.is_test:
        assert duration < 0.1  # Fast in test mode
    else:
        assert 0.5 <= duration <= 2.0  # Normal range
```

2. **Resource Monitoring**:
```python
def test_memory_usage():
    import psutil
    process = psutil.Process()
    
    initial_memory = process.memory_info().rss
    # Execute test
    final_memory = process.memory_info().rss
    
    # Check for memory leaks
    assert (final_memory - initial_memory) < 10 * 1024 * 1024  # 10MB limit
```

### Integration Testing

1. **Component Integration**:
```python
@pytest.mark.asyncio
async def test_full_workflow():
    # Test entire workflow
    gui_state = await capture_gui_state(page)
    actions = await claude.get_next_actions(goal, gui_state)
    assert await safety.confirm_actions(actions)
    
    for action in actions:
        await executor.execute_action(action)
        # Verify state after each action
        new_state = await capture_gui_state(page)
        assert verify_state_change(gui_state, new_state, action)
```

2. **Error Propagation**:
```python
@pytest.mark.asyncio
async def test_error_handling():
    with pytest.raises(PlaywrightError) as exc_info:
        await executor.execute_action(invalid_action)
    
    assert "Element not found" in str(exc_info.value)
    # Verify error is properly logged
    assert "Error executing action" in caplog.text
```

### Security Testing

1. **Input Validation**:
```python
@pytest.mark.asyncio
async def test_input_sanitization():
    malicious_input = "<script>alert('xss')</script>"
    action = {
        "action_type": "type",
        "value": malicious_input
    }
    
    # Verify input is properly sanitized
    await executor.execute_action(action)
    element_content = await page.evaluate("el => el.textContent")
    assert "<script>" not in element_content
```

2. **Permission Handling**:
```python
@pytest.mark.asyncio
async def test_permission_checks():
    # Test restricted actions
    with pytest.raises(PermissionError):
        await executor.execute_action(restricted_action)
```

### Documentation Testing

1. **Example Validation**:
```python
def test_readme_examples():
    """Ensure README examples are valid and up-to-date"""
    import doctest
    doctest.testfile("README.md")
```

2. **API Documentation**:
```python
def test_api_documentation():
    """Verify all public methods are documented"""
    import inspect
    
    for name, method in inspect.getmembers(ActionExecutor):
        if not name.startswith('_'):  # Public method
            assert method.__doc__, f"{name} missing documentation"
```

These patterns ensure:
- Reliable async testing
- Proper test isolation
- Comprehensive coverage
- Performance monitoring
- Security validation
- Documentation accuracy


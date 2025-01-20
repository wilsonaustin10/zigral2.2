from typing import Dict, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
import json
import logging
from functools import lru_cache

@dataclass
class GUIState:
    """Represents a snapshot of GUI state"""
    url: str
    title: str
    viewport: Dict
    elements: List[Dict]
    timestamp: datetime = field(default_factory=datetime.now)

class StateManager:
    def __init__(self):
        self.state_history = []
        
    @lru_cache(maxsize=100)
    async def capture_state(self, page) -> Optional[GUIState]:
        """Capture current GUI state with caching"""
        try:
            if not page:
                return None
                
            # Get basic page info
            url = page.url
            title = await page.title()
            viewport = await page.viewport_size
            
            # Get visible elements
            elements = await page.evaluate("""() => {
                return Array.from(document.querySelectorAll('*'))
                    .filter(el => {
                        const rect = el.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0;
                    })
                    .map(el => ({
                        tag: el.tagName,
                        id: el.id,
                        text: el.innerText,
                        isVisible: true,
                        selector: el.id ? '#' + el.id : el.className
                    }));
            }""")
            
            state = GUIState(
                url=url,
                title=title,
                viewport=viewport,
                elements=elements
            )
            
            self.state_history.append(state)
            return state
            
        except Exception as e:
            logging.error(f"State capture failed: {str(e)}")
            return None
            
    def get_state_diff(self, before: GUIState, after: GUIState) -> Dict:
        """Compare two states and return differences"""
        try:
            diffs = {
                "url_changed": before.url != after.url,
                "title_changed": before.title != after.title,
                "viewport_changed": before.viewport != after.viewport,
                "elements_added": [],
                "elements_removed": []
            }
            
            # Compare elements
            before_elements = {el["selector"]: el for el in before.elements}
            after_elements = {el["selector"]: el for el in after.elements}
            
            diffs["elements_added"] = [
                el for sel, el in after_elements.items() 
                if sel not in before_elements
            ]
            
            diffs["elements_removed"] = [
                el for sel, el in before_elements.items()
                if sel not in after_elements
            ]
            
            return diffs
            
        except Exception as e:
            logging.error(f"State diff failed: {str(e)}")
            return {} 
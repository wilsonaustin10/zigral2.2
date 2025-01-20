from typing import List, Dict, Optional
from dataclasses import dataclass
import logging
from playwright.async_api import Page, ElementHandle
from config.settings import config

logger = logging.getLogger(__name__)

@dataclass
class GUIElement:
    """Representation of a GUI element"""
    element_type: str
    selector: str
    text: Optional[str]
    location: Dict[str, int]
    attributes: Dict[str, str]
    is_visible: bool
    is_enabled: bool
    children: List['GUIElement']

class GUIObserver:
    """Observes and captures GUI state"""
    
    def __init__(self):
        self.supported_elements = config.vision.supported_element_types
        
    async def capture_state(self, page: Page) -> Dict:
        """
        Capture the current state of the GUI.
        
        Args:
            page: Playwright page object
            
        Returns:
            Dict containing the GUI state
        """
        try:
            logger.debug("Starting GUI state capture")
            
            # Get viewport size
            viewport = await page.viewport_size()
            
            # Capture visible elements
            elements = await self._capture_elements(page)
            
            # Get page metadata
            url = page.url
            title = await page.title()
            
            state = {
                "url": url,
                "title": title,
                "viewport": viewport,
                "elements": elements,
                "timestamp": self._get_timestamp()
            }
            
            logger.debug(f"Captured GUI state with {len(elements)} elements")
            return state
            
        except Exception as e:
            logger.error(f"Error capturing GUI state: {str(e)}")
            raise
            
    async def _capture_elements(self, page: Page) -> List[Dict]:
        """Capture all relevant UI elements"""
        elements = []
        
        for element_type in self.supported_elements:
            # Use appropriate selector based on element type
            selector = self._get_selector(element_type)
            handles = await page.query_selector_all(selector)
            
            for handle in handles:
                element = await self._process_element(handle, element_type)
                if element:
                    elements.append(element)
                    
        return elements
        
    async def _process_element(self, 
                             handle: ElementHandle, 
                             element_type: str) -> Optional[Dict]:
        """Process a single element"""
        try:
            # Check visibility
            is_visible = await handle.is_visible()
            if not is_visible and not config.vision.capture_hidden:
                return None
                
            # Get basic properties
            box = await handle.bounding_box()
            if not box:
                return None
                
            # Get element properties
            props = await self._get_element_properties(handle)
            
            # Create element representation
            element = GUIElement(
                element_type=element_type,
                selector=await self._generate_selector(handle),
                text=await handle.text_content(),
                location={
                    "x": box["x"],
                    "y": box["y"],
                    "width": box["width"],
                    "height": box["height"]
                },
                attributes=props,
                is_visible=is_visible,
                is_enabled=await handle.is_enabled(),
                children=[]
            )
            
            # Capture child elements if needed
            if config.vision.capture_children:
                children = await handle.query_selector_all("*")
                for child in children:
                    child_element = await self._process_element(
                        child, 
                        await self._determine_element_type(child)
                    )
                    if child_element:
                        element.children.append(child_element)
            
            return element.__dict__
            
        except Exception as e:
            logger.warning(f"Error processing element: {str(e)}")
            return None
            
    async def _get_element_properties(self, handle: ElementHandle) -> Dict[str, str]:
        """Get element properties and attributes"""
        props = {}
        
        # Get standard properties
        for prop in ["id", "class", "name", "type", "value", "href", "src"]:
            try:
                value = await handle.get_attribute(prop)
                if value:
                    props[prop] = value
            except:
                continue
                
        # Get ARIA properties
        for prop in ["role", "label", "description"]:
            try:
                value = await handle.get_attribute(f"aria-{prop}")
                if value:
                    props[f"aria-{prop}"] = value
            except:
                continue
                
        return props
        
    async def _generate_selector(self, handle: ElementHandle) -> str:
        """Generate a unique selector for the element"""
        # Try ID first
        element_id = await handle.get_attribute("id")
        if element_id:
            return f"#{element_id}"
            
        # Try unique attributes
        for attr in ["name", "data-testid", "aria-label"]:
            value = await handle.get_attribute(attr)
            if value:
                return f"[{attr}='{value}']"
                
        # Fallback to XPath
        xpath_script = """
            function getXPath(element) {
                if (element.id)
                    return `//*[@id="${element.id}"]`;
                if (element === document.body)
                    return '/html/body';
                    
                let ix = 0;
                let siblings = element.parentNode.childNodes;
                
                for (let sibling of siblings) {
                    if (sibling === element)
                        return getXPath(element.parentNode) + '/' + element.tagName.toLowerCase() + '[' + (ix + 1) + ']';
                    if (sibling.nodeType === 1 && sibling.tagName === element.tagName)
                        ix++;
                }
            }
            return getXPath(this);
        """
        return await handle.evaluate(xpath_script)
        
    def _get_selector(self, element_type: str) -> str:
        """Get appropriate selector for element type"""
        selectors = {
            "button": "button, [role='button'], input[type='button']",
            "input": "input:not([type='button']), textarea",
            "link": "a, [role='link']",
            "text": "p, span, div:not(:has(*))",
            "image": "img, [role='img']",
            "checkbox": "input[type='checkbox'], [role='checkbox']",
            "radio": "input[type='radio'], [role='radio']",
            "dropdown": "select, [role='listbox']",
            "slider": "input[type='range'], [role='slider']"
        }
        return selectors.get(element_type, "*")
        
    async def _determine_element_type(self, handle: ElementHandle) -> str:
        """Determine element type from its properties"""
        tag_name = await handle.evaluate("el => el.tagName.toLowerCase()")
        role = await handle.get_attribute("role")
        input_type = await handle.get_attribute("type")
        
        if role in self.supported_elements:
            return role
        if tag_name in self.supported_elements:
            return tag_name
        if tag_name == "input" and input_type:
            return input_type
            
        return "unknown"
        
    def _get_timestamp(self) -> int:
        """Get current timestamp in milliseconds"""
        import time
        return int(time.time() * 1000) 
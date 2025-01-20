from typing import Dict, List, Optional
import logging
import asyncio
from config.settings import config

logger = logging.getLogger(__name__)

class ActionValidator:
    """Validates actions before execution"""
    
    def __init__(self):
        self.required_fields = {
            "click": ["selector"],
            "type": ["selector", "value"],
            "press": ["value"],
            "wait": ["value"]
        }
        
        self.value_validators = {
            "selector": self._validate_selector,
            "value": self._validate_value
        }
        
    async def validate_actions(self, actions: List[Dict]) -> bool:
        """
        Validate a sequence of actions.
        
        Args:
            actions: List of action dictionaries
            
        Returns:
            bool: True if all actions are valid
        """
        try:
            for action in actions:
                if not await self.validate_action(action):
                    return False
            return True
            
        except Exception as e:
            logger.error(f"Action validation failed: {str(e)}")
            return False
            
    async def validate_action(self, action: Dict) -> bool:
        """Validate a single action"""
        try:
            # Check action type
            action_type = action.get("action_type")
            if not action_type or action_type not in self.required_fields:
                logger.error(f"Invalid action type: {action_type}")
                return False
                
            # Check required fields
            for field in self.required_fields[action_type]:
                if field not in action:
                    logger.error(f"Missing required field: {field}")
                    return False
                    
                # Validate field value
                if field in self.value_validators:
                    if not await self.value_validators[field](action[field]):
                        return False
                        
            # Action-specific validation
            if action_type == "click":
                return await self._validate_click_action(action)
            elif action_type == "type":
                return await self._validate_type_action(action)
            elif action_type == "press":
                return await self._validate_press_action(action)
            elif action_type == "wait":
                return await self._validate_wait_action(action)
                
            return True
            
        except Exception as e:
            logger.error(f"Action validation failed: {str(e)}")
            return False
            
    async def confirm_action(self, action: Dict) -> bool:
        """Get user confirmation for action"""
        if not config.safety.require_confirmation:
            return True
            
        try:
            description = self._get_action_description(action)
            print(f"\nProposed action: {description}")
            response = input("Execute this action? (y/n): ").lower()
            
            if response == 'y':
                return True
                
            logger.info("Action rejected by user")
            return False
            
        except Exception as e:
            logger.error(f"Action confirmation failed: {str(e)}")
            return False
            
    async def _validate_selector(self, selector: str) -> bool:
        """Validate a selector string"""
        if not selector or not isinstance(selector, str):
            logger.error("Invalid selector")
            return False
            
        # Basic selector validation
        invalid_chars = ['<', '>', '"', "'"]
        if any(char in selector for char in invalid_chars):
            logger.error("Selector contains invalid characters")
            return False
            
        # Length check
        if len(selector) > 1000:
            logger.error("Selector too long")
            return False
            
        return True
        
    async def _validate_value(self, value: str) -> bool:
        """Validate an input value"""
        if not isinstance(value, str):
            logger.error("Value must be a string")
            return False
            
        # Length check
        if len(value) > 10000:
            logger.error("Value too long")
            return False
            
        return True
        
    async def _validate_click_action(self, action: Dict) -> bool:
        """Validate click action"""
        # Additional click-specific validation
        return True
        
    async def _validate_type_action(self, action: Dict) -> bool:
        """Validate type action"""
        value = action["value"]
        
        # Check for dangerous input
        dangerous_patterns = [
            "<script>",
            "javascript:",
            "data:text/html",
            "document.cookie"
        ]
        
        if any(pattern in value.lower() for pattern in dangerous_patterns):
            logger.error("Potentially dangerous input detected")
            return False
            
        return True
        
    async def _validate_press_action(self, action: Dict) -> bool:
        """Validate keypress action"""
        valid_keys = [
            'Enter', 'Tab', 'Escape', 'ArrowUp', 'ArrowDown',
            'ArrowLeft', 'ArrowRight', 'Backspace', 'Delete',
            'Home', 'End', 'PageUp', 'PageDown'
        ]
        
        value = action["value"]
        if len(value) == 1:
            return True  # Single character key
            
        if value not in valid_keys:
            logger.error(f"Invalid key: {value}")
            return False
            
        return True
        
    async def _validate_wait_action(self, action: Dict) -> bool:
        """Validate wait action"""
        try:
            duration = int(action["value"])
            if duration < 0 or duration > 60000:  # Max 1 minute
                logger.error("Invalid wait duration")
                return False
            return True
        except ValueError:
            logger.error("Wait duration must be an integer")
            return False
            
    def _get_action_description(self, action: Dict) -> str:
        """Get human-readable action description"""
        action_type = action["action_type"]
        
        if action_type == "click":
            return f"Click element: {action['selector']}"
        elif action_type == "type":
            return f"Type '{action['value']}' into: {action['selector']}"
        elif action_type == "press":
            return f"Press key: {action['value']}"
        elif action_type == "wait":
            return f"Wait for {action['value']}ms"
        
        return str(action) 
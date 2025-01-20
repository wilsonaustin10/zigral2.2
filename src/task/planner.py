from typing import List, Optional, Dict
from src.actions.action_cache import Action, ActionSequence
from src.llm.claude_client import ClaudeClient
import logging

class TaskPlanner:
    def __init__(self, claude_client: ClaudeClient, action_cache):
        self.claude = claude_client
        self.cache = action_cache
        
    async def plan_actions(self, task: str, gui_state: Dict) -> Optional[List[Action]]:
        """Plan next actions for a task given current GUI state"""
        try:
            # First check cache for similar tasks
            cached_sequence = await self.cache.get_similar_task(task)
            if cached_sequence and cached_sequence.success_rate > 0.8:
                return cached_sequence.actions
                
            # Get actions from Claude
            actions = await self.claude.plan_actions(
                task,
                gui_state,
                action_history=None
            )
            return actions
            
        except Exception as e:
            logging.error(f"Action planning failed: {str(e)}")
            return None
            
    async def verify_completion(self, task: str, gui_state: Dict) -> bool:
        """Verify if task is complete given current state"""
        try:
            verification = await self.claude.plan_actions(
                f"Verify if this task is complete: {task}\n"
                f"Current GUI state:\n{gui_state}",
                gui_state,
                action_history=None
            )
            return not verification
        except Exception as e:
            logging.error(f"Completion verification failed: {str(e)}")
            return False 
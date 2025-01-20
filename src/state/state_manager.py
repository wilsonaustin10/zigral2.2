import logging
import json
import time
from typing import Dict, Optional, List
from dataclasses import dataclass
from datetime import datetime
from config.settings import config

logger = logging.getLogger(__name__)

@dataclass
class Checkpoint:
    """Represents a state checkpoint"""
    id: str
    timestamp: str
    gui_state: Dict
    task_state: Dict
    browser_state: Dict
    metadata: Dict

class StateManager:
    """Manages application state and checkpoints"""
    
    def __init__(self):
        self.current_state = {
            "gui": {},
            "task": {},
            "browser": {},
            "metadata": {}
        }
        self.checkpoints = []
        self.max_checkpoints = config.state.max_checkpoints
        self.auto_checkpoint_interval = config.state.auto_checkpoint_interval
        self.last_auto_checkpoint = time.time()
        
    def update_gui_state(self, gui_state: Dict):
        """Update GUI state"""
        self.current_state["gui"] = gui_state
        self._check_auto_checkpoint()
        
    def update_task_state(self, task_state: Dict):
        """Update task state"""
        self.current_state["task"] = task_state
        self._check_auto_checkpoint()
        
    def update_browser_state(self, browser_state: Dict):
        """Update browser state"""
        self.current_state["browser"] = browser_state
        self._check_auto_checkpoint()
        
    def update_metadata(self, metadata: Dict):
        """Update metadata"""
        self.current_state["metadata"].update(metadata)
        
    def create_checkpoint(self, checkpoint_id: Optional[str] = None) -> str:
        """Create a state checkpoint"""
        try:
            checkpoint = Checkpoint(
                id=checkpoint_id or f"checkpoint_{int(time.time())}",
                timestamp=datetime.now().isoformat(),
                gui_state=self.current_state["gui"].copy(),
                task_state=self.current_state["task"].copy(),
                browser_state=self.current_state["browser"].copy(),
                metadata=self.current_state["metadata"].copy()
            )
            
            self.checkpoints.append(checkpoint)
            
            # Maintain maximum checkpoints
            while len(self.checkpoints) > self.max_checkpoints:
                self.checkpoints.pop(0)
                
            logger.debug(f"Created checkpoint: {checkpoint.id}")
            return checkpoint.id
            
        except Exception as e:
            logger.error(f"Failed to create checkpoint: {str(e)}")
            raise
            
    def restore_checkpoint(self, checkpoint_id: str) -> bool:
        """Restore state from a checkpoint"""
        try:
            checkpoint = self._find_checkpoint(checkpoint_id)
            if not checkpoint:
                logger.warning(f"Checkpoint not found: {checkpoint_id}")
                return False
                
            self.current_state = {
                "gui": checkpoint.gui_state.copy(),
                "task": checkpoint.task_state.copy(),
                "browser": checkpoint.browser_state.copy(),
                "metadata": checkpoint.metadata.copy()
            }
            
            logger.debug(f"Restored checkpoint: {checkpoint_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to restore checkpoint: {str(e)}")
            return False
            
    def get_checkpoint(self, checkpoint_id: str) -> Optional[Dict]:
        """Get checkpoint data"""
        checkpoint = self._find_checkpoint(checkpoint_id)
        if not checkpoint:
            return None
            
        return {
            "id": checkpoint.id,
            "timestamp": checkpoint.timestamp,
            "gui_state": checkpoint.gui_state,
            "task_state": checkpoint.task_state,
            "browser_state": checkpoint.browser_state,
            "metadata": checkpoint.metadata
        }
        
    def list_checkpoints(self) -> List[Dict]:
        """List all checkpoints"""
        return [
            {
                "id": cp.id,
                "timestamp": cp.timestamp,
                "metadata": cp.metadata
            }
            for cp in self.checkpoints
        ]
        
    def delete_checkpoint(self, checkpoint_id: str) -> bool:
        """Delete a checkpoint"""
        try:
            checkpoint = self._find_checkpoint(checkpoint_id)
            if not checkpoint:
                return False
                
            self.checkpoints.remove(checkpoint)
            logger.debug(f"Deleted checkpoint: {checkpoint_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete checkpoint: {str(e)}")
            return False
            
    def clear_checkpoints(self):
        """Clear all checkpoints"""
        self.checkpoints = []
        logger.debug("Cleared all checkpoints")
        
    def get_current_state(self) -> Dict:
        """Get current state"""
        return self.current_state.copy()
        
    def _find_checkpoint(self, checkpoint_id: str) -> Optional[Checkpoint]:
        """Find checkpoint by ID"""
        for checkpoint in self.checkpoints:
            if checkpoint.id == checkpoint_id:
                return checkpoint
        return None
        
    def _check_auto_checkpoint(self):
        """Check if auto-checkpoint should be created"""
        if not config.state.auto_checkpoint_enabled:
            return
            
        now = time.time()
        if now - self.last_auto_checkpoint >= self.auto_checkpoint_interval:
            self.create_checkpoint(f"auto_{int(now)}")
            self.last_auto_checkpoint = now
            
    def export_state(self, filepath: str):
        """Export current state to file"""
        try:
            state_data = {
                "current_state": self.current_state,
                "checkpoints": [
                    {
                        "id": cp.id,
                        "timestamp": cp.timestamp,
                        "gui_state": cp.gui_state,
                        "task_state": cp.task_state,
                        "browser_state": cp.browser_state,
                        "metadata": cp.metadata
                    }
                    for cp in self.checkpoints
                ]
            }
            
            with open(filepath, 'w') as f:
                json.dump(state_data, f, indent=2)
                
            logger.debug(f"Exported state to: {filepath}")
            
        except Exception as e:
            logger.error(f"Failed to export state: {str(e)}")
            raise
            
    def import_state(self, filepath: str):
        """Import state from file"""
        try:
            with open(filepath, 'r') as f:
                state_data = json.load(f)
                
            self.current_state = state_data["current_state"]
            self.checkpoints = [
                Checkpoint(**cp_data)
                for cp_data in state_data["checkpoints"]
            ]
            
            logger.debug(f"Imported state from: {filepath}")
            
        except Exception as e:
            logger.error(f"Failed to import state: {str(e)}")
            raise 
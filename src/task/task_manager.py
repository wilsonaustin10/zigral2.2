import logging
import asyncio
import uuid
from typing import Dict, List, Optional, Callable, Awaitable
from datetime import datetime
from dataclasses import dataclass
from enum import Enum
from config.settings import config

logger = logging.getLogger(__name__)

class TaskStatus(Enum):
    """Task status enum"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"

@dataclass
class Task:
    """Represents a task"""
    id: str
    description: str
    status: TaskStatus
    created_at: str
    started_at: Optional[str]
    completed_at: Optional[str]
    error: Optional[str]
    metadata: Dict
    subtasks: List['Task']
    parent_id: Optional[str]
    priority: int
    max_retries: int
    retry_count: int
    timeout: Optional[float]

class TaskManager:
    """Manages tasks and workflows"""
    
    def __init__(self):
        self.tasks = {}
        self.running_tasks = set()
        self.task_queue = asyncio.PriorityQueue()
        self.task_handlers = {}
        self.max_concurrent_tasks = config.task.max_concurrent_tasks
        self.task_timeout = config.task.default_timeout
        
    def register_handler(self, task_type: str, handler: Callable[[Task], Awaitable[None]]):
        """Register a task handler"""
        self.task_handlers[task_type] = handler
        logger.debug(f"Registered handler for task type: {task_type}")
        
    async def create_task(self,
                         description: str,
                         task_type: str,
                         metadata: Optional[Dict] = None,
                         parent_id: Optional[str] = None,
                         priority: int = 0,
                         max_retries: int = 3,
                         timeout: Optional[float] = None) -> str:
        """Create a new task"""
        try:
            task_id = str(uuid.uuid4())
            task = Task(
                id=task_id,
                description=description,
                status=TaskStatus.PENDING,
                created_at=datetime.now().isoformat(),
                started_at=None,
                completed_at=None,
                error=None,
                metadata=metadata or {},
                subtasks=[],
                parent_id=parent_id,
                priority=priority,
                max_retries=max_retries,
                retry_count=0,
                timeout=timeout or self.task_timeout
            )
            
            # Add task type to metadata
            task.metadata["type"] = task_type
            
            # Store task
            self.tasks[task_id] = task
            
            # Add to queue if no parent
            if not parent_id:
                await self.task_queue.put((priority, task_id))
                
            logger.debug(f"Created task: {task_id}")
            return task_id
            
        except Exception as e:
            logger.error(f"Failed to create task: {str(e)}")
            raise
            
    async def start_task(self, task_id: str):
        """Start a task"""
        try:
            task = self.tasks.get(task_id)
            if not task:
                logger.warning(f"Task not found: {task_id}")
                return
                
            if task.status != TaskStatus.PENDING:
                logger.warning(f"Task {task_id} is not pending")
                return
                
            # Check if we can run more tasks
            if len(self.running_tasks) >= self.max_concurrent_tasks:
                logger.warning("Maximum concurrent tasks reached")
                return
                
            # Update task status
            task.status = TaskStatus.RUNNING
            task.started_at = datetime.now().isoformat()
            self.running_tasks.add(task_id)
            
            # Get task handler
            task_type = task.metadata.get("type")
            handler = self.task_handlers.get(task_type)
            
            if not handler:
                raise ValueError(f"No handler for task type: {task_type}")
                
            # Run task with timeout
            try:
                if task.timeout:
                    await asyncio.wait_for(handler(task), timeout=task.timeout)
                else:
                    await handler(task)
                    
                # Mark as completed
                task.status = TaskStatus.COMPLETED
                task.completed_at = datetime.now().isoformat()
                
                # Start subtasks
                for subtask in task.subtasks:
                    await self.task_queue.put((subtask.priority, subtask.id))
                    
            except asyncio.TimeoutError:
                task.error = "Task timed out"
                await self._handle_task_failure(task)
                
            except Exception as e:
                task.error = str(e)
                await self._handle_task_failure(task)
                
            finally:
                self.running_tasks.remove(task_id)
                
        except Exception as e:
            logger.error(f"Failed to start task: {str(e)}")
            
    async def _handle_task_failure(self, task: Task):
        """Handle task failure"""
        if task.retry_count < task.max_retries:
            # Retry task
            task.retry_count += 1
            task.status = TaskStatus.PENDING
            task.error = None
            await self.task_queue.put((task.priority, task.id))
            logger.debug(f"Retrying task {task.id} (attempt {task.retry_count})")
        else:
            # Mark as failed
            task.status = TaskStatus.FAILED
            logger.error(f"Task {task.id} failed after {task.retry_count} retries")
            
    async def cancel_task(self, task_id: str):
        """Cancel a task"""
        try:
            task = self.tasks.get(task_id)
            if not task:
                return
                
            task.status = TaskStatus.CANCELLED
            
            # Cancel subtasks
            for subtask in task.subtasks:
                await self.cancel_task(subtask.id)
                
            logger.debug(f"Cancelled task: {task_id}")
            
        except Exception as e:
            logger.error(f"Failed to cancel task: {str(e)}")
            
    async def pause_task(self, task_id: str):
        """Pause a task"""
        try:
            task = self.tasks.get(task_id)
            if not task:
                return
                
            if task.status == TaskStatus.RUNNING:
                task.status = TaskStatus.PAUSED
                self.running_tasks.remove(task_id)
                
            logger.debug(f"Paused task: {task_id}")
            
        except Exception as e:
            logger.error(f"Failed to pause task: {str(e)}")
            
    async def resume_task(self, task_id: str):
        """Resume a paused task"""
        try:
            task = self.tasks.get(task_id)
            if not task or task.status != TaskStatus.PAUSED:
                return
                
            task.status = TaskStatus.PENDING
            await self.task_queue.put((task.priority, task_id))
            
            logger.debug(f"Resumed task: {task_id}")
            
        except Exception as e:
            logger.error(f"Failed to resume task: {str(e)}")
            
    def get_task(self, task_id: str) -> Optional[Task]:
        """Get task by ID"""
        return self.tasks.get(task_id)
        
    def list_tasks(self, status: Optional[TaskStatus] = None) -> List[Task]:
        """List tasks, optionally filtered by status"""
        if status:
            return [task for task in self.tasks.values() if task.status == status]
        return list(self.tasks.values())
        
    async def process_queue(self):
        """Process task queue"""
        while True:
            try:
                # Get next task
                priority, task_id = await self.task_queue.get()
                
                # Start task
                await self.start_task(task_id)
                
                # Mark task as done
                self.task_queue.task_done()
                
            except Exception as e:
                logger.error(f"Error processing task queue: {str(e)}")
                await asyncio.sleep(1)  # Prevent tight loop on error
                
    def clear_completed_tasks(self):
        """Clear completed and failed tasks"""
        completed_ids = [
            task_id for task_id, task in self.tasks.items()
            if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED]
        ]
        
        for task_id in completed_ids:
            del self.tasks[task_id]
            
        logger.debug(f"Cleared {len(completed_ids)} completed tasks")
        
    async def add_subtask(self,
                         parent_id: str,
                         description: str,
                         task_type: str,
                         metadata: Optional[Dict] = None,
                         priority: int = 0) -> Optional[str]:
        """Add a subtask to a parent task"""
        try:
            parent_task = self.tasks.get(parent_id)
            if not parent_task:
                logger.warning(f"Parent task not found: {parent_id}")
                return None
                
            subtask_id = await self.create_task(
                description=description,
                task_type=task_type,
                metadata=metadata,
                parent_id=parent_id,
                priority=priority
            )
            
            subtask = self.tasks[subtask_id]
            parent_task.subtasks.append(subtask)
            
            return subtask_id
            
        except Exception as e:
            logger.error(f"Failed to add subtask: {str(e)}")
            return None
            
    def get_task_tree(self, task_id: str) -> Dict:
        """Get task and its subtasks as a tree"""
        task = self.tasks.get(task_id)
        if not task:
            return {}
            
        return {
            "id": task.id,
            "description": task.description,
            "status": task.status.value,
            "created_at": task.created_at,
            "started_at": task.started_at,
            "completed_at": task.completed_at,
            "error": task.error,
            "metadata": task.metadata,
            "subtasks": [
                self.get_task_tree(subtask.id)
                for subtask in task.subtasks
            ]
        } 
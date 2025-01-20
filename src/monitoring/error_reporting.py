import logging
import traceback
import json
import time
import psutil
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from config.settings import config

logger = logging.getLogger(__name__)

@dataclass
class ErrorContext:
    """Context information for errors"""
    timestamp: str
    error_type: str
    message: str
    severity: str
    stack_trace: Optional[str]
    component: str
    task_id: Optional[str]
    gui_state: Optional[Dict]
    additional_data: Optional[Dict]

@dataclass
class PerformanceMetrics:
    """Performance metrics for operations"""
    operation_name: str
    start_time: float
    end_time: Optional[float]
    duration: Optional[float]
    cpu_percent: float
    memory_usage: int
    steps: List[Dict]
    status: str

class ErrorReporter:
    """Handles error reporting and tracking"""
    
    def __init__(self, log_file: str = "errors.log"):
        # Configure error logger
        self.logger = logging.getLogger("error_reporter")
        handler = logging.FileHandler(log_file)
        handler.setFormatter(
            logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        )
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.DEBUG)
        
        # Initialize error stats
        self.error_counts = {}
        self.last_errors = []
        self.max_stored_errors = 100
        
    def report_error(self,
                    error: Exception,
                    component: str,
                    severity: str = "ERROR",
                    task_id: Optional[str] = None,
                    gui_state: Optional[Dict] = None,
                    additional_data: Optional[Dict] = None):
        """Report an error with context"""
        try:
            # Create error context
            context = ErrorContext(
                timestamp=datetime.now().isoformat(),
                error_type=type(error).__name__,
                message=str(error),
                severity=severity,
                stack_trace=traceback.format_exc() if severity == "ERROR" else None,
                component=component,
                task_id=task_id,
                gui_state=gui_state,
                additional_data=additional_data
            )
            
            # Log error
            self._log_error(context)
            
            # Update statistics
            self._update_stats(context)
            
            # Store error
            self._store_error(context)
            
            # Check for error patterns
            self._check_patterns()
            
        except Exception as e:
            logger.error(f"Error reporting failed: {str(e)}")
            
    def get_error_stats(self) -> Dict:
        """Get error statistics"""
        return {
            "error_counts": self.error_counts,
            "recent_errors": [asdict(e) for e in self.last_errors[-10:]]
        }
        
    def _log_error(self, context: ErrorContext):
        """Log error with appropriate severity"""
        error_data = asdict(context)
        
        if context.severity == "ERROR":
            self.logger.error(json.dumps(error_data))
        elif context.severity == "WARNING":
            self.logger.warning(json.dumps(error_data))
        else:
            self.logger.info(json.dumps(error_data))
            
    def _update_stats(self, context: ErrorContext):
        """Update error statistics"""
        error_type = context.error_type
        
        if error_type not in self.error_counts:
            self.error_counts[error_type] = {
                "count": 0,
                "first_seen": context.timestamp,
                "last_seen": context.timestamp
            }
            
        self.error_counts[error_type]["count"] += 1
        self.error_counts[error_type]["last_seen"] = context.timestamp
        
    def _store_error(self, context: ErrorContext):
        """Store error for pattern analysis"""
        self.last_errors.append(context)
        
        # Maintain maximum size
        if len(self.last_errors) > self.max_stored_errors:
            self.last_errors.pop(0)
            
    def _check_patterns(self):
        """Check for error patterns and trends"""
        if len(self.last_errors) < 5:
            return
            
        # Check for repeated errors
        last_five = self.last_errors[-5:]
        if all(e.error_type == last_five[0].error_type for e in last_five):
            logger.warning(f"Detected repeated errors of type: {last_five[0].error_type}")
            
        # Check for rapid error rate
        if len(self.last_errors) >= 10:
            last_ten = self.last_errors[-10:]
            time_span = (
                datetime.fromisoformat(last_ten[-1].timestamp) -
                datetime.fromisoformat(last_ten[0].timestamp)
            ).total_seconds()
            
            if time_span < 60:  # 10 errors in less than a minute
                logger.warning("Detected high error rate")

class PerformanceMonitor:
    """Monitors and tracks performance metrics"""
    
    def __init__(self):
        self.logger = logging.getLogger("performance")
        self.active_operations = {}
        self.completed_operations = []
        self.process = psutil.Process()
        
    def start_operation(self, 
                       operation_name: str,
                       task_id: Optional[str] = None) -> str:
        """Start timing an operation"""
        try:
            metrics = PerformanceMetrics(
                operation_name=operation_name,
                start_time=time.time(),
                end_time=None,
                duration=None,
                cpu_percent=self.process.cpu_percent(),
                memory_usage=self.process.memory_info().rss,
                steps=[],
                status="running"
            )
            
            self.active_operations[operation_name] = metrics
            
            logger.debug(f"Started monitoring operation: {operation_name}")
            return operation_name
            
        except Exception as e:
            logger.error(f"Failed to start performance monitoring: {str(e)}")
            return ""
            
    def end_operation(self, operation_name: str, status: str = "completed"):
        """End timing an operation"""
        try:
            if operation_name not in self.active_operations:
                logger.warning(f"Operation not found: {operation_name}")
                return
                
            metrics = self.active_operations[operation_name]
            metrics.end_time = time.time()
            metrics.duration = metrics.end_time - metrics.start_time
            metrics.status = status
            
            # Update final resource usage
            metrics.cpu_percent = self.process.cpu_percent()
            metrics.memory_usage = self.process.memory_info().rss
            
            # Log metrics
            self._log_metrics(metrics)
            
            # Store completed operation
            self.completed_operations.append(metrics)
            del self.active_operations[operation_name]
            
            logger.debug(f"Completed monitoring operation: {operation_name}")
            
        except Exception as e:
            logger.error(f"Failed to end performance monitoring: {str(e)}")
            
    def log_step(self, operation_name: str, step_name: str):
        """Log a step within an operation"""
        try:
            if operation_name not in self.active_operations:
                logger.warning(f"Operation not found: {operation_name}")
                return
                
            metrics = self.active_operations[operation_name]
            metrics.steps.append({
                "name": step_name,
                "timestamp": time.time(),
                "cpu_percent": self.process.cpu_percent(),
                "memory_usage": self.process.memory_info().rss
            })
            
        except Exception as e:
            logger.error(f"Failed to log step: {str(e)}")
            
    def get_metrics(self, operation_name: Optional[str] = None) -> Dict:
        """Get performance metrics"""
        try:
            if operation_name:
                if operation_name in self.active_operations:
                    return asdict(self.active_operations[operation_name])
                    
                # Search completed operations
                for op in reversed(self.completed_operations):
                    if op.operation_name == operation_name:
                        return asdict(op)
                        
                return {}
                
            # Return all metrics
            return {
                "active": {
                    name: asdict(metrics)
                    for name, metrics in self.active_operations.items()
                },
                "completed": [
                    asdict(metrics)
                    for metrics in self.completed_operations[-10:]  # Last 10
                ]
            }
            
        except Exception as e:
            logger.error(f"Failed to get metrics: {str(e)}")
            return {}
            
    def _log_metrics(self, metrics: PerformanceMetrics):
        """Log performance metrics"""
        try:
            metric_data = asdict(metrics)
            
            # Check thresholds
            if metrics.duration and metrics.duration > config.performance.max_operation_time:
                logger.warning(f"Operation took too long: {metrics.operation_name}")
                
            if metrics.memory_usage > config.performance.max_memory_usage:
                logger.warning(f"High memory usage in operation: {metrics.operation_name}")
                
            self.logger.info(json.dumps(metric_data))
            
        except Exception as e:
            logger.error(f"Failed to log metrics: {str(e)}")
            
    def clear_history(self):
        """Clear performance history"""
        self.completed_operations = [] 
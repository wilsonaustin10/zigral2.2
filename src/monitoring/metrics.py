from typing import Dict, Any, Optional
import time
import logging
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
import psutil
import os

@dataclass
class SystemMetrics:
    """System resource metrics"""
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    disk_usage: Dict[str, float] = field(default_factory=dict)
    network_io: Dict[str, int] = field(default_factory=dict)

@dataclass
class ApplicationMetrics:
    """Application-specific metrics"""
    total_tasks: int = 0
    successful_tasks: int = 0
    failed_tasks: int = 0
    avg_task_duration: float = 0.0
    cache_hit_rate: float = 0.0
    error_count: Dict[str, int] = field(default_factory=dict)

class MetricsCollector:
    """Collect and aggregate metrics"""
    def __init__(self):
        self.system_metrics = SystemMetrics()
        self.app_metrics = ApplicationMetrics()
        self.start_time = datetime.now()
        
    def collect_system_metrics(self):
        """Collect system resource metrics"""
        try:
            process = psutil.Process(os.getpid())
            
            # CPU and memory
            self.system_metrics.cpu_percent = process.cpu_percent()
            self.system_metrics.memory_percent = process.memory_percent()
            
            # Disk usage
            disk = psutil.disk_usage('/')
            self.system_metrics.disk_usage = {
                'total': disk.total,
                'used': disk.used,
                'free': disk.free,
                'percent': disk.percent
            }
            
            # Network I/O
            net_io = psutil.net_io_counters()
            self.system_metrics.network_io = {
                'bytes_sent': net_io.bytes_sent,
                'bytes_recv': net_io.bytes_recv
            }
            
        except Exception as e:
            logging.error(f"Failed to collect system metrics: {str(e)}")
            
    def track_task(self, success: bool, duration: float, error_type: Optional[str] = None):
        """Track task execution metrics"""
        self.app_metrics.total_tasks += 1
        if success:
            self.app_metrics.successful_tasks += 1
        else:
            self.app_metrics.failed_tasks += 1
            if error_type:
                self.app_metrics.error_count[error_type] = \
                    self.app_metrics.error_count.get(error_type, 0) + 1
                    
        # Update average duration
        if self.app_metrics.avg_task_duration == 0:
            self.app_metrics.avg_task_duration = duration
        else:
            self.app_metrics.avg_task_duration = (
                self.app_metrics.avg_task_duration * (self.app_metrics.total_tasks - 1) +
                duration
            ) / self.app_metrics.total_tasks
            
    def track_cache_access(self, hit: bool):
        """Track cache hit/miss metrics"""
        total = (
            self.app_metrics.cache_hit_rate * 
            (self.app_metrics.total_tasks - 1)
        )
        if hit:
            total += 1
        self.app_metrics.cache_hit_rate = total / self.app_metrics.total_tasks
        
    def get_metrics(self) -> Dict[str, Any]:
        """Get all metrics"""
        self.collect_system_metrics()
        
        return {
            'timestamp': datetime.now().isoformat(),
            'uptime': (datetime.now() - self.start_time).total_seconds(),
            'system': asdict(self.system_metrics),
            'application': asdict(self.app_metrics)
        }
        
class MetricsLogger:
    """Log metrics to file/stdout"""
    def __init__(self, collector: MetricsCollector, log_file: Optional[str] = None):
        self.collector = collector
        self.log_file = log_file
        
    def log_metrics(self):
        """Log current metrics"""
        metrics = self.collector.get_metrics()
        
        # Log to file if specified
        if self.log_file:
            with open(self.log_file, 'a') as f:
                f.write(json.dumps(metrics) + '\n')
                
        # Log summary to stdout
        logging.info("=== Metrics Summary ===")
        logging.info(f"Uptime: {metrics['uptime']:.1f}s")
        logging.info(f"Tasks: {metrics['application']['total_tasks']}")
        logging.info(f"Success Rate: {metrics['application']['successful_tasks'] / max(1, metrics['application']['total_tasks']):.2%}")
        logging.info(f"Cache Hit Rate: {metrics['application']['cache_hit_rate']:.2%}")
        logging.info(f"Avg Duration: {metrics['application']['avg_task_duration']:.2f}s")
        logging.info(f"Memory Usage: {metrics['system']['memory_percent']:.1f}%")
        logging.info("====================")

def track_metrics(func):
    """Decorator to track function metrics"""
    async def wrapper(*args, **kwargs):
        start = time.time()
        error_type = None
        success = False
        
        try:
            result = await func(*args, **kwargs)
            success = True
            return result
        except Exception as e:
            error_type = type(e).__name__
            raise
        finally:
            duration = time.time() - start
            # Get metrics collector from class instance if available
            collector = getattr(args[0], 'metrics_collector', None)
            if collector:
                collector.track_task(success, duration, error_type)
    
    return wrapper 
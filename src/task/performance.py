from typing import Dict, Any, Callable
import time
import asyncio
from functools import lru_cache, wraps
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

@dataclass
class PerformanceMetrics:
    """Track performance metrics"""
    action_count: int = 0
    start_time: datetime = field(default_factory=datetime.now)
    action_durations: List[float] = field(default_factory=list)
    errors: Dict[str, int] = field(default_factory=dict)

class RateLimiter:
    """Rate limit action execution"""
    def __init__(self, max_actions: int, time_window: int):
        self.max_actions = max_actions
        self.time_window = time_window
        self.action_times = []
        
    async def acquire(self):
        """Acquire rate limit slot"""
        now = time.time()
        
        # Remove old actions
        self.action_times = [t for t in self.action_times 
                           if now - t < self.time_window]
                           
        # Check if we can proceed
        if len(self.action_times) >= self.max_actions:
            sleep_time = self.action_times[0] + self.time_window - now
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
                
        self.action_times.append(now)

def cache_state(func):
    """Cache state results with TTL"""
    cache = {}
    TTL = 60  # Cache for 60 seconds
    
    @wraps(func)
    async def wrapper(*args, **kwargs):
        key = str(args) + str(kwargs)
        now = time.time()
        
        if key in cache:
            result, timestamp = cache[key]
            if now - timestamp < TTL:
                return result
                
        result = await func(*args, **kwargs)
        cache[key] = (result, now)
        return result
        
    return wrapper

class PerformanceMonitor:
    """Monitor and track performance metrics"""
    def __init__(self):
        self.metrics = PerformanceMetrics()
        
    def track_action(self, duration: float):
        """Track action execution"""
        self.metrics.action_count += 1
        self.metrics.action_durations.append(duration)
        
    def track_error(self, error_type: str):
        """Track error occurrence"""
        self.metrics.errors[error_type] = self.metrics.errors.get(error_type, 0) + 1
        
    def get_stats(self) -> Dict[str, Any]:
        """Get performance statistics"""
        if not self.metrics.action_durations:
            return {}
            
        return {
            "total_actions": self.metrics.action_count,
            "avg_duration": sum(self.metrics.action_durations) / len(self.metrics.action_durations),
            "max_duration": max(self.metrics.action_durations),
            "error_count": sum(self.metrics.errors.values()),
            "error_types": dict(self.metrics.errors),
            "uptime": (datetime.now() - self.metrics.start_time).total_seconds()
        }

def measure_time(func):
    """Measure execution time of function"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        start = time.time()
        try:
            result = await func(*args, **kwargs)
            duration = time.time() - start
            logging.info(f"{func.__name__} took {duration:.2f}s")
            return result
        except Exception as e:
            duration = time.time() - start
            logging.error(f"{func.__name__} failed after {duration:.2f}s: {str(e)}")
            raise
    return wrapper 
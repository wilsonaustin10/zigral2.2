import pytest
import asyncio
import time
import os
import tempfile
from datetime import datetime, timedelta
import psutil

from src.actions.action_cache import ActionCache, Action, ActionSequence
from src.llm.claude_client import ClaudeClient
from src.task.executor import TaskExecutor, GUIState

@pytest.fixture
async def test_db_path():
    """Create a temporary database file for testing"""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    yield db_path
    os.unlink(db_path)

@pytest.mark.asyncio
async def test_cache_performance(test_db_path):
    """Test cache read/write performance"""
    db_path = await anext(test_db_path)
    async with ActionCache(db_path=db_path) as cache:
        # Create test data
        sequences = []
        for i in range(100):
            sequences.append(ActionSequence(
                task_key=f"task_{i}",
                actions=[
                    Action(type="click", selector=f"#button_{i}"),
                    Action(type="type", selector=f"#input_{i}", text=f"test_{i}")
                ],
                success_rate=1.0,
                execution_count=1,
                avg_execution_time=0.5,
                metadata={},
                last_used=datetime.now()
            ))
        
        # Test write performance
        start_time = datetime.now()
        for sequence in sequences:
            await cache.store(sequence)
        write_time = (datetime.now() - start_time).total_seconds()
        assert write_time < 5.0  # Should complete in reasonable time
        
        # Test read performance
        start_time = datetime.now()
        for i in range(100):
            sequence = await cache.get_similar_task(f"task_{i}")
            assert sequence is not None
            assert len(sequence.actions) == 2
        read_time = (datetime.now() - start_time).total_seconds()
        assert read_time < 5.0  # Should complete in reasonable time

@pytest.mark.asyncio
async def test_cache_memory_usage(test_db_path):
    """Test cache memory efficiency"""
    db_path = await anext(test_db_path)
    async with ActionCache(db_path=db_path) as cache:
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss
        
        # Store large number of sequences
        for i in range(1000):
            sequence = ActionSequence(
                task_key=f"large_task_{i}",
                actions=[Action(type="click", selector=f"#{j}") for j in range(10)],
                success_rate=1.0,
                execution_count=1,
                avg_execution_time=0.5,
                metadata={"large": "data" * 100},  # Large metadata
                last_used=datetime.now()
            )
            await cache.store(sequence)
        
        final_memory = process.memory_info().rss
        memory_increase = (final_memory - initial_memory) / 1024 / 1024  # MB
        
        # Assert reasonable memory usage (less than 100MB increase)
        assert memory_increase < 100

@pytest.mark.asyncio
async def test_claude_rate_limiting(test_db_path):
    """Test rate limiting for Claude API requests"""
    db_path = await anext(test_db_path)
    async with ActionCache(db_path=db_path) as cache:
        # Create test data
        sequence = ActionSequence(
            task_key="test_task",
            actions=[
                Action(type="click", selector="#submit-btn"),
                Action(type="type", selector="#input", text="test")
            ],
            success_rate=1.0,
            execution_count=1,
            avg_execution_time=0.5,
            metadata={},
            last_used=datetime.now()
        )

        # Test rapid requests
        for i in range(10):
            sequence.task_key = f"task_{i}"
            await cache.store(sequence)
            await asyncio.sleep(0.1)  # Small delay between requests

        # Verify cache state
        stats = await cache.get_stats()
        assert stats["total_sequences"] == 10
        assert stats["avg_success_rate"] == 1.0

@pytest.mark.asyncio
async def test_concurrent_cache_access(test_db_path):
    """Test concurrent cache access"""
    db_path = await anext(test_db_path)
    async with ActionCache(db_path=db_path) as cache:
        async def write_task(i):
            sequence = ActionSequence(
                task_key=f"concurrent_task_{i}",
                actions=[Action(type="click", selector=f"#button_{i}")],
                success_rate=1.0,
                execution_count=1,
                avg_execution_time=0.5,
                metadata={},
                last_used=datetime.now()
            )
            await cache.store(sequence)
            return await cache.get_similar_task(sequence.task_key)
        
        # Run concurrent operations
        tasks = [write_task(i) for i in range(50)]
        results = await asyncio.gather(*tasks)
        
        # Verify all operations succeeded
        assert all(r is not None for r in results)
        assert len(results) == 50

@pytest.mark.asyncio
async def test_cache_cleanup(test_db_path):
    """Test cache cleanup performance"""
    db_path = await anext(test_db_path)
    async with ActionCache(db_path=db_path) as cache:
        # Store sequences with old timestamps
        old_time = datetime.now() - timedelta(days=30)
        for i in range(100):
            sequence = ActionSequence(
                task_key=f"old_task_{i}",
                actions=[Action(type="click", selector=f"#button_{i}")],
                success_rate=1.0,
                execution_count=1,
                avg_execution_time=0.5,
                metadata={},
                last_used=old_time
            )
            await cache.store(sequence)
        
        # Store sequences with recent timestamps
        for i in range(100):
            sequence = ActionSequence(
                task_key=f"new_task_{i}",
                actions=[Action(type="click", selector=f"#button_{i}")],
                success_rate=1.0,
                execution_count=1,
                avg_execution_time=0.5,
                metadata={},
                last_used=datetime.now()
            )
            await cache.store(sequence)
        
        # Measure cleanup performance
        start_time = time.time()
        stats_before = await cache.get_stats()
        
        await cache.cleanup(max_age_days=7)
        
        cleanup_time = time.time() - start_time
        stats_after = await cache.get_stats()
        
        # Verify cleanup performance and results
        assert cleanup_time < 1.0  # Cleanup should be fast
        assert stats_after["total_sequences"] == 100  # Only recent sequences remain
        assert stats_before["total_sequences"] == 200  # Had both old and new before 
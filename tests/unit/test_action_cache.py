import pytest
import os
import tempfile
from datetime import datetime, timedelta
from src.actions.action_cache import ActionCache, Action, ActionSequence

@pytest.fixture
async def test_db_path():
    """Create a temporary database file for testing"""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    yield db_path
    os.unlink(db_path)

@pytest.fixture
async def action_cache(test_db_path):
    """Create an ActionCache instance for testing"""
    cache = ActionCache(db_path=test_db_path)
    yield cache
    await cache.clear()

@pytest.fixture
def sample_action_sequence():
    """Create a sample action sequence for testing"""
    actions = [
        Action(type="click", selector="#test-button"),
        Action(type="type", selector="#test-input", text="test"),
        Action(type="wait", timeout=1000)
    ]
    return ActionSequence(
        task_key="test_task",
        actions=actions,
        success_rate=0.0,
        execution_count=0,
        avg_execution_time=0.0,
        metadata={},
        last_used=datetime.now()
    )

@pytest.mark.asyncio
async def test_store_and_retrieve(test_db_path):
    """Test storing and retrieving an action sequence"""
    db_path = await anext(test_db_path)
    async with ActionCache(db_path=db_path) as cache:
        # Create test sequence
        actions = [
            Action(type="click", selector="#test-button"),
            Action(type="type", selector="#test-input", text="test"),
            Action(type="wait", timeout=1000)
        ]
        sequence = ActionSequence(
            task_key="test_task",
            actions=actions,
            success_rate=0.0,
            execution_count=0,
            avg_execution_time=0.0,
            metadata={},
            last_used=datetime.now()
        )
        
        # Store sequence
        await cache.store(sequence)
        
        # Retrieve sequence
        retrieved = await cache.get_similar_task(sequence.task_key)
        
        assert retrieved is not None
        assert retrieved.task_key == sequence.task_key
        assert len(retrieved.actions) == len(sequence.actions)
        assert retrieved.actions[0].type == "click"
        assert retrieved.actions[0].selector == "#test-button"

@pytest.mark.asyncio
async def test_update_stats(test_db_path):
    """Test updating statistics for a stored sequence"""
    db_path = await anext(test_db_path)
    async with ActionCache(db_path=db_path) as cache:
        # Create and store sequence
        actions = [Action(type="click", selector="#test-button")]
        sequence = ActionSequence(
            task_key="test_task",
            actions=actions,
            success_rate=0.0,
            execution_count=0,
            avg_execution_time=0.0,
            metadata={},
            last_used=datetime.now()
        )
        await cache.store(sequence)
        
        # Update stats
        await cache.update_stats(sequence.task_key, 1.5, True)
        
        # Verify stats
        retrieved = await cache.get_similar_task(sequence.task_key)
        assert retrieved is not None
        assert retrieved.success_rate > 0
        assert retrieved.execution_count == 1
        assert retrieved.avg_execution_time == 1.5

@pytest.mark.asyncio
async def test_clear_cache(test_db_path):
    """Test clearing the cache"""
    db_path = await anext(test_db_path)
    async with ActionCache(db_path=db_path) as cache:
        # Create and store sequence
        actions = [Action(type="click", selector="#test-button")]
        sequence = ActionSequence(
            task_key="test_task",
            actions=actions,
            success_rate=0.0,
            execution_count=0,
            avg_execution_time=0.0,
            metadata={},
            last_used=datetime.now()
        )
        await cache.store(sequence)
        
        # Clear cache
        await cache.clear()
        
        # Verify sequence is gone
        retrieved = await cache.get_similar_task(sequence.task_key)
        assert retrieved is None

@pytest.mark.asyncio
async def test_get_stats(test_db_path):
    """Test retrieving cache statistics"""
    db_path = await anext(test_db_path)
    async with ActionCache(db_path=db_path) as cache:
        # Create and store sequence
        actions = [Action(type="click", selector="#test-button")]
        sequence = ActionSequence(
            task_key="test_task",
            actions=actions,
            success_rate=0.0,
            execution_count=0,
            avg_execution_time=0.0,
            metadata={},
            last_used=datetime.now()
        )
        await cache.store(sequence)
        
        # Update stats
        await cache.update_stats(sequence.task_key, 1.5, True)
        
        # Get stats
        stats = await cache.get_stats()
        
        assert stats["total_sequences"] == 1
        assert stats["avg_success_rate"] == 1.0
        assert stats["avg_executions"] == 1
        assert stats["avg_execution_time"] == 1.5

@pytest.mark.asyncio
async def test_cleanup(test_db_path):
    """Test cleaning up old cache entries"""
    db_path = await anext(test_db_path)
    async with ActionCache(db_path=db_path) as cache:
        # Create old sequence
        actions = [Action(type="click", selector="#test-button")]
        old_sequence = ActionSequence(
            task_key="old_task",
            actions=actions,
            success_rate=0.0,
            execution_count=0,
            avg_execution_time=0.0,
            metadata={},
            last_used=datetime.now() - timedelta(days=31)
        )
        await cache.store(old_sequence)
        
        # Create recent sequence
        recent_sequence = ActionSequence(
            task_key="recent_task",
            actions=actions,
            success_rate=0.0,
            execution_count=0,
            avg_execution_time=0.0,
            metadata={},
            last_used=datetime.now()
        )
        await cache.store(recent_sequence)
        
        # Clean up old entries
        await cache.cleanup(max_age_days=30)
        
        # Verify old sequence is gone but recent remains
        old_retrieved = await cache.get_similar_task(old_sequence.task_key)
        recent_retrieved = await cache.get_similar_task(recent_sequence.task_key)
        
        assert old_retrieved is None
        assert recent_retrieved is not None

@pytest.mark.asyncio
async def test_store_sequence(test_db_path):
    """Test storing a sequence using store_sequence helper"""
    db_path = await anext(test_db_path)
    async with ActionCache(db_path=db_path) as cache:
        actions = [
            Action(type="click", selector="#test-button"),
            Action(type="type", selector="#test-input", text="test")
        ]
        
        # Store sequence
        await cache.store_sequence("test_task", actions)
        
        # Verify sequence was stored
        retrieved = await cache.get_similar_task("test_task")
        assert retrieved is not None
        assert len(retrieved.actions) == 2
        assert retrieved.actions[0].type == "click"
        assert retrieved.actions[1].type == "type" 
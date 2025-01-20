from typing import Optional, List, Dict
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict, field
import aiosqlite
import sqlite3
import json
import logging
from pathlib import Path
import re
import redis
import asyncio

logger = logging.getLogger(__name__)

SESSION_TIMEOUT = 30 * 60  # 30 minutes in seconds

@dataclass
class Action:
    """Represents a single browser action"""
    type: str  # navigate, click, type, wait, press
    selector: Optional[str] = None
    url: Optional[str] = None
    text: Optional[str] = None
    timeout: Optional[int] = None
    key: Optional[str] = None
    timestamp: Optional[datetime] = field(default_factory=lambda: datetime.now())  # Initialize with current time

    def to_dict(self) -> dict:
        """Convert action to dictionary with proper timestamp handling"""
        d = asdict(self)
        if self.timestamp:
            d['timestamp'] = self.timestamp.isoformat()
        return d

@dataclass
class ActionSequence:
    """Represents a sequence of actions for a task"""
    task_key: str
    actions: List[Action]
    success_rate: float
    execution_count: int
    avg_execution_time: float
    metadata: Dict
    last_used: datetime
    action_success_rates: Dict
    partial_successes: List

    def __init__(self, task_key: str, actions: List[Action], success_rate: float = 0.0,
                 execution_count: int = 0, avg_execution_time: float = 0.0,
                 metadata: Dict = None, last_used: datetime = None):
        self.task_key = task_key
        self.actions = actions
        self.success_rate = success_rate
        self.execution_count = execution_count
        self.avg_execution_time = avg_execution_time
        self.metadata = metadata or {}
        self.last_used = last_used or datetime.now()
        self.action_success_rates = {}  # Track success rate per action
        self.partial_successes = []  # Store which actions succeeded in partial success cases

    def update_action_success(self, action_index: int, success: bool) -> None:
        """Update success rate for a specific action"""
        if action_index not in self.action_success_rates:
            self.action_success_rates[action_index] = {'success': 0, 'total': 0}
        
        self.action_success_rates[action_index]['total'] += 1
        if success:
            self.action_success_rates[action_index]['success'] += 1

    def get_action_success_rate(self, action_index: int) -> float:
        """Get success rate for a specific action"""
        if action_index not in self.action_success_rates:
            return 0.0
        stats = self.action_success_rates[action_index]
        return stats['success'] / stats['total'] if stats['total'] > 0 else 0.0

    def record_partial_success(self, successful_indices: List[int]) -> None:
        """Record which actions succeeded in a partial success case"""
        self.partial_successes.append({
            'timestamp': datetime.now(),
            'successful_actions': successful_indices
        })

class ActionCache:
    """Caches successful action sequences for reuse"""
    
    def __init__(self, db_path: str = "action_cache.db", redis_url: str = "redis://localhost:6379"):
        self.db_path = db_path
        self.db = None  # Initialize db attribute
        self._init_db()
        
        # Initialize Redis connection
        self.redis = redis.Redis.from_url(redis_url, decode_responses=True)
        self.current_session = None
        self.current_user_id = None
        
        # Start default session
        asyncio.create_task(self.start_session("default_user"))
        
    def _init_db(self):
        """Initialize SQLite database with user and session tracking"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                # First check if table exists and get its columns
                cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='action_sequences'")
                table_exists = cursor.fetchone() is not None
                
                if not table_exists:
                    # Create table if it doesn't exist
                conn.execute("""
                        CREATE TABLE action_sequences (
                            task_key TEXT,
                            user_id TEXT,
                        actions TEXT,
                        success_rate REAL,
                        execution_count INTEGER,
                        avg_execution_time REAL,
                        metadata TEXT,
                            last_used TIMESTAMP,
                            PRIMARY KEY (task_key, user_id)
                    )
                """)
                else:
                    # Check if user_id column exists
                    cursor = conn.execute("PRAGMA table_info(action_sequences)")
                    columns = [col[1] for col in cursor.fetchall()]
                    if 'user_id' not in columns:
                        # Add user_id column to existing table
                        conn.execute("ALTER TABLE action_sequences ADD COLUMN user_id TEXT DEFAULT 'default_user'")
                    
                conn.commit()
                logger.info("Cache database initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize cache database: {str(e)}")
            raise
            
    async def connect(self):
        """Establish database connection"""
        try:
            if not self.db:
                self.db = await aiosqlite.connect(self.db_path)
            return self.db
        except Exception as e:
            logger.error(f"Failed to connect to database: {str(e)}")
            return None

    async def start_session(self, user_id: str) -> None:
        """Start a new session for a user"""
        try:
            self.current_user_id = user_id
            self.current_session = datetime.now().isoformat()
            
            # Set session key in Redis with timeout
            session_key = f"session:{user_id}"
            self.redis.set(session_key, self.current_session, ex=SESSION_TIMEOUT)
            
            # Load user's sequences from SQLite into Redis
            await self._load_user_sequences(user_id)
            
        except Exception as e:
            logger.error(f"Failed to start session: {str(e)}")
            
    async def _load_user_sequences(self, user_id: str) -> None:
        """Load user's sequences from SQLite into Redis"""
        try:
            db = await self.connect()
            cursor = await db.execute(
                "SELECT task_key, actions, metadata FROM action_sequences WHERE user_id = ?",
                (user_id,)
            )
            rows = await cursor.fetchall()
            
            # Store in Redis with timeout
            for row in rows:
                task_key, actions_json, metadata_json = row
                cache_key = f"sequence:{user_id}:{task_key}"
                data = {
                    'actions': actions_json,
                    'metadata': metadata_json
                }
                self.redis.set(cache_key, json.dumps(data), ex=SESSION_TIMEOUT)
                
        except Exception as e:
            logger.error(f"Failed to load user sequences: {str(e)}")

    async def extend_session(self) -> None:
        """Extend current session timeout"""
        if self.current_user_id:
            session_key = f"session:{self.current_user_id}"
            self.redis.expire(session_key, SESSION_TIMEOUT)
            
            # Extend all sequence keys for this user
            pattern = f"sequence:{self.current_user_id}:*"
            for key in self.redis.scan_iter(pattern):
                self.redis.expire(key, SESSION_TIMEOUT)

    def _index_task_semantics(self, task: str, sequence_key: str):
        """Index task components for semantic search"""
        try:
            normalized = self._normalize_task(task)
            components = normalized.split()
            
            # Extract entities and verbs
            entities = {w.split(':')[1] for w in components if ':' in w}
            verbs = {w for w in components if w in {'go to', 'find', 'click', 'type'}}
            
            # Store in Redis sets with user-specific prefixes
            user_prefix = f"user:{self.current_user_id}"
            pipe = self.redis.pipeline()
            
            # Index by entities
            for entity in entities:
                key = f"{user_prefix}:entity:{entity}"
                pipe.sadd(key, sequence_key)
                pipe.expire(key, SESSION_TIMEOUT)
                
            # Index by verbs
            for verb in verbs:
                key = f"{user_prefix}:verb:{verb}"
                pipe.sadd(key, sequence_key)
                pipe.expire(key, SESSION_TIMEOUT)
                
            # Store normalized form
            key = f"{user_prefix}:normalized:{normalized}"
            pipe.set(key, sequence_key, ex=SESSION_TIMEOUT)
            
            pipe.execute()  # Synchronous execution
            
        except Exception as e:
            logger.error(f"Failed to index task semantics: {str(e)}")
            
    async def store_sequence_with_results(self, task: str, actions: List[Action], 
                                        action_results: List[bool], 
                                        user_confirmed: bool = False) -> None:
        """Store a sequence with results in both Redis and SQLite"""
        if not self.current_user_id:
            logger.warning("No active session, skipping sequence storage")
            return
            
        try:
            # Prepare sequence data
            normalized_task = self._normalize_task(task)
            sequence = ActionSequence(
                task_key=task,
                actions=actions
            )
            
            # Update success information
            successful_indices = []
            for i, (action, success) in enumerate(zip(actions, action_results)):
                sequence.update_action_success(i, success)
                if success:
                    successful_indices.append(i)
                    
            if successful_indices and len(successful_indices) < len(actions):
                sequence.record_partial_success(successful_indices)
                
            sequence.execution_count += 1
            if user_confirmed:
                sequence.success_rate = (sequence.success_rate * (sequence.execution_count - 1) + 1) / sequence.execution_count
                
            # Store in Redis
            cache_key = f"sequence:{self.current_user_id}:{normalized_task}"
            data = {
                'actions': json.dumps([action.to_dict() for action in actions]),
                'metadata': json.dumps({
                    'action_success_rates': sequence.action_success_rates,
                    'partial_successes': [
                        {
                            'timestamp': ps['timestamp'].isoformat(),
                            'successful_actions': ps['successful_actions']
                        }
                        for ps in sequence.partial_successes
                    ]
                })
            }
            self.redis.set(cache_key, json.dumps(data), ex=SESSION_TIMEOUT)
            
            # Index for semantic search
            self._index_task_semantics(task, cache_key)  # Remove await
            
            # Persist to SQLite
            await self._store_in_db(sequence)
            
        except Exception as e:
            logger.error(f"Failed to store sequence with results: {str(e)}")

    async def get_similar_task(self, task: str) -> Optional[ActionSequence]:
        """Get similar task using semantic search in Redis, falling back to SQLite"""
        if not self.current_user_id:
            return None
            
        try:
            # Extend session timeout
            await self.extend_session()
            
            # First try exact normalized match
            normalized_task = self._normalize_task(task)
            user_prefix = f"user:{self.current_user_id}"
            exact_key = f"{user_prefix}:normalized:{normalized_task}"
            sequence_key = self.redis.get(exact_key)
            
            if not sequence_key:
                # Try semantic search
                components = normalized_task.split()
                entities = {w.split(':')[1] for w in components if ':' in w}
                verbs = {w for w in components if w in {'go to', 'find', 'click', 'type'}}
                
                # Get candidate sequences matching entities and verbs
                candidates = set()
                for entity in entities:
                    key = f"{user_prefix}:entity:{entity}"
                    candidates.update(self.redis.smembers(key))
                    
                for verb in verbs:
                    key = f"{user_prefix}:verb:{verb}"
                    candidates.update(self.redis.smembers(key))
                
                # Score candidates
                best_score = 0
                best_sequence = None
                
                for candidate_key in candidates:
                    cached_data = self.redis.get(candidate_key)
                    if cached_data:
                        data = json.loads(cached_data)
                        actions_data = json.loads(data['actions'])
                        metadata = json.loads(data['metadata'])
                        
                        # Calculate similarity score
                        cached_task = candidate_key.split(':')[-1]
                        score = self._calculate_task_similarity(task, cached_task, actions_data)
                        
                        # Check success criteria
                        success_rate = metadata.get('action_success_rates', {}).get('overall', 0)
                        if score > best_score and score >= 0.8 and success_rate >= 0.8:
                            best_score = score
                            best_sequence = ActionSequence(
                                task_key=task,
                                actions=[Action(**a) for a in actions_data],
                                success_rate=success_rate,
                                metadata=metadata
                            )
                
                if best_sequence:
                    return best_sequence
            
            elif sequence_key:
                # Use exact match
                cached_data = self.redis.get(sequence_key)
                if cached_data:
                    data = json.loads(cached_data)
                    actions_data = json.loads(data['actions'])
                    metadata = json.loads(data['metadata'])
                    
                    success_rate = metadata.get('action_success_rates', {}).get('overall', 0)
                    if success_rate >= 0.8:
                        return ActionSequence(
                            task_key=task,
                            actions=[Action(**a) for a in actions_data],
                            success_rate=success_rate,
                            metadata=metadata
                        )
            
            # Fall back to SQLite for historical data
            return await self._get_similar_task_from_db(task)
            
        except Exception as e:
            logger.error(f"Failed to get similar task: {str(e)}")
            return None

    async def cleanup_expired_sessions(self) -> None:
        """Remove expired sessions and their associated data"""
        try:
            # Get all session keys
            for key in self.redis.scan_iter("session:*"):
                if not self.redis.exists(key):
                    user_id = key.split(':')[1]
                    # Clean up associated sequence data
                    pattern = f"sequence:{user_id}:*"
                    for seq_key in self.redis.scan_iter(pattern):
                        self.redis.delete(seq_key)
                        
        except Exception as e:
            logger.error(f"Failed to cleanup expired sessions: {str(e)}")

    async def end_session(self) -> None:
        """End current session and persist final state to SQLite"""
        if self.current_user_id:
            try:
                # Ensure we have a valid DB connection
                if not self.db:
                    self.db = await aiosqlite.connect(self.db_path)
                
                # Get all sequences for current user from Redis
                pattern = f"sequence:{self.current_user_id}:*"
                for key in self.redis.scan_iter(pattern):
                    data = self.redis.get(key)
                    if data:
                        # Parse the Redis data
                        sequence_data = json.loads(data)
                        actions_data = json.loads(sequence_data['actions'])
                        metadata = json.loads(sequence_data['metadata'])
                        
                        # Create sequence with proper timestamp handling
                        sequence = ActionSequence(
                            task_key=key.split(':')[-1],
                            actions=[Action(**a) for a in actions_data],
                            metadata=metadata,
                            last_used=datetime.now()  # Use fresh timestamp
                        )
                        
                        # Store in SQLite
                        await self._store_in_db(sequence)
                        
                # Clear Redis data
                self.redis.delete(f"session:{self.current_user_id}")
                for key in self.redis.scan_iter(pattern):
                    self.redis.delete(key)
                    
                self.current_user_id = None
                self.current_session = None
                
                # Close DB connection
                if self.db:
                    await self.db.close()
                    self.db = None
                    
            except Exception as e:
                logger.error(f"Failed to end session: {str(e)}")
                # Ensure DB connection is closed even on error
                if self.db:
                    await self.db.close()
                    self.db = None
            
    async def store(self, sequence: ActionSequence) -> None:
        """Store an action sequence in the cache"""
        try:
            # Convert actions to JSON string
            actions_json = json.dumps([asdict(action) for action in sequence.actions])
            
            # Insert or update sequence using aiosqlite
            db = await self.connect()
                await db.execute(
                    """
                    INSERT OR REPLACE INTO action_sequences 
                    (task_key, actions, success_rate, execution_count, avg_execution_time, metadata, last_used)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        sequence.task_key,
                        actions_json,
                        sequence.success_rate,
                        sequence.execution_count,
                        sequence.avg_execution_time,
                        json.dumps(sequence.metadata),
                        sequence.last_used.isoformat()
                    )
                )
                await db.commit()
        except Exception as e:
            logger.error(f"Failed to store sequence: {e}")
            raise
            
    def _normalize_task(self, task: str) -> str:
        """Normalize task description for better matching"""
        # Convert to lowercase and remove extra whitespace
        normalized = " ".join(task.lower().split())
        
        # Action verb synonyms - group similar actions
        action_verb_groups = {
            "navigation": {
                "go to", "navigate to", "open", "visit", "browse to", "load", "access"
            },
            "search": {
                "find", "search for", "look for", "locate", "get", "show", "display", "check", "view"
            },
            "interaction": {
                "click", "press", "select", "choose", "pick"
            },
            "input": {
                "type", "enter", "input", "fill", "write"
            }
        }
        
        # Replace verbs with their canonical form
        canonical_forms = {
            "navigation": "go to",
            "search": "find",
            "interaction": "click",
            "input": "type"
        }
        
        # Find and replace verb phrases
        words = normalized.split()
        for i, word in enumerate(words):
            # Check for two-word phrases
            if i < len(words) - 1:
                phrase = f"{word} {words[i+1]}"
                for group, verbs in action_verb_groups.items():
                    if phrase in verbs:
                        words[i:i+2] = [canonical_forms[group]]
                        break
            # Check single words
            for group, verbs in action_verb_groups.items():
                if word in verbs:
                    words[i] = canonical_forms[group]
                    break
        
        normalized = " ".join(words)
        
        # Remove noise words
        noise_words = {"the", "a", "an", "for", "of", "in", "on", "at", "to", "and", "or"}
        words = [w for w in normalized.split() if w not in noise_words]
        
        # Reconstruct normalized task
        return " ".join(words)

    async def store_sequence(self, task: str, actions: List[Action]) -> None:
        """Store an action sequence with task aliases"""
        normalized_task = self._normalize_task(task)
        
        # Create or update sequence
        if normalized_task not in self.sequences:
            self.sequences[normalized_task] = ActionSequence(
                task_key=task,
                actions=actions,
                success_rate=0.0,
                execution_count=0,
                avg_execution_time=0.0,
                metadata={},
                last_used=datetime.now()
            )
        else:
            # Update existing sequence if new one is shorter/better
            existing = self.sequences[normalized_task]
            if len(actions) < len(existing.actions):
                existing.actions = actions
                
        # Update task aliases
        if normalized_task not in self.task_aliases:
            self.task_aliases[normalized_task] = set()
        self.task_aliases[normalized_task].add(task)

    async def _get_similar_task_from_db(self, task: str) -> Optional[ActionSequence]:
        """Get a similar task from the database"""
        try:
            # Normalize task description
            task = task.lower().strip()
            
            # First try exact match
            cursor = await self.db.execute(
                "SELECT task_key, actions, metadata FROM action_sequences"
            )
            rows = await cursor.fetchall()
            
            best_match = None
            best_score = 0
            
            for row in rows:
                cached_task = row[0].lower().strip()
                cached_actions = json.loads(row[1])
                metadata = json.loads(row[2]) if row[2] else {}
                
                # Calculate similarity score
                score = self._calculate_task_similarity(task, cached_task, cached_actions)
                
                # Must meet minimum threshold and have good success rate
                success_rate = metadata.get('success_rate', 0)
                if score > best_score and score >= 0.8 and success_rate >= 0.8:
                    best_score = score
                    best_match = ActionSequence(
                        task_key=row[0],
                        actions=[Action(**a) for a in cached_actions],
                        success_rate=success_rate
                    )
            
            return best_match
            
        except Exception as e:
            logger.error(f"Failed to get similar task from database: {str(e)}")
            return None
            
    def _calculate_task_similarity(self, task1: str, task2: str, cached_actions: List[dict]) -> float:
        """Calculate similarity score between two tasks"""
        # Normalize both tasks
        task1_norm = self._normalize_task(task1)
        task2_norm = self._normalize_task(task2)
        
        # Split into words
        words1 = set(task1_norm.split())
        words2 = set(task2_norm.split())
        
        # Key action verbs that should match (using canonical forms)
        action_verbs = {'go to', 'find', 'click', 'type'}
        
        # Get canonical verbs from each task
        task1_verbs = words1.intersection(action_verbs)
        task2_verbs = words2.intersection(action_verbs)
        
        # Calculate word similarity
        common_words = words1.intersection(words2)
        word_score = len(common_words) / max(len(words1), len(words2))
        
        # Calculate verb similarity - at least one verb should match
        verb_score = 1.0 if task1_verbs.intersection(task2_verbs) else 0.0
        
        # Calculate final score - verb matching is critical
        return word_score * verb_score if verb_score > 0 else 0.0

    async def update_stats(self, task: str, old_success_rate: float, success: bool) -> None:
        """Update sequence statistics"""
        normalized_task = self._normalize_task(task)
        if normalized_task in self.sequences:
            sequence = self.sequences[normalized_task]
            sequence.execution_count += 1
            if success:
                sequence.success_rate = (sequence.success_rate * (sequence.execution_count - 1) + 1) / sequence.execution_count
            
            # If success rate improves significantly, make this the canonical sequence
            if sequence.success_rate > old_success_rate + 0.2:  # 20% improvement threshold
                for alias in self.task_aliases.get(normalized_task, set()):
                    if alias != task:
                        self.sequences[self._normalize_task(alias)] = sequence
            
    async def clear(self):
        """Clear all cached sequences"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("DELETE FROM action_sequences")
                await db.commit()
                
        except Exception as e:
            logger.error(f"Failed to clear cache: {str(e)}")
            
    async def get_stats(self) -> Dict:
        """Get cache statistics"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                    """
                    SELECT COUNT(*) as total,
                           AVG(success_rate) as avg_success,
                           AVG(execution_count) as avg_executions,
                           AVG(avg_execution_time) as avg_time
                    FROM action_sequences
                    """
                ) as cursor:
                    stats = await cursor.fetchone()
                    
                    return {
                        "total_sequences": stats[0],
                        "avg_success_rate": stats[1],
                        "avg_executions": stats[2],
                        "avg_execution_time": stats[3]
                    }
                    
        except Exception as e:
            logger.error(f"Failed to get cache stats: {str(e)}")
            return {}

    async def close(self):
        """Clean up resources"""
        try:
            if self.db:
                await self.db.close()
            if self.redis:
                await self.end_session()
                self.redis.close()
            logger.info("Cache resources cleaned up successfully")
        except Exception as e:
            logger.error(f"Error during cache cleanup: {str(e)}")

    async def cleanup(self, max_age_days: int = 30):
        """Remove old entries from the cache"""
        try:
            cutoff_date = (datetime.now() - timedelta(days=max_age_days)).isoformat()
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    """
                    DELETE FROM action_sequences
                    WHERE last_used < ?
                    """, 
                    (cutoff_date,)
                )
                await db.commit()
            logger.info(f"Cleaned up action cache (removed entries older than {max_age_days} days)")
        except Exception as e:
            logger.error(f"Failed to cleanup cache: {str(e)}")
            # Continue execution even if cleanup fails

    async def store_sequence(self, task_key: str, actions: List[Action]) -> None:
        """Store a new action sequence in the cache"""
        try:
            db = await self.connect()
            if not db:
                logger.warning("No database connection, skipping cache storage")
                return
                
            sequence = ActionSequence(
                task_key=task_key,
                actions=actions,
                success_rate=0.0,
                execution_count=0,
                avg_execution_time=0.0,
                metadata={},
                last_used=datetime.now()
            )
            await self.store(sequence)
        except Exception as e:
            logger.error(f"Failed to store sequence: {str(e)}")
            # Continue execution even if storage fails 

    async def _store_in_db(self, sequence: ActionSequence) -> None:
        """Store sequence in database with detailed success information"""
        if not sequence:
            return
        
        try:
            # Ensure we have a DB connection
            if not self.db:
                self.db = await aiosqlite.connect(self.db_path)
            
            # Convert action success rates and partial successes to JSON
            metadata = {
                'action_success_rates': sequence.action_success_rates,
                'partial_successes': []
            }
            
            # Handle partial success timestamps
            for ps in sequence.partial_successes:
                timestamp = ps['timestamp']
                if isinstance(timestamp, datetime):
                    timestamp_str = timestamp.isoformat()
                elif isinstance(timestamp, str):
                    timestamp_str = timestamp  # Already a string
                else:
                    timestamp_str = datetime.now().isoformat()  # Fallback
                
                metadata['partial_successes'].append({
                    'timestamp': timestamp_str,
                    'successful_actions': ps['successful_actions']
                })
            
            metadata.update(sequence.metadata)
            
            # Convert actions to JSON using to_dict method
            actions_json = json.dumps([action.to_dict() for action in sequence.actions])
            
            # Ensure last_used is a valid timestamp string
            last_used = sequence.last_used
            if isinstance(last_used, datetime):
                last_used_str = last_used.isoformat()
            elif isinstance(last_used, str):
                last_used_str = last_used
            else:
                last_used_str = datetime.now().isoformat()
            
            # Store in database
            await self.db.execute(
                """
                INSERT OR REPLACE INTO action_sequences 
                (task_key, actions, success_rate, execution_count, avg_execution_time, metadata, last_used)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sequence.task_key,
                    actions_json,
                    sequence.success_rate,
                    sequence.execution_count,
                    sequence.avg_execution_time,
                    json.dumps(metadata),
                    last_used_str
                )
            )
            await self.db.commit()
            
        except Exception as e:
            logger.error(f"Failed to store sequence in database: {str(e)}")
            # Don't raise - Redis is our primary storage

    def get_action_status_prompt(self, actions: List[Action]) -> str:
        """Generate a prompt to ask user about specific action successes"""
        prompt = "Which actions completed successfully? (Enter numbers, separated by commas)\n"
        for i, action in enumerate(actions, 1):
            prompt += f"{i}. {action.type}: "
            if action.type == 'navigate':
                prompt += f"Go to {action.url}\n"
            elif action.type in ['click', 'wait']:
                prompt += f"Find element {action.selector}\n"
            elif action.type == 'type':
                prompt += f"Type into {action.selector}\n"
            elif action.type == 'press':
                prompt += f"Press {action.key}\n"
        prompt += "\nEnter numbers or 'all' if everything succeeded: " 
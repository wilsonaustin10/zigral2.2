# Migration Guide to Zigral 2.2

This guide helps you migrate from previous versions to Zigral 2.2. Please follow these steps in order to ensure a smooth transition.

## Major Changes

### 1. Task Management System
- **Before**: Direct action execution
- **Now**: Task-based orchestration with queuing
- **Migration**:
  ```python
  # Old way
  agent.execute_action(action)
  
  # New way
  task = Task(action=action, priority=Priority.NORMAL)
  task_manager.submit(task)
  ```

### 2. State Management
- **Before**: In-memory state
- **Now**: Persistent state with transactions
- **Migration**:
  ```python
  # Old way
  state = {"key": "value"}
  
  # New way
  from src.state import StateManager
  
  state_manager = StateManager()
  with state_manager.transaction() as state:
      state["key"] = "value"
  ```

### 3. Monitoring Integration
- **Before**: Basic logging
- **Now**: Full observability stack
- **Migration**:
  1. Update your `.env` file with new monitoring configurations
  2. Replace logging calls:
  ```python
  # Old way
  logging.info("Event occurred")
  
  # New way
  import structlog
  logger = structlog.get_logger()
  logger.info("event.occurred", metadata={"key": "value"})
  ```

### 4. Safety Layer
- **Before**: Basic input validation
- **Now**: Comprehensive safety checks
- **Migration**:
  ```python
  # Old way
  if validate_input(data):
      process(data)
  
  # New way
  from src.safety import SafetyValidator
  
  validator = SafetyValidator()
  with validator.check_context(data) as safe_data:
      process(safe_data)
  ```

## Configuration Updates

### Environment Variables
Add these new variables to your `.env`:
```bash
# Monitoring
PROMETHEUS_PORT=9090
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317

# State Management
POSTGRES_DSN=postgresql://user:pass@localhost:5432/zigral
REDIS_URL=redis://localhost:6379

# Task Management
MAX_CONCURRENT_TASKS=10
TASK_QUEUE_SIZE=1000
```

### Configuration File
Update your `config.json`:
```json
{
  "task_management": {
    "enabled": true,
    "default_priority": "normal"
  },
  "safety": {
    "strict_mode": true,
    "rate_limits": {
      "api_calls": 100,
      "file_operations": 50
    }
  },
  "monitoring": {
    "metrics_enabled": true,
    "tracing_enabled": true,
    "log_level": "INFO"
  }
}
```

## Breaking Changes

1. **API Changes**
   - `Agent.run()` is now deprecated, use `TaskManager.submit()`
   - `State.get()` now returns a context manager
   - All monitoring functions require structured logging

2. **Directory Structure**
   - Move custom actions to `src/actions/custom/`
   - Move state handlers to `src/state/handlers/`
   - Update import paths accordingly

3. **Dependencies**
   - Minimum Python version is now 3.11
   - New required services: Redis and PostgreSQL
   - Updated package versions in `requirements.txt`

## Deprecation Notices

The following features are deprecated and will be removed in 3.0:
- `DirectExecutor` class - use `TaskManager` instead
- `SimpleState` class - use `StateManager` instead
- Plain text logging - use structured logging
- Synchronous API calls - use async versions

## Rollback Procedure

If you need to rollback to a previous version:
1. Restore your old `.env` and `config.json`
2. Revert code changes
3. Reinstall previous dependencies
4. Stop new monitoring services

## Support

- Report migration issues on GitHub
- Join our Discord for migration support
- Check migration FAQs in the wiki

## Verification Steps

After migration, verify:
1. All tests pass with new architecture
2. Monitoring dashboards show data
3. State persistence works
4. Safety checks are active
5. Task queuing functions correctly

## Next Steps

1. Review the updated [README.md](README.md)
2. Check [TESTING.md](TESTING.md) for new testing requirements
3. Update your CI/CD pipeline
4. Monitor system performance 
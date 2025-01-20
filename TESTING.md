# Zigral Testing Guide

## Test Organization

### Directory Structure
```
zigral/tests/
  ├─ unit/              # Unit tests for individual components
  │  ├─ state/         # State management tests
  │  ├─ actions/       # Action execution tests
  │  ├─ safety/        # Safety mechanism tests
  │  └─ llm/           # Claude integration tests
  ├─ integration/       # Integration tests
  ├─ performance/       # Performance benchmarks
  └─ security/         # Security tests
```

## Test Categories

### Unit Tests
- Component-level testing
- Mocked dependencies
- Fast execution
- High coverage requirements (>90%)

### Integration Tests
- Cross-component functionality
- Real dependencies (when possible)
- End-to-end workflows
- API contract validation

### Performance Tests
- Response time benchmarks
- Resource usage monitoring
- Concurrency testing
- Load testing scenarios

### Security Tests
- Input validation
- Authentication/Authorization
- Rate limiting
- Resource constraints

## Running Tests

### Local Development
```bash
# Run all tests
pytest

# Run specific test category
pytest tests/unit/
pytest tests/integration/
pytest tests/performance/
pytest tests/security/

# Run with coverage
pytest --cov=src tests/

# Generate coverage report
coverage html
```

### CI/CD Pipeline
- Tests run on every PR
- Coverage reports generated
- Performance benchmarks compared
- Security scan results

## Test Writing Guidelines

### Unit Tests
1. One test file per source file
2. Use fixtures for common setup
3. Mock external dependencies
4. Test edge cases and errors

### Integration Tests
1. Focus on component interactions
2. Use test databases
3. Clean up resources after tests
4. Verify end-to-end workflows

### Performance Tests
1. Define baseline metrics
2. Use realistic data volumes
3. Monitor resource usage
4. Compare against benchmarks

### Security Tests
1. Test input validation
2. Verify access controls
3. Check rate limiting
4. Validate output sanitization

## Tools and Dependencies

- pytest: Test runner
- pytest-asyncio: Async test support
- pytest-cov: Coverage reporting
- pytest-mock: Mocking support
- pytest-timeout: Test timeouts
- pytest-xdist: Parallel testing
- coverage-badge: Coverage visualization 
# Cursor AI Development Guidelines

## Project Structure Rules

1. **File Organization**
   - Follow the exact directory structure defined in `instructions.md`
   - Place new files in appropriate directories based on functionality
   - Maintain separation of concerns between modules

2. **Code Style**
   - Use Python type hints consistently
   - Follow PEP 8 guidelines
   - Use async/await patterns for all I/O operations
   - Document all public methods and classes

3. **Dependencies**
   - Use only the versions specified in requirements.txt
   - Propose new dependencies with justification
   - Keep third-party dependencies minimal

## Implementation Guidelines

1. **Vision Processing**
   - Implement feature compression before UI detection
   - Cache processed features when possible
   - Use configurable confidence thresholds

2. **Action Execution**
   - Always implement human-like patterns
   - Include random delays and natural movements
   - Handle timeouts and retries gracefully

3. **Safety Mechanisms**
   - Validate all actions before execution
   - Implement emergency stop functionality
   - Maintain action history for rollbacks

4. **Claude Integration**
   - Use appropriate model for each task type
   - Implement proper rate limiting
   - Cache common responses
   - Handle API errors gracefully

## Development Process

1. **Before Implementation**
   - Check existing code for similar functionality
   - Review relevant sections in instructions.md
   - Verify dependencies are available

2. **During Implementation**
   - Add type hints and docstrings
   - Include error handling
   - Add logging statements
   - Write unit tests

3. **After Implementation**
   - Verify against test cases
   - Check performance metrics
   - Update documentation
   - Create checkpoints

## Error Handling

1. **Required Error Handlers**
   - Network failures
   - API rate limits
   - Browser automation errors
   - Vision processing failures
   - Invalid user input

2. **Logging Requirements**
   - Log all errors with context
   - Include timestamps
   - Track performance metrics
   - Maintain action history

## Testing Requirements

1. **Unit Tests**
   - Test each component in isolation
   - Mock external dependencies
   - Include edge cases
   - Verify error handling

2. **Integration Tests**
   - Test component interactions
   - Verify end-to-end workflows
   - Test performance under load
   - Validate rollback mechanisms

## Documentation Standards

1. **Code Documentation**
   ```python
   def function_name(param1: type, param2: type) -> return_type:
       """
       Brief description of function purpose.

       Args:
           param1: Description of param1
           param2: Description of param2

       Returns:
           Description of return value

       Raises:
           ErrorType: Description of error conditions
       """
   ```

2. **Class Documentation**
   ```python
   class ClassName:
       """
       Brief description of class purpose.

       Attributes:
           attr1: Description of attr1
           attr2: Description of attr2

       Methods:
           method1: Description of method1
           method2: Description of method2
       """
   ```

## Performance Guidelines

1. **Resource Usage**
   - Monitor memory consumption
   - Track CPU usage
   - Optimize network requests
   - Cache when appropriate

2. **Response Times**
   - Vision processing: < 500ms
   - Action execution: Natural timing
   - API responses: < 2000ms
   - UI updates: < 100ms

## Security Guidelines

1. **Data Handling**
   - Never store API keys in code
   - Use environment variables
   - Sanitize user input
   - Validate file paths

2. **Browser Automation**
   - Use secure browser contexts
   - Handle sensitive data carefully
   - Implement anti-detection measures
   - Clear session data appropriately

## Checkpoint Requirements

1. **When to Create Checkpoints**
   - Before complex operations
   - After successful feature implementations
   - Before state-changing actions
   - At user-defined intervals

2. **Checkpoint Data**
   - GUI state
   - Action history
   - Browser state
   - Configuration settings

## Version Control Guidelines

1. **Commit Messages**
   ```
   type(scope): description

   [optional body]

   [optional footer]
   ```
   Types: feat, fix, docs, style, refactor, test, chore

2. **Branch Strategy**
   - main: stable releases
   - develop: integration
   - feature/*: new features
   - fix/*: bug fixes

## Maintenance Rules

1. **Code Updates**
   - Keep dependencies updated
   - Remove unused code
   - Optimize performance bottlenecks
   - Update documentation

2. **Error Monitoring**
   - Track error frequencies
   - Monitor performance metrics
   - Update error handling
   - Improve recovery mechanisms 
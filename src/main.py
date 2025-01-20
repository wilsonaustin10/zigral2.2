import os
import asyncio
import logging
import signal
from dotenv import load_dotenv
from browser.browser_manager import BrowserManager
from actions.action_cache import ActionCache
from llm.claude_client import ClaudeClient
from task.executor import TaskExecutor
from config.config_manager import ConfigManager

# Configure logging
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def async_input(prompt: str) -> str:
    """Async wrapper for input()"""
    return await asyncio.get_event_loop().run_in_executor(None, input, prompt)

async def main():
    """Main entry point"""
    # Initialize components
    browser = None
    cache = None
    
    try:
        # Load environment variables
        load_dotenv()
        
        # Initialize components
        config = ConfigManager("config.json")
        browser = BrowserManager(config)
        if not await browser.initialize():
            logger.error("Failed to initialize browser")
            return
            
        cache = ActionCache()
        claude = ClaudeClient(api_key=os.getenv("ANTHROPIC_API_KEY"), config_manager=config)
        
        # Create task executor
        executor = TaskExecutor(browser, cache, claude)
        
        # Simple CLI interface
        print("Zigral LAM Agent Ready")
        print("Enter tasks or 'quit' to exit")
        
        while True:
            try:
                user_input = await async_input("> ")
                user_input = user_input.strip()
                
                if user_input.lower() in ['quit', 'exit']:
                    break
                    
                if user_input:
                    success = await executor.execute_request(user_input)
                    if success:
                        print("✓ Task completed successfully")
                    else:
                        print("✗ Task failed")
                        
            except asyncio.CancelledError:
                logger.info("Operation cancelled by user")
                continue
                
            except Exception as e:
                logger.error(f"Error processing request: {str(e)}")
                continue
                
    except KeyboardInterrupt:
        logger.info("Shutting down gracefully...")
        
    except Exception as e:
        logger.error(f"Application error: {str(e)}")
        
    finally:
        # Cleanup
        if browser:
            try:
                await browser.cleanup()
            except Exception as e:
                logger.error(f"Error during browser cleanup: {str(e)}")
                
        if cache:
            try:
                await cache.close()
            except Exception as e:
                logger.error(f"Error during cache cleanup: {str(e)}")

def handle_sigint(signum, frame):
    """Handle SIGINT signal"""
    logger.info("Received interrupt signal")
    raise KeyboardInterrupt()

if __name__ == "__main__":
    # Set up signal handler
    signal.signal(signal.SIGINT, handle_sigint)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass  # Exit gracefully 
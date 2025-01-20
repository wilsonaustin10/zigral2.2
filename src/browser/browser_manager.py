import logging
import asyncio
import json
import aiohttp
import subprocess
import time
import os
import traceback
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from datetime import datetime
import random
from src.actions.action_cache import Action
from typing import Optional, Dict, List

class BrowserManager:
    def __init__(self, config_manager=None):
        self.config = config_manager.config if config_manager else None
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self._is_creating_page = False  # Flag to track page creation state

    async def initialize(self) -> bool:
        try:
            logging.info("Starting Playwright")
            self.playwright = await async_playwright().start()
            logging.info("Playwright started successfully")

            logging.info("Launching browser")
            self.browser = await self.playwright.chromium.launch(
                headless=False,
                timeout=60000
            )
            if not self.browser:
                logging.error("Browser launch returned None")
                return False
            logging.info("Browser launched successfully")

            logging.info("Creating browser context")
            self.context = await self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                accept_downloads=True,
                ignore_https_errors=True  # Add this to handle SSL issues
            )
            if not self.context:
                logging.error("Browser context creation returned None")
                return False
            logging.info("Browser context created successfully")

            # Create page with immediate configuration
            try:
                logging.info("Starting page creation sequence")
                self._is_creating_page = True
                
                # Create and configure page immediately
            self.page = await self.context.new_page()
                if not self.page:
                    logging.error("context.new_page() returned None")
                    return False
                
                logging.debug(f"Page created successfully: {self.page}")
                
                # Configure page settings immediately
                logging.info("Configuring page settings")
                self.page.set_default_timeout(60000)  # No await needed
                self.page.set_default_navigation_timeout(60000)  # No await needed
                
                # Attach handlers
                logging.info("Attaching event handlers")
                self.page.on("dialog", self._handle_dialog)
                self.context.on("page", self._handle_new_page)
                
                logging.info("Page initialization completed successfully")
                return True

            except Exception as e:
                logging.error(f"Page creation/configuration failed: {str(e)}")
                logging.error(f"Error details:\n{traceback.format_exc()}")
                return False
            finally:
                self._is_creating_page = False
                
        except Exception as e:
            logging.error(f"Browser initialization failed: {str(e)}")
            logging.error(f"Initialization error details:\n{traceback.format_exc()}")
            await self.cleanup()
            return False 

    async def _handle_dialog(self, dialog) -> None:
        """Handle JavaScript dialogs (alert, confirm, prompt)"""
        try:
            dialog_type = dialog.type
            message = dialog.message
            logging.info(f"Handling {dialog_type} dialog: {message}")
            
            if dialog_type in ['alert', 'confirm']:
                await dialog.accept()
                logging.info(f"Accepted {dialog_type} dialog")
            elif dialog_type == 'prompt':
                await dialog.dismiss()
                logging.info(f"Dismissed {dialog_type} dialog")
            
        except Exception as e:
            logging.error(f"Dialog handling failed: {str(e)}")

    async def _handle_new_page(self, new_page) -> None:
        """Handle new pages/popups that open in new tabs"""
        # Skip handling if we're in the process of creating a page
        if self._is_creating_page:
            logging.debug("Ignoring new page event during page creation")
            return
            
        try:
            logging.info("New page/popup detected")
            
            # Wait for the page to load
            await new_page.wait_for_load_state('domcontentloaded')
            
            url = new_page.url
            title = await new_page.title()
            logging.info(f"New page loaded - URL: {url}, Title: {title}")
            
            # Close unwanted popups based on URL or title patterns
            if any(term in url.lower() or term in title.lower() for term in [
                'ad', 'popup', 'subscribe', 'newsletter', 'sign-up', 'registration'
            ]):
                logging.info(f"Closing unwanted popup: {url}")
                await new_page.close()
            else:
                # For wanted popups (e.g. login forms), keep them open
                logging.info(f"Keeping page open: {url}")
                
        except Exception as e:
            logging.error(f"New page handling failed: {str(e)}")
            try:
                await new_page.close()
            except:
                pass

    async def _handle_modal_popup(self) -> bool:
        """Handle modal/overlay popups within the current page"""
        try:
            # Common modal/overlay selectors
            modal_selectors = [
                'div[role="dialog"]',
                'div[class*="modal"]',
                'div[class*="popup"]',
                'div[class*="overlay"]',
                'div[id*="modal"]',
                'div[id*="popup"]'
            ]
            
            # Check for visible modals
            for selector in modal_selectors:
                try:
                    modal = self.page.locator(selector)
                    if await modal.count() > 0 and await modal.is_visible():
                        logging.info(f"Found modal popup: {selector}")
                        
                        # Try to find and click close button
                        close_selectors = [
                            'button[class*="close"]',
                            'i[class*="close"]',
                            'span[class*="close"]',
                            '[aria-label*="close" i]',
                            '[title*="close" i]',
                            'button:has-text("Close")',
                            'button:has-text("×")'
                        ]
                        
                        for close_selector in close_selectors:
                            try:
                                close_button = modal.locator(close_selector)
                                if await close_button.count() > 0 and await close_button.is_visible():
                                    await close_button.click(timeout=2000)
                                    logging.info(f"Closed modal using {close_selector}")
                                    await asyncio.sleep(0.5)  # Wait for animation
                                    return True
                            except Exception as e:
                                continue
                                
                        # If no close button found, try clicking outside
                        try:
                            await self.page.mouse.click(0, 0)
                            logging.info("Attempted to close modal by clicking outside")
                            await asyncio.sleep(0.5)
                            return True
                        except:
                            pass
                except:
                    continue
                    
            return False
            
        except Exception as e:
            logging.error(f"Modal popup handling failed: {str(e)}")
            return False
        
    async def _check_for_popup(self) -> bool:
        """Quick check if there's a popup present"""
        try:
            # Check for JavaScript dialogs (these are handled by event handler)
            
            # Check for modal/overlay popups
            if await self._handle_modal_popup():
                return True
                
            # Check for cookie/consent banners
            cookie_selectors = [
                '[id*="cookie-banner"]',
                '[class*="cookie-banner"]',
                '[id*="consent"]',
                '[class*="consent"]',
                'button:has-text("Accept Cookies")',
                'button:has-text("Accept All")'
            ]
            
            for selector in cookie_selectors:
                try:
                    banner = self.page.locator(selector)
                    if await banner.count() > 0 and await banner.is_visible():
                        await banner.click(timeout=2000)
                        logging.info(f"Closed cookie banner using {selector}")
                        return True
                except:
                    continue
                    
            return False
            
        except Exception as e:
            logging.debug(f"Error checking for popup: {str(e)}")
            return False

    async def get_active_page(self) -> dict:
        """Get the current state of the active page"""
        try:
            if not self.page:
                return self._get_empty_state()
                
            # Wait for page to be stable before capturing state
            try:
                await self.page.wait_for_load_state('domcontentloaded', timeout=5000)
            except Exception as e:
                logging.warning(f"Page load state wait failed: {str(e)}")
            
            # Get basic page info
            url = self.page.url  # Use direct property instead of evaluate
            title = await self.page.title()
            viewport = self.page.viewport_size
            
            # Get all visible elements with their properties
            elements = await self.page.evaluate("""() => {
                function getUniqueSelector(el) {
                    // Try ID first
                    if (el.id) {
                        return '#' + el.id;
                    }
                    
                    // Try name attribute
                    if (el.name) {
                        return `[name="${el.name}"]`;
                    }
                    
                    // Try specific attributes for common elements
                    if (el.type === 'text' || el.type === 'password' || el.type === 'email') {
                        return `input[type="${el.type}"]`;
                    }
                    
                    // Try aria-label
                    if (el.getAttribute('aria-label')) {
                        return `[aria-label="${el.getAttribute('aria-label')}"]`;
                    }
                    
                    // Try placeholder
                    if (el.placeholder) {
                        return `[placeholder="${el.placeholder}"]`;
                    }
                    
                    // Fallback to a more complex selector
                    let path = [];
                    while (el.nodeType === Node.ELEMENT_NODE) {
                        let selector = el.nodeName.toLowerCase();
                        if (el.className) {
                            selector += '.' + Array.from(el.classList).join('.');
                        }
                        path.unshift(selector);
                        el = el.parentNode;
                    }
                    return path.join(' > ');
                }
                
                const elements = document.querySelectorAll('button, input, a, select, [role="button"]');
                return Array.from(elements).map(el => {
                    const rect = el.getBoundingClientRect();
                    return {
                        tag: el.tagName.toLowerCase(),
                        type: el.type || '',
                        id: el.id || '',
                        name: el.name || '',
                        value: el.value || '',
                        text: el.textContent.trim(),
                        placeholder: el.placeholder || '',
                        href: el.href || '',
                        role: el.getAttribute('role') || '',
                        aria_label: el.getAttribute('aria-label') || '',
                        visible: rect.width > 0 && rect.height > 0,
                        selector: getUniqueSelector(el)
                    };
                }).filter(el => el.visible);
            }""")
            
            return {
                "url": url,
                "title": title,
                "viewport": viewport,
                "timestamp": datetime.now().isoformat(),
                "elements": elements or []  # Ensure elements is never null
            }
            
        except Exception as e:
            logging.error(f"Failed to get page state: {str(e)}")
            return self._get_empty_state()
            
    def _get_empty_state(self):
        """Return empty state structure"""
        return {
            "url": "",
            "title": "",
            "viewport": {"width": 1920, "height": 1080},
            "timestamp": "",
            "elements": []
        } 

    async def _scroll_to_element(self, selector: str, smooth: bool = True) -> bool:
        """Scroll to an element with natural behavior"""
        try:
            # First check if element exists and get its position
            element = await self.page.wait_for_selector(selector, state='attached', timeout=5000)
            if not element:
                return False
                
            # Get element position
            box = await element.bounding_box()
            if not box:
                return False
                
            # Current viewport scroll position
            scroll_pos = await self.page.evaluate('() => ({ x: window.scrollX, y: window.scrollY })')
            
            # Get viewport dimensions
            dimensions = await self._get_viewport_dimensions()
            if not dimensions:
                return False
                
            # Target position (aim for element to be in upper third of viewport)
            target_y = box['y'] - (dimensions['height'] / 3)
            
            if smooth:
                # Calculate number of steps for smooth scrolling
                distance = target_y - scroll_pos['y']
                steps = 12  # More steps = smoother scrolling
                
                for i in range(steps + 1):
                    # Easing function for more natural movement
                    progress = i / steps
                    ease = progress * (2 - progress)  # Ease out quad
                    
                    current_y = scroll_pos['y'] + (distance * ease)
                    
                    await self.page.evaluate(f'window.scrollTo({{top: {current_y}, behavior: "auto"}})')
                    await asyncio.sleep(random.uniform(0.03, 0.08))  # Random delay between steps
                    
            # Final scroll to ensure element is in view
            await element.scroll_into_view_if_needed()
            await asyncio.sleep(random.uniform(0.3, 0.7))  # Pause after scrolling
            
            return True
                
        except Exception as e:
            logging.error(f"Scroll to element failed: {str(e)}")
            return False 

    async def navigate(self, url: str) -> bool:
        """Navigate to a URL with preparatory actions during load"""
        try:
            if not self.page:
                logging.error("No page available for navigation")
                return False
            
            logging.info(f"Navigating to {url}")
            
            # Start navigation without waiting for load
            navigation_promise = self.page.goto(url, wait_until="commit", timeout=30000)
            
            # Brief wait for initial page commit
            await asyncio.sleep(0.2)
            
            # Perform preparatory actions during load
            try:
                # Use the dedicated methods for cursor movements and clicks
                await self._perform_cursor_movements()
                await asyncio.sleep(0.1)
                await self._perform_blank_clicks()
            except Exception as e:
                logging.debug(f"Preparatory actions during navigation failed: {str(e)}")
                # Continue with navigation even if prep actions fail
            
            # Wait for navigation to complete
            await navigation_promise
            
            # Brief wait for any immediate post-load events
            await asyncio.sleep(0.2)
            
            logging.info(f"Successfully navigated to {url}")
            return True
            
        except Exception as e:
            logging.error(f"Navigation failed: {str(e)}")
            return False

    async def _handle_investing_popups(self) -> None:
        """Handle popups specific to investing.com"""
        try:
            # Common cookie banner selectors for investing.com
            cookie_selectors = [
                "#onetrust-accept-btn-handler",
                "button.cookieConsentAccept",
                "[data-testid='banner-accept-button']",
                "#cookiebanner .accept-btn",
                ".cookie-notice-visible .accept",
                "[aria-label*='Accept'] button",
                "button:has-text('Accept')",
                "button:has-text('Accept All')",
                "button:has-text('I Accept')"
            ]

            # Try each selector with a short timeout
            for selector in cookie_selectors:
                try:
                    await self.page.click(selector, timeout=2000)
                    logging.info(f"Clicked cookie banner using selector: {selector}")
                    await asyncio.sleep(0.5)  # Brief pause for animation
                    break
                except Exception:
                    continue

            # Handle other common investing.com popups
            modal_selectors = [
                "button.popupCloseIcon",
                ".modal .close-btn",
                "[data-name='gam-ad-popup-close']",
                "div[class*='popup'] button[class*='close']"
            ]

            for selector in modal_selectors:
                try:
                    await self.page.click(selector, timeout=2000)
                    logging.info(f"Closed modal using selector: {selector}")
                    await asyncio.sleep(0.5)
                except Exception:
                    continue
                
        except Exception as e:
            logging.warning(f"Error handling investing.com popups: {str(e)}")

    async def _handle_generic_popups(self) -> None:
        """Handle generic popups and cookie banners"""
        try:
            # Common cookie banner patterns
            cookie_patterns = [
                {"text": ["accept", "cookies"], "role": "button"},
                {"text": ["agree", "continue"], "role": "button"},
                {"text": ["got it", "ok"], "role": "button"},
                {"id": ["cookie", "consent", "privacy"]},
                {"class": ["cookie", "consent", "privacy"]}
            ]

            # Try each pattern
            for pattern in cookie_patterns:
                try:
                    if "text" in pattern:
                        for text in pattern["text"]:
                            try:
                                button = self.page.get_by_role(pattern["role"], name=text, exact=False)
                                if await button.count() > 0:
                                    await button.click(timeout=2000)
                                    logging.info(f"Clicked cookie button with text: {text}")
                                    await asyncio.sleep(0.5)
                                    break
                            except Exception:
                                continue
                    elif "id" in pattern:
                        for id_part in pattern["id"]:
                            try:
                                await self.page.click(f"[id*='{id_part}'] button", timeout=2000)
                                logging.info(f"Clicked button in element with id containing: {id_part}")
                                await asyncio.sleep(0.5)
                                break
                            except Exception:
                                continue
                    elif "class" in pattern:
                        for class_part in pattern["class"]:
                            try:
                                await self.page.click(f"[class*='{class_part}'] button", timeout=2000)
                                logging.info(f"Clicked button in element with class containing: {class_part}")
                                await asyncio.sleep(0.5)
                                break
                            except Exception:
                                continue
                except Exception as e:
                    logging.debug(f"Failed to handle pattern {pattern}: {str(e)}")
                    continue

            # Handle any remaining modal dialogs
            await self._handle_modal_popup()
            
        except Exception as e:
            logging.warning(f"Error handling generic popups: {str(e)}")

    async def click(self, selector: str) -> bool:
        """Click on an element"""
        try:
            logging.info(f"Clicking element: {selector}")
            
            # Scroll element into view first
            await self._scroll_to_element(selector)
            
            # Use Playwright's locator API
            locator = self.page.locator(selector)
            
            # Wait for element to be visible and clickable
            await locator.wait_for(state='visible', timeout=5000)
            
            # Click with retry logic
            try:
                await locator.click(timeout=5000)
            except:
                # If normal click fails, try force click
                await locator.click(force=True)
                
            logging.info(f"Successfully clicked element: {selector}")
            return True
            
        except Exception as e:
            logging.error(f"Click failed on {selector}: {str(e)}")
            import traceback
            logging.error(traceback.format_exc())
            return False

    async def type(self, selector: str, text: str) -> bool:
        """Type text into an element"""
        try:
            logging.info(f"Typing '{text}' into element: {selector}")
            
            # Handle cookie banner and popups first
            try:
                # Common cookie accept button selectors
                cookie_selectors = [
                    "button:has-text('Accept All Cookies')",
                    "button:has-text('Accept')",
                    "button:has-text('I Accept')",
                    "[id*='cookie-accept']",
                    "[class*='cookie-accept']",
                    ".cc-btn.cc-accept-all"
                ]
                
                for cookie_selector in cookie_selectors:
                    try:
                        await self.page.click(cookie_selector, timeout=3000)
                        logging.info(f"Closed cookie banner using {cookie_selector}")
                        await asyncio.sleep(1)  # Wait for banner animation
                        break
                    except:
                        continue
            except Exception as e:
                logging.debug(f"Cookie banner handling failed: {str(e)}")
            
            # For investing.com, try multiple search input selectors
            if selector == "input.searchText":
                search_selectors = [
                    "input.searchText",
                    "#searchTextHeader",
                    "input[type='search']",
                    "input[placeholder*='Search']",
                    "[role='searchbox']"
                ]
                
                # Try each selector until we find one that works
                for search_selector in search_selectors:
                    try:
                        locator = self.page.locator(search_selector)
                        await locator.wait_for(state="visible", timeout=3000)
                        selector = search_selector  # Use the working selector
                        logging.info(f"Found search input using selector: {selector}")
                        break
                    except:
                        continue
            
            # Scroll element into view first
            await self._scroll_to_element(selector)
            
            # Use Playwright's locator API with increased timeout
            locator = self.page.locator(selector)
            
            # Wait for element to be visible and enabled
            await locator.wait_for(state="visible", timeout=10000)
            
            # Clear the field first
            await locator.clear()
            
            # Type with human-like delays
            await locator.type(text, delay=random.randint(50, 150))
            
            logging.info(f"Successfully typed into element: {selector}")
            return True
            
        except Exception as e:
            logging.error(f"Type failed on {selector}: {str(e)}")
            import traceback
            logging.error(traceback.format_exc())
            return False

    async def press(self, key: str) -> bool:
        """Press a keyboard key"""
        try:
            logging.info(f"Pressing key: {key}")
            
            # Handle Enter key specifically for forms
            if key.lower() == 'enter':
                # Wait for potential navigation
                async with self.page.expect_navigation(wait_until=['load', 'networkidle'], timeout=30000):
                    await self.page.keyboard.press(key)
                    
                # Handle any popups after navigation
                await self._handle_popups()
            else:
                await self.page.keyboard.press(key)
                
            logging.info(f"Successfully pressed key: {key}")
            return True
            
        except Exception as e:
            logging.error(f"Key press failed for {key}: {str(e)}")
            import traceback
            logging.error(traceback.format_exc())
            return False

    async def wait_for(self, selector: str = None, timeout: int = None) -> bool:
        """Wait for an element or timeout"""
        try:
            if selector:
                logging.info(f"Waiting for element: {selector}")
                
                # Use Playwright's locator API
                locator = self.page.locator(selector)
                
                # Wait for element to be visible
                await locator.wait_for(state='visible', timeout=timeout or 30000)
                
                logging.info(f"Successfully found element: {selector}")
            elif timeout:
                logging.info(f"Waiting for {timeout}ms")
                await asyncio.sleep(timeout / 1000)  # Convert ms to seconds
                logging.info("Wait completed")
            
            return True
            
        except Exception as e:
            if selector:
                logging.error(f"Wait failed for {selector}: {str(e)}")
            else:
                logging.error(f"Wait failed: {str(e)}")
            import traceback
            logging.error(traceback.format_exc())
            return False 

    async def execute_action(self, action: Action, index: int) -> bool:
        """Execute a browser action with improved error handling"""
        try:
            if not self.page:
                logging.error(f"Action {index} failed: No active page")
                return False

            logging.info(f"Executing action: {action}")
            
            if action.type == 'navigate':
                if not action.url:
                    logging.error("Navigate action missing URL")
                    return False
                logging.info(f"Navigating to {action.url}")
                try:
                    # Wait longer for investing.com and handle common popups
                    if "investing.com" in action.url:
                        await self.page.goto(action.url, wait_until='domcontentloaded', timeout=30000)
                        await asyncio.sleep(1)  # Brief pause for dynamic content
                        
                        # Handle cookie consent and popups
                        try:
                            # Common cookie accept buttons
                            cookie_buttons = [
                                "#onetrust-accept-btn-handler",
                                "[id*='cookie-accept']",
                                "button:has-text('Accept')",
                                "button:has-text('Accept All')"
                            ]
                            for selector in cookie_buttons:
                                try:
                                    await self.page.click(selector, timeout=2000)
                                    break
                                except:
                                    continue
                                    
                            # Close any popups
                            popup_close_buttons = [
                                "button.popupCloseIcon",
                                "[data-name='gam-ad-popup-close']",
                                "div[class*='popup'] button[class*='close']"
                            ]
                            for selector in popup_close_buttons:
                                try:
                                    await self.page.click(selector, timeout=2000)
                                except:
                                    continue
                        except Exception as e:
                            logging.warning(f"Error handling popups: {e}")
                            
                    else:
                        await self.page.goto(action.url, wait_until='domcontentloaded')
                        
                    logging.info(f"Successfully navigated to {action.url}")
                    return True
                except Exception as e:
                    logging.error(f"Navigation failed: {str(e)}")
                    return False
                    
            elif action.type == 'wait':
                if not action.selector:
                    logging.error(f"Action {index} failed: No selector provided for wait action")
                    return False
                    
                logging.info(f"Waiting for element: {action.selector}")
                locator = self.page.locator(action.selector)
                try:
                    # Increase default timeout to 30 seconds if none specified
                    await locator.wait_for(state='visible', timeout=action.timeout or 30000)
                    return True
                except Exception as e:
                    logging.error(f"Wait failed for {action.selector}: {str(e)}")
                    logging.error(f"Traceback:\n{traceback.format_exc()}")
                    return False
                    
            elif action.type == 'click':
                if not action.selector:
                    logging.error("Click action missing selector")
                    return False
                logging.info(f"Clicking element: {action.selector}")
                try:
                    await self.page.click(action.selector, timeout=action.timeout or 5000)
                    logging.info(f"Successfully clicked element: {action.selector}")
                    return True
                except Exception as e:
                    logging.error(f"Click failed for {action.selector}: {str(e)}")
                    return False
                    
            elif action.type == 'type':
                if not action.selector or not action.text:
                    logging.error("Type action missing selector or text")
                    return False
                logging.info(f"Typing into element: {action.selector}")
                try:
                    await self.page.fill(action.selector, action.text, timeout=action.timeout or 5000)
                    logging.info(f"Successfully typed into element: {action.selector}")
                    return True
                except Exception as e:
                    logging.error(f"Type failed for {action.selector}: {str(e)}")
                    return False
                    
            else:
                logging.error(f"Unknown action type: {action.type}")
                return False
                
        except Exception as e:
            logging.error(f"Action execution failed: {str(e)}")
            logging.error(f"Traceback:\n{traceback.format_exc()}")
            return False
            
    async def cleanup(self):
        """Clean up browser resources"""
        try:
            if self.page:
                await self.page.close()
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
            logging.info("Browser resources cleaned up successfully")
        except Exception as e:
            logging.error(f"Error during browser cleanup: {str(e)}")
            import traceback
            logging.error(traceback.format_exc()) 

    async def _perform_cursor_movements(self) -> None:
        """Move cursor around the page to trigger dynamic content"""
        try:
            if not self.page:
                return
            
            # Get viewport size using evaluate
            dimensions = await self._get_viewport_dimensions()
            if not dimensions:
                return
            
            width = dimensions['width']
            height = dimensions['height']
            
            # Define movement points
            points = [
                {'x': width // 4, 'y': height // 4},
                {'x': width * 3 // 4, 'y': height // 4},
                {'x': width // 2, 'y': height // 2},
                {'x': width // 4, 'y': height * 3 // 4},
                {'x': width * 3 // 4, 'y': height * 3 // 4}
            ]
            
            # Move to each point with small delay
            for point in points:
                await self.page.mouse.move(point['x'], point['y'])
                await asyncio.sleep(0.2)
            
        except Exception as e:
            logging.warning(f"Cursor movements failed: {str(e)}")

    async def _perform_blank_clicks(self) -> None:
        """Click in blank areas to trigger popups"""
        try:
            if not self.page:
                return
            
            # Get viewport size using evaluate
            dimensions = await self._get_viewport_dimensions()
            if not dimensions:
                return
            
            width = dimensions['width']
            height = dimensions['height']
            
            # Define click points (avoiding edges and center)
            click_points = [
                {'x': width // 4, 'y': height // 4},
                {'x': width * 3 // 4, 'y': height // 4},
                {'x': width // 4, 'y': height * 3 // 4},
                {'x': width * 3 // 4, 'y': height * 3 // 4}
            ]
            
            # Click each point with small delay
            for point in click_points:
                await self.page.mouse.click(point['x'], point['y'])
                await asyncio.sleep(0.2)
            
        except Exception as e:
            logging.warning(f"Blank clicks failed: {str(e)}")

    async def _execute_preparatory_actions(self) -> None:
        """Execute actions to prepare page state"""
        if not self.page:
            return
        
        # Add small delay after navigation
        await asyncio.sleep(0.5)
        
        # Perform cursor movements first
        await self._perform_cursor_movements()
        
        # Add small delay between movements and clicks
        await asyncio.sleep(0.5)
        
        # Perform blank clicks
        await self._perform_blank_clicks()
        
        # Final delay to allow popups to appear
        await asyncio.sleep(0.5) 

    async def _get_viewport_dimensions(self) -> Optional[Dict[str, int]]:
        """Safely get viewport dimensions using JavaScript evaluation"""
        try:
            if not self.page:
                return None
            
            # Use JavaScript to get viewport dimensions
            dimensions = await self.page.evaluate('''
                () => ({
                    width: Math.max(document.documentElement.clientWidth, window.innerWidth || 0),
                    height: Math.max(document.documentElement.clientHeight, window.innerHeight || 0)
                })
            ''')
            return dimensions
        except Exception as e:
            logging.debug(f"Failed to get viewport dimensions: {str(e)}")
            return None 

    def _get_investing_selectors(self) -> List[str]:
        """Return a list of reliable selectors for investing.com navigation."""
        return [
            'header',  # More general header element
            '.main-nav',  # Alternative nav class
            '#navMenu',  # Nav menu ID
            '.topBar',  # Top bar class
            '#fullColumn'  # Main content area
        ]

    async def execute_actions(self, actions: List[Action]) -> List[bool]:
        results = []
        for i, action in enumerate(actions):
            success = await self.execute_action(action, i)
            if action.type == 'wait' and not success:
                # Try alternative selectors for investing.com
                if 'investing.com' in self.page.url:
                    for selector in self._get_investing_selectors():
                        try:
                            logging.info(f"Trying alternative selector: {selector}")
                            await self.page.locator(selector).wait_for(state='visible', timeout=10000)
                            success = True
                            break
                        except Exception:
                            continue
            results.append(success)
        return results 
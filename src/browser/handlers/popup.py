from typing import List, Optional
import logging
import asyncio

class PopupHandler:
    def __init__(self, page):
        self.page = page
        
    async def handle_all_popups(self) -> bool:
        """Handle all types of popups"""
        try:
            handled = False
            handled |= await self._handle_modal_popups()
            handled |= await self._handle_cookie_banners()
            handled |= await self._handle_site_specific_popups()
            return handled
        except Exception as e:
            logging.error(f"Popup handling failed: {str(e)}")
            return False
            
    async def _handle_modal_popups(self) -> bool:
        """Handle modal/overlay popups"""
        modal_selectors = [
            'div[role="dialog"]',
            'div[class*="modal"]',
            'div[class*="popup"]',
            'div[class*="overlay"]',
            'div[id*="modal"]',
            'div[id*="popup"]'
        ]
        
        for selector in modal_selectors:
            try:
                modal = self.page.locator(selector)
                if await modal.count() > 0 and await modal.is_visible():
                    if await self._try_close_modal(modal):
                        return True
            except Exception:
                continue
        return False
        
    async def _handle_cookie_banners(self) -> bool:
        """Handle cookie consent banners"""
        cookie_selectors = [
            "#onetrust-accept-btn-handler",
            "[id*='cookie-accept']",
            "button:has-text('Accept')",
            "button:has-text('Accept All')",
            "[id*='cookie-banner']",
            "[class*='cookie-banner']",
            "[id*='consent']",
            "[class*='consent']"
        ]
        
        for selector in cookie_selectors:
            try:
                banner = self.page.locator(selector)
                if await banner.count() > 0 and await banner.is_visible():
                    await banner.click(timeout=2000)
                    logging.info(f"Closed cookie banner using {selector}")
                    return True
            except Exception:
                continue
        return False
        
    async def _handle_site_specific_popups(self) -> bool:
        """Handle known site-specific popups"""
        if "investing.com" in self.page.url:
            return await self._handle_investing_popups()
        return False
        
    async def _try_close_modal(self, modal) -> bool:
        """Try various methods to close a modal"""
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
                    await asyncio.sleep(0.5)
                    return True
            except Exception:
                continue
                
        # Try clicking outside
        try:
            await self.page.mouse.click(0, 0)
            logging.info("Attempted to close modal by clicking outside")
            await asyncio.sleep(0.5)
            return True
        except Exception:
            return False
            
    async def _handle_investing_popups(self) -> bool:
        """Handle investing.com specific popups"""
        investing_selectors = [
            "button.popupCloseIcon",
            ".modal .close-btn",
            "[data-name='gam-ad-popup-close']",
            "div[class*='popup'] button[class*='close']"
        ]
        
        for selector in investing_selectors:
            try:
                await self.page.click(selector, timeout=2000)
                logging.info(f"Closed investing.com popup using {selector}")
                await asyncio.sleep(0.5)
                return True
            except Exception:
                continue
        return False 
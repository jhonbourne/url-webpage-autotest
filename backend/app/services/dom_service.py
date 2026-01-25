import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from typing import Dict, Any, Optional, List


class DOMService:
    def __init__(self):
        self.browser = None
        self.playwright = None
    
    async def get_page_html(self, url: str, wait_for_selector: Optional[str] = None) -> str:
        """Get rendered HTML"""
        if not self.playwright:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch()
        
        page = await self.browser.new_page()
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            
            if wait_for_selector:
                await page.wait_for_selector(wait_for_selector, timeout=10000)
            
            # wait for dynamic content loading
            await asyncio.sleep(1)
            
            html = await page.content()
            return html
        finally:
            await page.close()
    
    async def extract_structure(self, html: str, 
                              include_text: bool = True,
                              include_attributes: List[str] = None) -> Dict[str, Any]:
        """Tool function for getting specific element in html"""
        soup = BeautifulSoup(html, 'html.parser')
        
        # remove scripts and styles
        for script in soup(["script", "style"]):
            script.decompose()
        
        # define a function for recursion in the DOM tree
        def element_to_dict(element) -> Dict[str, Any]:
            result = {
                "tag": element.name,
            }
            
            if include_attributes:
                result["attributes"] = {
                    attr: element.get(attr) 
                    for attr in include_attributes 
                    if element.get(attr)
                }
            
            if include_text and element.string:
                result["text"] = element.string.strip()
            
            children = [element_to_dict(child) for child in element.find_all(recursive=False)]
            if children:
                result["children"] = children
            
            return result
        
        # Extract content from body
        body = soup.find('body')
        if body:
            return element_to_dict(body)
        
        return {}
    
    @staticmethod
    def summarize_dom(self, structured_dom: Dict[str, Any],
                    n_item_truncate: int = 10) -> str:
        """Create a text summary of the DOM structure"""
        
        if not structured_dom:
            return "No DOM structure available"
        
        summary_parts = []
        
        # Extract key element information
        if isinstance(structured_dom, dict):
            for key, value in structured_dom.items():
                if key in ["buttons", "inputs", "links", "forms", "divs", "tables"]:
                    if isinstance(value, list) and value:
                        # Create a more readable summary
                        elements = []
                        for item in value[:n_item_truncate]:
                            if isinstance(item, dict):
                                elem_desc = self._describe_element(item)
                                elements.append(elem_desc)
                            else:
                                elements.append(str(item))
                        
                        summary_parts.append(f"{key.upper()}:\n" + "\n".join(f"  - {e}" for e in elements))
                
                elif key == "structure" and isinstance(value, str):
                    # Include HTML structure for reference
                    summary_parts.append(f"HTML STRUCTURE (first 2000 chars):\n{value[:2000]}")
        
        summary = "\n\n".join(summary_parts) if summary_parts else "DOM structure analyzed"
        return summary
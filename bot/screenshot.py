import base64
from playwright.async_api import Page


async def capturar_base64(page: Page) -> str:
   
    screenshot_bytes = await page.screenshot(full_page=False)
    return base64.b64encode(screenshot_bytes).decode("utf-8")
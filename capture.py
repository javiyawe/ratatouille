import asyncio
import os
from playwright.async_api import async_playwright

async def capture_screenshots():
    print("Capturing screenshots...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        
        # Helper to take screenshot
        async def take_shot(name, width, height):
            page = await browser.new_page(viewport={"width": width, "height": height})
            await page.goto("http://localhost:8000/recetario")
            # Wait for any dynamic rendering
            await asyncio.sleep(2)
            filepath = os.path.join("static", f"{name}.png")
            await page.screenshot(path=filepath, full_page=True)
            print(f"Saved {filepath}")
            await page.close()

        # Desktop
        await take_shot("real_pc", 1920, 1080)
        # iPad
        await take_shot("real_ipad", 810, 1080)
        # Mobile
        await take_shot("real_mobile", 390, 844)
        
        await browser.close()
    print("Done!")

if __name__ == "__main__":
    asyncio.run(capture_screenshots())

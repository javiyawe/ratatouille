import asyncio
import os
from playwright.async_api import async_playwright

async def capture_screenshots():
    print("Capturing specific use cases...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        
        async def take_scenario(name, width, height, setup_callback=None):
            page = await browser.new_page(viewport={"width": width, "height": height})
            await page.goto("http://localhost:8000/recetario")
            
            if setup_callback:
                await setup_callback(page)
            
            # Final wait for stability
            await asyncio.sleep(2)
            filepath = os.path.join("static", f"{name}.png")
            await page.screenshot(path=filepath, full_page=True)
            print(f"Saved {filepath}")
            await page.close()

        # Scenario 1: Clean Home
        await take_scenario("real_pc_home", 1920, 1080)
        
        # Scenario 2: Active Chat / Interaction
        async def setup_chat(page):
            try:
                # Open chat first
                await page.click("#layoutChatBtn")
                await asyncio.sleep(1)
                await page.fill("textarea#chatInput", "¡Hola Chef! Tengo pechuga de pollo, un poco de nata y champiñones. ¿Qué puedo hacer que sea espectacular?")
                await page.click("#sendChat")
                # Wait for the AI to stream response (up to 8 seconds)
                await asyncio.sleep(8)
            except Exception as e:
                print(f"Could not interact with chat: {e}")
        
        await take_scenario("real_pc_chat", 1920, 1080, setup_chat)
        
        # Scenario 3: Recipe extraction Modal
        async def setup_extract(page):
            try:
                await page.click("#addRecipeBtn")
                await asyncio.sleep(1)
                await page.fill("#rawRecipeText", "Para hacer una tarta de manzana perfecta necesitas:\n- 4 manzanas\n- 1 masa quebrada\n- Azúcar\n- Canela\n\nPela y corta las manzanas, mézclalas con el azúcar y la canela. Ponlas sobre la masa en un molde y hornea a 180 grados durante 45 minutos.")
                await page.click("#extractBtn")
                await asyncio.sleep(8)
            except Exception as e:
                print(f"Could not interact with extract: {e}")
            
        await take_scenario("real_pc_extract", 1920, 1080, setup_extract)

        await browser.close()
    print("Done!")

if __name__ == "__main__":
    asyncio.run(capture_screenshots())

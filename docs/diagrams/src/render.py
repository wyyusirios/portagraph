"""Рендер SVG/HTML в PNG через Chromium (Playwright)."""
import sys, asyncio, pathlib
from playwright.async_api import async_playwright
EXE = "/opt/pw-browsers/chromium-1243/chrome-linux64/chrome"

async def shot(src, out, selector="svg", scale=2):
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path=EXE)
        pg = await b.new_page(device_scale_factor=scale, viewport={"width": 1800, "height": 1200})
        await pg.goto(pathlib.Path(src).resolve().as_uri())
        await pg.wait_for_timeout(300)
        await pg.locator(selector).first.screenshot(path=out, omit_background=False)
        await b.close()

if __name__ == "__main__":
    asyncio.run(shot(sys.argv[1], sys.argv[2], *(sys.argv[3:4] or ["svg"])))

import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 390, "height": 844},
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)"
        )
        page = await context.new_page()

        # Collect console messages
        console_logs = []
        page.on("console", lambda msg: console_logs.append(f"[{msg.type}] {msg.text}"))

        # Collect page errors
        page_errors = []
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))

        # Navigate
        print("=== NAVIGATING ===")
        try:
            response = await page.goto("http://127.0.0.1:5173/", wait_until="networkidle", timeout=15000)
            print(f"Status: {response.status if response else 'no response'}")
        except Exception as e:
            print(f"Navigation error: {e}")

        # Wait a bit for React to render
        await page.wait_for_timeout(3000)

        # Take screenshot
        await page.screenshot(path="e2e_screenshot.png", full_page=True)
        print("=== SCREENSHOT SAVED: e2e_screenshot.png ===")

        # Get page title
        title = await page.title()
        print(f"Page title: {title}")

        # Get visible text content
        body_text = await page.inner_text("body")
        print(f"\n=== VISIBLE TEXT (first 800 chars) ===\n{body_text[:800]}")

        # Check for specific elements
        print("\n=== ELEMENT CHECK ===")
        selectors = [
            ("loading-screen", "[class*='loading'], [class*='Loading'], [class*='loader'], [class*='spinner']"),
            ("error-screen", "[class*='error'], [class*='Error']"),
            ("onboarding-screen", "[class*='onboard'], [class*='Onboard'], [class*='welcome']"),
            ("vpn-screen", "[class*='vpn'], [class*='Vpn'], [class*='VPN']"),
            ("retry-button", "button:has-text('Повторить'), button:has-text('Retry'), button:has-text('повторить')"),
            ("main-app", "#root, #app, [class*='app'], [class*='App']"),
        ]
        for name, sel in selectors:
            try:
                el = page.locator(sel).first
                visible = await el.is_visible(timeout=1000)
                text = ""
                if visible:
                    text = await el.inner_text()[:100]
                print(f"  {name}: {'FOUND' if visible else 'not visible'} {('text=' + text) if text else ''}")
            except Exception:
                print(f"  {name}: not found")

        # Get full HTML
        html = await page.content()
        print(f"\n=== HTML LENGTH: {len(html)} chars ===")
        print(f"HTML snippet:\n{html[:2000]}")

        # Console logs
        print(f"\n=== CONSOLE LOGS ({len(console_logs)}) ===")
        for log in console_logs[:20]:
            print(f"  {log}")

        # Page errors
        print(f"\n=== PAGE ERRORS ({len(page_errors)}) ===")
        for err in page_errors:
            print(f"  {err}")

        # Try clicking retry button if visible
        retry_btn = page.locator("button:has-text('Повторить'), button:has-text('повторить'), button:has-text('Retry')")
        if await retry_btn.count() > 0:
            print("\n=== CLICKING RETRY BUTTON ===")
            await retry_btn.first.click()
            await page.wait_for_timeout(2000)
            await page.screenshot(path="e2e_screenshot_after_retry.png", full_page=True)
            print("After-retry screenshot saved")
            body_text2 = await page.inner_text("body")
            print(f"Text after retry: {body_text2[:300]}")

        await browser.close()
        print("\n=== DONE ===")

asyncio.run(main())

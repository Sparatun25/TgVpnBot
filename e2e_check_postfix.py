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
        page.on("console", lambda msg: console_logs.append({"type": msg.type, "text": msg.text}))

        # Collect page errors
        page_errors = []
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))

        # Navigate
        print("=== NAVIGATING to http://127.0.0.1:5173/ ===")
        try:
            response = await page.goto("http://127.0.0.1:5173/", wait_until="networkidle", timeout=15000)
            print(f"HTTP status: {response.status if response else 'no response'}")
        except Exception as e:
            print(f"Navigation error: {e}")

        # Wait 3 seconds for full React render + Telegram SDK
        await page.wait_for_timeout(3000)

        # ===== CHECK 1: console errors about integrity =====
        print("\n=== INTEGRITY ERROR CHECK ===")
        integrity_errors = []
        for log in console_logs:
            text_lower = log["text"].lower()
            if "integrity" in text_lower and ("invalid" in text_lower or "fail" in text_lower or "error" in text_lower or "mismatch" in text_lower):
                integrity_errors.append(log)
        if integrity_errors:
            print(f"  INTEGRITY ERRORS FOUND: {len(integrity_errors)}")
            for e in integrity_errors:
                print(f"    [{e['type']}] {e['text']}")
        else:
            print("  No integrity errors detected.")

        # Also check if the broken sha384 string appears anywhere in logs
        broken_hash = "sha384-6QmQnCh8B9cDJxgGfKz9S+OQ3E5gT5gGfKz9S+OQ3E5gT5g"
        hash_in_logs = any(broken_hash in log["text"] for log in console_logs)
        print(f"  Broken hash in console logs: {hash_in_logs}")

        # ===== CHECK 2: window.Telegram.WebApp availability =====
        print("\n=== TELEGRAM WEBAPP SDK CHECK ===")
        tg_type = await page.evaluate('typeof window.Telegram?.WebApp')
        tg_webapp = await page.evaluate('window.Telegram?.WebApp?.initData ?? "(no initData)"')
        tg_version = await page.evaluate('window.Telegram?.WebApp?.version ?? "(no version)"')
        tg_platform = await page.evaluate('window.Telegram?.WebApp?.platform ?? "(no platform)"')
        print(f"  typeof window.Telegram?.WebApp = '{tg_type}'")
        print(f"  WebApp.version = {tg_version}")
        print(f"  WebApp.platform = {tg_platform}")
        print(f"  initData (first 60) = {str(tg_webapp)[:60]}")

        sdk_loaded = await page.evaluate('''(() => {
            const s = document.querySelector('script[src*="telegram-web-app.js"]');
            return s ? { found: true, src: s.src, hasIntegrity: s.hasAttribute('integrity') } : { found: false };
        })()''')
        print(f"  SDK script tag: {sdk_loaded}")

        # ===== CHECK 3: screenshot =====
        await page.screenshot(path="e2e_postfix_screenshot.png", full_page=True)
        print("\n=== SCREENSHOT: e2e_postfix_screenshot.png ===")

        # ===== CHECK 4: #root content =====
        root_html = await page.evaluate('document.getElementById("root")?.innerHTML ?? "<root not found>"')
        root_text = await page.evaluate('document.getElementById("root")?.innerText?.slice(0, 400) ?? ""')
        print(f"\n=== #root innerHTML (first 1200 chars) ===\n{root_html[:1200]}")
        print(f"\n=== #root visible text (first 400 chars) ===\n{root_text}")

        # ===== CHECK 5: all console logs =====
        print(f"\n=== ALL CONSOLE LOGS ({len(console_logs)}) ===")
        for log in console_logs[:30]:
            print(f"  [{log['type']}] {log['text'][:200]}")

        # ===== CHECK 6: page errors =====
        print(f"\n=== PAGE ERRORS ({len(page_errors)}) ===")
        for err in page_errors:
            print(f"  {err[:200]}")

        # ===== VERDICT =====
        print("\n" + "="*50)
        print("=== VERDICT ===")
        integrity_bug_fixed = len(integrity_errors) == 0 and not hash_in_logs
        sdk_available = tg_type == "object"
        print(f"  Integrity bug fixed: {integrity_bug_fixed}")
        print(f"  window.Telegram.WebApp available: {sdk_available}")
        print(f"  #root has content: {len(root_html) > 10}")
        if integrity_bug_fixed and sdk_available:
            print("  >>> PASS: Fix is working correctly.")
        else:
            print("  >>> FAIL: Fix is not working.")
        print("="*50)

        await browser.close()

asyncio.run(main())

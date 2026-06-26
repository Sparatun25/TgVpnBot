"""Detailed test - listen to all errors and dump full state."""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

PROJECT_ROOT = Path(__file__).resolve().parent

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 390, "height": 844})

        async def block_tg_sdk(route):
            if "telegram-web-app.js" in route.request.url:
                await route.abort()
            else:
                await route.continue_()
        await context.route("**/*", block_tg_sdk)

        await context.add_init_script("""
        window.Telegram = {
          WebApp: {
            initData: 'test_init_data_123',
            initDataUnsafe: { user: { id: 888888, first_name: 'Test' } },
            ready: function() {},
            expand: function() {},
            MainButton: {
              _text: '', _shown: false, _active: true, _progress: false, _cb: null,
              text: '', color: '#7C3AED', textColor: '#FFFFFF',
              setText: function(t) { this._text = t; this.text = t; window.__mainButtonText = t; },
              show: function() { this._shown = true; window.__mainButtonShown = true; },
              hide: function() { this._shown = false; window.__mainButtonShown = false; },
              enable: function() { this._active = true; },
              disable: function() { this._active = false; },
              showProgress: function() { this._progress = true; },
              hideProgress: function() { this._progress = false; },
              onClick: function(cb) { this._cb = cb; window.__mainButtonCallback = cb; },
              offClick: function(cb) { this._cb = null; window.__mainButtonCallback = null; }
            },
            BackButton: { show: () => {}, hide: () => {}, onClick: () => {}, offClick: () => {} },
            HapticFeedback: { impactOccurred: () => {}, notificationOccurred: () => {}, selectionChanged: () => {} },
            themeParams: { bg_color: '#0B0B0C', text_color: '#FFFFFF', hint_color: '#8E8E93', link_color: '#7C3AED', button_color: '#7C3AED', button_text_color: '#FFFFFF', secondary_bg_color: '#1C1C1E' },
            colorScheme: 'dark',
            openLink: () => {},
            openTelegramLink: () => {},
            onEvent: () => {},
            offEvent: () => {}
          }
        };
        """)

        page = await context.new_page()

        console_msgs = []
        page_errors = []
        page.on("console", lambda msg: console_msgs.append(f"[{msg.type}] {msg.text}"))
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))

        await page.goto("http://127.0.0.1:5173/", wait_until="domcontentloaded")
        await asyncio.sleep(5)  # Wait longer

        result = await page.evaluate("""
            ({
                initDataLen: window.Telegram?.WebApp?.initData?.length || 0,
                rootChildren: document.getElementById('root')?.children?.length || 0,
                rootFirstChildClass: document.getElementById('root')?.firstElementChild?.className || 'none',
                bodyText: document.body.innerText.substring(0, 500),
                loadingScreen: !!document.querySelector('.loading-screen'),
                errorScreen: !!document.querySelector('.error-screen'),
                welcomeScreen: !!document.querySelector('.welcome-screen'),
                onboardingScreen: !!document.querySelector('.onboarding-screen'),
                allDivs: Array.from(document.querySelectorAll('div')).map(d => d.className).filter(c => c).slice(0, 20)
            })
        """)

        with open(PROJECT_ROOT / "debug_output.txt", "w", encoding="utf-8") as f:
            f.write(f"initDataLen: {result['initDataLen']}\n")
            f.write(f"root children count: {result['rootChildren']}\n")
            f.write(f"root first child class: {result['rootFirstChildClass']}\n")
            f.write(f"loadingScreen: {result['loadingScreen']}\n")
            f.write(f"errorScreen: {result['errorScreen']}\n")
            f.write(f"welcomeScreen: {result['welcomeScreen']}\n")
            f.write(f"onboardingScreen: {result['onboardingScreen']}\n")
            f.write(f"\n=== BODY TEXT ===\n{result['bodyText']}\n")
            f.write(f"\n=== ALL DIVS ===\n{result['allDivs']}\n")
            f.write(f"\n=== CONSOLE ({len(console_msgs)}) ===\n")
            for m in console_msgs:
                f.write(f"{m}\n")
            f.write(f"\n=== PAGE ERRORS ({len(page_errors)}) ===\n")
            for e in page_errors:
                f.write(f"{e}\n")

        print(f"root children: {result['rootChildren']}, firstChild class: {result['rootFirstChildClass']!r}")
        print(f"loadingScreen: {result['loadingScreen']}, errorScreen: {result['errorScreen']}")
        print(f"welcomeScreen: {result['welcomeScreen']}, onboardingScreen: {result['onboardingScreen']}")
        print(f"console: {len(console_msgs)}, errors: {len(page_errors)}")
        for e in page_errors[:5]:
            print(f"  ERROR: {e[:300]}")

        await browser.close()

asyncio.run(main())

"""Quick test to dump exact error message."""
import asyncio
import sys
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

        # Простой мок только с initData
        await context.add_init_script("""
        window.Telegram = {
          WebApp: {
            initData: 'test_init_data_123',
            initDataUnsafe: { user: { id: 888888, first_name: 'Test' } },
            ready: function() {},
            expand: function() {},
            MainButton: { setText: () => {}, show: () => {}, hide: () => {}, onClick: () => {}, offClick: () => {} },
            BackButton: { show: () => {}, hide: () => {}, onClick: () => {}, offClick: () => {} },
            HapticFeedback: { impactOccurred: () => {}, notificationOccurred: () => {} },
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
        await page.goto("http://127.0.0.1:5173/", wait_until="domcontentloaded")
        await asyncio.sleep(3)

        # Получаем точный текст ошибки
        result = await page.evaluate("""
            ({
                initDataLen: window.Telegram?.WebApp?.initData?.length || 0,
                errorText: document.querySelector('.error-text')?.innerText || 'no error',
                errorScreenExists: !!document.querySelector('.error-screen'),
                loadingScreenExists: !!document.querySelector('.loading-screen'),
                bodyHTML: document.body.innerHTML.substring(0, 2000)
            })
        """)

        # Записываем в файл в UTF-8 чтобы прочитать без mojibake
        with open(PROJECT_ROOT / "debug_output.txt", "w", encoding="utf-8") as f:
            f.write(f"initDataLen: {result['initDataLen']}\n")
            f.write(f"errorScreenExists: {result['errorScreenExists']}\n")
            f.write(f"loadingScreenExists: {result['loadingScreenExists']}\n")
            f.write(f"\n=== ERROR TEXT ===\n{result['errorText']}\n")
            f.write(f"\n=== BODY HTML (first 2000) ===\n{result['bodyHTML']}\n")

        print(f"initDataLen: {result['initDataLen']}")
        print(f"errorScreen: {result['errorScreenExists']}")
        print(f"loadingScreen: {result['loadingScreenExists']}")
        print(f"errorText: {result['errorText'][:200]}")
        print("Full dump saved to debug_output.txt")

        await browser.close()

asyncio.run(main())

"""Full onboarding E2E - no .env read, uses fake initData for mock.
Tests UI rendering and button interactions, not real API.
"""
import asyncio
import sys
from pathlib import Path
from playwright.async_api import async_playwright

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

PROJECT_ROOT = Path(__file__).resolve().parent
FRONTEND_URL = "http://127.0.0.1:5173/"
SCREENSHOTS_DIR = PROJECT_ROOT / "e2e_screenshots"
SCREENSHOTS_DIR.mkdir(exist_ok=True)

# Полный мок Telegram.WebApp со всеми методами, которые вызывают хуки приложения
TELEGRAM_MOCK = """
window.__mainButtonText = '';
window.__mainButtonShown = false;
window.__mainButtonCallback = null;
window.__backButtonCallback = null;
window.Telegram = {
  WebApp: {
    initData: 'test_init_data_123',
    initDataUnsafe: {
      user: { id: 888888, first_name: 'Test', username: 'test_user', language_code: 'ru' },
      query_id: 'test_query',
      auth_date: Math.floor(Date.now() / 1000)
    },
    version: '6.0',
    platform: 'web',
    colorScheme: 'dark',
    themeParams: {
      bg_color: '#0B0B0C',
      text_color: '#FFFFFF',
      hint_color: '#8E8E93',
      link_color: '#7C3AED',
      button_color: '#7C3AED',
      button_text_color: '#FFFFFF',
      secondary_bg_color: '#1C1C1E'
    },
    ready: function() {},
    expand: function() {},
    close: function() {},
    MainButton: {
      _text: '', _shown: false, _active: true, _progress: false, _cb: null,
      text: '', color: '#7C3AED', textColor: '#FFFFFF', isVisible: false, isActive: true, isProgressVisible: false,
      setText: function(t) { this._text = t; this.text = t; window.__mainButtonText = t; },
      show: function() { this._shown = true; this.isVisible = true; window.__mainButtonShown = true; },
      hide: function() { this._shown = false; this.isVisible = false; window.__mainButtonShown = false; },
      enable: function() { this._active = true; this.isActive = true; },
      disable: function() { this._active = false; this.isActive = false; },
      showProgress: function(leaveActive) { this._progress = true; this.isProgressVisible = true; },
      hideProgress: function() { this._progress = false; this.isProgressVisible = false; },
      onClick: function(cb) { this._cb = cb; window.__mainButtonCallback = cb; },
      offClick: function(cb) { this._cb = null; window.__mainButtonCallback = null; }
    },
    BackButton: {
      isVisible: false,
      show: function() { this.isVisible = true; },
      hide: function() { this.isVisible = false; },
      onClick: function(cb) { window.__backButtonCallback = cb; },
      offClick: function(cb) { window.__backButtonCallback = null; }
    },
    HapticFeedback: {
      impactOccurred: function() {},
      notificationOccurred: function() {},
      selectionChanged: function() {}
    },
    openLink: function(url) { window.open(url, '_blank'); },
    openTelegramLink: function(url) { window.open(url, '_blank'); },
    onEvent: function() {},
    offEvent: function() {}
  }
};
"""


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 390, "height": 844},
            device_scale_factor=2,
        )

        async def block_tg_sdk(route):
            if "telegram-web-app.js" in route.request.url:
                await route.abort()
            else:
                await route.continue_()

        # Регистрируем более специфичный обработчик ПОСЛЕДНИМ — в Playwright
        # последний зарегистрированный handler вызывается первым.
        await context.route("**/*", block_tg_sdk)

        # Мок API: возвращаем профиль без активной подписки и без триала,
        # чтобы App.tsx не падал в error-state и показывал онбординг.
        async def mock_api(route):
            url = route.request.url
            if "/api/profile" in url:
                await route.fulfill(
                    status=200,
                    content_type="application/json",
                    body='{"subscription":{"active":false,"expires_at":null,"plan_type":null,"connection_url":null},"has_used_trial":false,"balance":0,"referral_code":"ONYXTEST","referral_count":0}'
                )
            elif "/api/subscription/trial" in url:
                await route.fulfill(
                    status=200,
                    content_type="application/json",
                    body='{"subscription":{"active":true,"expires_at":"2026-06-29T00:00:00Z","plan_type":"trial","connection_url":"vpn://test"},"has_used_trial":true,"balance":0,"referral_code":"ONYXTEST","referral_count":0}'
                )
            else:
                await route.continue_()

        await context.route("**/api/**", mock_api)

        await context.add_init_script(TELEGRAM_MOCK)

        page = await context.new_page()

        page_errors = []
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))

        print("[step] Открываю Mini App...")
        await page.goto(FRONTEND_URL, wait_until="domcontentloaded", timeout=15000)

        # Ждём пока React отрендерит
        for i in range(10):
            await asyncio.sleep(1)
            has_app = await page.evaluate("document.querySelector('.app') !== null")
            if has_app:
                print(f"[wait] App отрендерилась через {i+1}с")
                break

        # === STEP 1: WelcomeScreen ===
        await page.screenshot(path=str(SCREENSHOTS_DIR / "01_welcome.png"))
        text = await page.evaluate("document.body.innerText")
        print(f"\n[01 Welcome] {text[:300].replace(chr(10), ' | ')}")

        mb = await page.evaluate("({text: window.__mainButtonText, shown: window.__mainButtonShown})")
        print(f"[01 Welcome] MainButton: text={mb['text']!r}, shown={mb['shown']}")

        # Click MainButton → InstallScreen
        clicked = await page.evaluate("window.__mainButtonCallback && window.__mainButtonCallback()")
        await asyncio.sleep(2)

        # === STEP 2: InstallScreen ===
        await page.screenshot(path=str(SCREENSHOTS_DIR / "02_install.png"))
        text = await page.evaluate("document.body.innerText")
        print(f"\n[02 Install] {text[:300].replace(chr(10), ' | ')}")

        mb = await page.evaluate("({text: window.__mainButtonText, shown: window.__mainButtonShown})")
        print(f"[02 Install] MainButton: text={mb['text']!r}, shown={mb['shown']}")

        # Click MainButton → PreparingScreen
        clicked = await page.evaluate("window.__mainButtonCallback && window.__mainButtonCallback()")
        await asyncio.sleep(2)

        # === STEP 3: PreparingScreen ===
        await page.screenshot(path=str(SCREENSHOTS_DIR / "03_preparing.png"))
        text = await page.evaluate("document.body.innerText")
        print(f"\n[03 Preparing] {text[:300].replace(chr(10), ' | ')}")

        mb = await page.evaluate("({text: window.__mainButtonText, shown: window.__mainButtonShown})")
        print(f"[03 Preparing] MainButton: text={mb['text']!r}, shown={mb['shown']}")

        # === STEP 4: ConnectScreen ===
        clicked = await page.evaluate("window.__mainButtonCallback && window.__mainButtonCallback()")
        await asyncio.sleep(2)

        await page.screenshot(path=str(SCREENSHOTS_DIR / "04_connect.png"))
        text = await page.evaluate("document.body.innerText")
        print(f"\n[04 Connect] {text[:300].replace(chr(10), ' | ')}")

        # === STEP 5: Back to start, then dashboard test ===
        # Reload to skip onboarding (clear localStorage first)
        await page.evaluate("localStorage.removeItem('onboarding_step')")
        await page.reload()
        await asyncio.sleep(3)

        await page.screenshot(path=str(SCREENSHOTS_DIR / "05_dashboard.png"))
        text = await page.evaluate("document.body.innerText")
        print(f"\n[05 Dashboard] {text[:300].replace(chr(10), ' | ')}")

        # === Summary ===
        print(f"\n[stats] Page errors: {len(page_errors)}")
        for e in page_errors[:5]:
            print(f"  - {e[:200]}")

        print(f"\n[shots] Saved to {SCREENSHOTS_DIR}/")
        for s in sorted(SCREENSHOTS_DIR.glob("*.png")):
            print(f"  - {s.name} ({s.stat().st_size} bytes)")

        await browser.close()


asyncio.run(main())

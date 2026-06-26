"""Full E2E test for OnyxVpn Mini App onboarding flow."""
import asyncio
import hashlib
import hmac
import json
import sys
import time
import urllib.parse
from pathlib import Path

# Принудительно UTF-8 для stdout, иначе Windows cp1251 падает на эмодзи
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from dotenv import dotenv_values
from playwright.async_api import async_playwright

PROJECT_ROOT = Path(__file__).resolve().parent
FRONTEND_URL = "http://127.0.0.1:5173/"
SCREENSHOTS_DIR = PROJECT_ROOT / "e2e_screenshots"
SCREENSHOTS_DIR.mkdir(exist_ok=True)

TEST_USER_ID = 888888
TEST_USERNAME = "test_user"


def generate_init_data(bot_token: str, user_id: int, username: str) -> str:
    user_dict = {
        "id": user_id,
        "first_name": "Test",
        "username": username,
        "language_code": "ru",
        "is_premium": False,
    }
    user_json = json.dumps(user_dict, separators=(",", ":"))
    params = {
        "user": user_json,
        "auth_date": str(int(time.time())),
        "query_id": "test_query",
    }
    data_check_parts = [f"{k}={v}" for k, v in sorted(params.items())]
    data_check_string = "\n".join(data_check_parts)
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    hash_value = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    params["hash"] = hash_value
    return urllib.parse.urlencode(params)


def build_telegram_mock(init_data: str, user_id: int, username: str) -> str:
    """Полный мок Telegram.WebApp со всеми методами, которые вызывают хуки приложения."""
    return f"""
    window.__mainButtonText = '';
    window.__mainButtonShown = false;
    window.__mainButtonCallback = null;
    window.__backButtonCallback = null;
    window.Telegram = {{
      WebApp: {{
        initData: {json.dumps(init_data)},
        initDataUnsafe: {{
          user: {{
            id: {user_id},
            first_name: "Test",
            username: "{username}",
            language_code: "ru"
          }},
          query_id: "test_query",
          auth_date: {int(time.time())}
        }},
        version: "6.0",
        platform: "web",
        colorScheme: "dark",
        themeParams: {{
          bg_color: "#0B0B0C",
          text_color: "#FFFFFF",
          hint_color: "#8E8E93",
          link_color: "#7C3AED",
          button_color: "#7C3AED",
          button_text_color: "#FFFFFF",
          secondary_bg_color: "#1C1C1E"
        }},
        ready: function() {{}},
        expand: function() {{}},
        close: function() {{}},
        MainButton: {{
          _text: '', _shown: false, _active: true, _progress: false, _cb: null,
          text: '', color: '#7C3AED', textColor: '#FFFFFF', isVisible: false, isActive: true, isProgressVisible: false,
          setText: function(t) {{ this._text = t; this.text = t; window.__mainButtonText = t; }},
          show: function() {{ this._shown = true; this.isVisible = true; window.__mainButtonShown = true; }},
          hide: function() {{ this._shown = false; this.isVisible = false; window.__mainButtonShown = false; }},
          enable: function() {{ this._active = true; this.isActive = true; }},
          disable: function() {{ this._active = false; this.isActive = false; }},
          showProgress: function(leaveActive) {{ this._progress = true; this.isProgressVisible = true; }},
          hideProgress: function() {{ this._progress = false; this.isProgressVisible = false; }},
          onClick: function(cb) {{ this._cb = cb; window.__mainButtonCallback = cb; }},
          offClick: function(cb) {{ this._cb = null; window.__mainButtonCallback = null; }}
        }},
        BackButton: {{
          isVisible: false,
          show: function() {{ this.isVisible = true; }},
          hide: function() {{ this.isVisible = false; }},
          onClick: function(cb) {{ window.__backButtonCallback = cb; }},
          offClick: function(cb) {{ window.__backButtonCallback = null; }}
        }},
        HapticFeedback: {{
          impactOccurred: function() {{}},
          notificationOccurred: function() {{}},
          selectionChanged: function() {{}}
        }},
        openLink: function(url) {{ window.open(url, '_blank'); }},
        openTelegramLink: function(url) {{ window.open(url, '_blank'); }},
        onEvent: function() {{}},
        offEvent: function() {{}}
      }}
    }};
    console.log("[MOCK] Telegram.WebApp initialized, initData len=" + window.Telegram.WebApp.initData.length);
    """


async def main():
    cfg = dotenv_values(PROJECT_ROOT / ".env")
    bot_token = cfg.get("BOT_TOKEN")
    if not bot_token:
        print("ERROR: BOT_TOKEN не найден в .env")
        sys.exit(1)
    print(f"[init] bot_token loaded ({len(bot_token)} chars)")

    init_data = generate_init_data(bot_token, TEST_USER_ID, TEST_USERNAME)
    print(f"[init] initData ({len(init_data)} chars)")

    telegram_mock = build_telegram_mock(init_data, TEST_USER_ID, TEST_USERNAME)

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
        await context.route("**/*", block_tg_sdk)

        await context.add_init_script(telegram_mock)

        page = await context.new_page()

        console_msgs = []
        page_errors = []
        page.on("console", lambda msg: console_msgs.append(f"[{msg.type}] {msg.text}"))
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))

        print("\n[step] Открываю Mini App...")
        await page.goto(FRONTEND_URL, wait_until="domcontentloaded", timeout=15000)

        # Ждём пока React отрендерит
        for i in range(10):
            await asyncio.sleep(1)
            has_content = await page.evaluate("document.querySelector('.app') !== null")
            if has_content:
                print(f"[wait] App отрендерилась через {i+1}с")
                break

        # Скриншот 1: Welcome
        await page.screenshot(path=str(SCREENSHOTS_DIR / "01_welcome.png"))
        print(f"[shot] 01_welcome.png")

        text = await page.evaluate("document.body.innerText")
        print(f"[ui] Welcome: {text[:200]}")

        # Кликаем MainButton через колбэк
        clicked = await page.evaluate("""
            () => {
                if (typeof window.__mainButtonCallback === 'function') {
                    window.__mainButtonCallback();
                    return true;
                }
                return false;
            }
        """)
        print(f"[step] MainButton click on welcome: {clicked}")
        await asyncio.sleep(2)

        await page.screenshot(path=str(SCREENSHOTS_DIR / "02_after_welcome.png"))
        text = await page.evaluate("document.body.innerText")
        print(f"[ui] After welcome click: {text[:200]}")

        # Получаем текущее состояние экрана
        step = 1
        max_steps = 6
        while step < max_steps:
            await asyncio.sleep(1.5)
            screen_class = await page.evaluate("""
                (() => {
                    const screens = ['welcome-screen', 'install-screen', 'preparing-screen', 'connect-screen', 'waiting-screen', 'success-screen', 'dashboard'];
                    for (const s of screens) {
                        if (document.querySelector('.' + s)) return s;
                    }
                    return 'unknown';
                })()
            """)
            mb_text = await page.evaluate("window.__mainButtonText || ''")
            print(f"[step {step}] Screen: {screen_class}, MainButton text: {mb_text!r}")

            shot_path = SCREENSHOTS_DIR / f"step_{step}_{screen_class}.png"
            await page.screenshot(path=str(shot_path))

            clicked = await page.evaluate("""
                () => {
                    if (typeof window.__mainButtonCallback === 'function') {
                        window.__mainButtonCallback();
                        return true;
                    }
                    return false;
                }
            """)
            if not clicked:
                print(f"[step {step}] Нет MainButton callback - возможно экран без неё")
                break

            step += 1

        # Финальный скриншот
        await page.screenshot(path=str(SCREENSHOTS_DIR / f"99_final.png"))
        text = await page.evaluate("document.body.innerText")
        print(f"\n[final UI]:\n{text[:600]}")

        print(f"\n[stats] Console: {len(console_msgs)} msgs, errors: {len(page_errors)}")
        if page_errors:
            print("[!] Page errors:")
            for e in page_errors[:5]:
                print(f"  - {e[:300]}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())

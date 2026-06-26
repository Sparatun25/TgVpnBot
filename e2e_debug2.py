"""E2E debug v2 - block telegram-web-app.js (which overrides our mock), capture all responses."""
import asyncio
import hashlib
import hmac
import json
import sys
import time
import urllib.parse
from pathlib import Path

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


async def main():
    cfg = dotenv_values(PROJECT_ROOT / ".env")
    bot_token = cfg.get("BOT_TOKEN")
    if not bot_token:
        print("ERROR: BOT_TOKEN не найден")
        sys.exit(1)
    print(f"[init] bot_token loaded: {len(bot_token)} chars")

    init_data = generate_init_data(bot_token, TEST_USER_ID, TEST_USERNAME)
    print(f"[init] initData ({len(init_data)} chars) сгенерирован")

    telegram_mock = f"""
    window.__telegramReady = false;
    window.__apiCalls = [];
    window.__apiResponses = [];
    window.Telegram = {{
      WebApp: {{
        initData: {json.dumps(init_data)},
        initDataUnsafe: {{
          user: {{
            id: {TEST_USER_ID},
            first_name: "Test",
            username: "{TEST_USERNAME}",
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
        ready: function() {{ window.__telegramReady = true; }},
        expand: function() {{}},
        close: function() {{}},
        MainButton: {{
          _text: "",
          _shown: false,
          _cb: null,
          setText: function(t) {{ this._text = t; window.__mainButtonText = t; }},
          show: function() {{ this._shown = true; window.__mainButtonShown = true; }},
          hide: function() {{ this._shown = false; window.__mainButtonShown = false; }},
          enable: function() {{}},
          disable: function() {{}},
          showProgress: function() {{}},
          hideProgress: function() {{}},
          onClick: function(cb) {{ this._cb = cb; window.__mainButtonCallback = cb; }},
          offClick: function(cb) {{ this._cb = null; window.__mainButtonCallback = null; }}
        }},
        BackButton: {{
          show: function() {{}},
          hide: function() {{}},
          onClick: function(cb) {{ window.__backButtonCallback = cb; }},
          offClick: function(cb) {{}}
        }},
        HapticFeedback: {{
          impactOccurred: function() {{}},
          notificationOccurred: function() {{}},
          selectionChanged: function() {{}}
        }},
        openLink: function(url) {{ window.open(url, "_blank"); }},
        openTelegramLink: function(url) {{ window.open(url, "_blank"); }},
        onEvent: function() {{}},
        offEvent: function() {{}}
      }}
    }};
    // Intercept fetch
    const origFetch = window.fetch;
    window.fetch = function(...args) {{
      window.__apiCalls.push({{ url: String(args[0]), method: (args[1]?.method || 'GET'), time: Date.now() }});
      return origFetch.apply(this, args).then(async (resp) => {{
        const clone = resp.clone();
        let body = '';
        try {{ body = await clone.text(); }} catch(e) {{ body = '[binary]'; }}
        window.__apiResponses.push({{ url: String(args[0]), status: resp.status, body: body.substring(0, 300), time: Date.now() }});
        return resp;
      }});
    }};
    console.log("[MOCK] Telegram.WebApp + fetch interceptor ready, initData len=" + window.Telegram.WebApp.initData.length);
    """

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 390, "height": 844},
            device_scale_factor=2,
        )

        # Блокируем загрузку настоящего telegram-web-app.js чтобы не перетёр наш мок
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
        all_responses = []

        page.on("console", lambda msg: console_msgs.append(f"[{msg.type}] {msg.text}"))
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))
        page.on("response", lambda resp: all_responses.append((resp.status, resp.url, resp.request.method)))

        print("\n[step] Открываю frontend...")
        await page.goto(FRONTEND_URL, wait_until="domcontentloaded", timeout=15000)

        # Ждём пока React отрендерит что-то осмысленное
        for i in range(15):
            await asyncio.sleep(1)
            text = await page.evaluate("document.body.innerText")
            has_buttons = await page.evaluate("document.querySelectorAll('button').length")
            if (text and len(text) > 5) or has_buttons > 0:
                print(f"[wait] DOM готов через {i+1}с, text={text[:80]!r}, buttons={has_buttons}")
                break

        await page.screenshot(path=str(SCREENSHOTS_DIR / "01_initial.png"), full_page=False)

        state = await page.evaluate("""
            ({
                tgReady: window.__telegramReady,
                initDataLen: window.Telegram?.WebApp?.initData?.length || 0,
                initDataSample: window.Telegram?.WebApp?.initData?.substring(0, 80) || '',
                apiCalls: window.__apiCalls,
                apiResponses: window.__apiResponses,
                bodyText: document.body.innerText.substring(0, 500),
                rootHTML: document.getElementById('root')?.innerHTML?.substring(0, 800) || 'no root',
                buttonCount: document.querySelectorAll('button').length,
                buttonTexts: Array.from(document.querySelectorAll('button')).slice(0, 5).map(b => b.innerText)
            })
        """)
        print("\n[STATE]:")
        print(f"  tgReady: {state['tgReady']}")
        print(f"  initData length: {state['initDataLen']}")
        print(f"  body text: {state['bodyText']!r}")
        print(f"  root html: {state['rootHTML'][:400]}")
        print(f"  button count: {state['buttonCount']}")
        print(f"  button texts: {state['buttonTexts']}")
        print(f"  api calls ({len(state['apiCalls'])}):")
        for c in state['apiCalls']:
            print(f"    - {c['method']} {c['url']}")
        print(f"  api responses ({len(state['apiResponses'])}):")
        for r in state['apiResponses']:
            print(f"    - {r['status']} {r['url']} -> {r['body'][:200]}")

        print(f"\n[NETWORK] {len(all_responses)} responses:")
        for status, url, method in all_responses:
            if status >= 400 or '/api/' in url:
                print(f"  *** {status} {method} {url}")

        print(f"\n[CONSOLE] {len(console_msgs)} messages:")
        for m in console_msgs[:30]:
            print(f"  {m}")

        print(f"\n[ERRORS] {len(page_errors)} page errors:")
        for e in page_errors[:5]:
            print(f"  {e[:500]}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())

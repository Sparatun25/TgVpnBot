"""E2E debug test - captures all console messages, network requests and DOM state."""
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

    # Verify backend can decode it
    import urllib.request
    req = urllib.request.Request(
        "http://127.0.0.1:8000/api/profile",
        headers={"Authorization": f"Bearer {init_data}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            print(f"[verify] /api/profile → {r.status}")
            print(f"[verify] body: {r.read().decode()[:200]}")
    except urllib.error.HTTPError as e:
        print(f"[verify] /api/profile -> {e.code}: {e.read().decode()[:200]}")
    except Exception as e:
        print(f"[verify] /api/profile -> error: {e}")

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
    // Intercept fetch to log API calls
    const origFetch = window.fetch;
    window.fetch = function(...args) {{
      window.__apiCalls.push({{ url: args[0], method: (args[1]?.method || 'GET'), time: Date.now() }});
      return origFetch.apply(this, args).then(async (resp) => {{
        const clone = resp.clone();
        let body = '';
        try {{ body = await clone.text(); }} catch(e) {{ body = '[binary]'; }}
        window.__apiResponses.push({{ url: args[0], status: resp.status, body: body.substring(0, 200), time: Date.now() }});
        return resp;
      }});
    }};
    console.log("[MOCK] Telegram.WebApp + fetch interceptor ready");
    """

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 390, "height": 844},
            device_scale_factor=2,
        )
        await context.add_init_script(telegram_mock)

        page = await context.new_page()

        console_msgs = []
        page_errors = []

        page.on("console", lambda msg: console_msgs.append(f"[{msg.type}] {msg.text}"))
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))

        print("\n[step] Открываю frontend...")
        await page.goto(FRONTEND_URL, wait_until="domcontentloaded", timeout=15000)

        # Ждём пока React отрендерит что-то осмысленное
        for i in range(10):
            await asyncio.sleep(1)
            text = await page.evaluate("document.body.innerText")
            if text and len(text) > 5:
                print(f"[wait] DOM готов через {i+1}с, текст: {text[:150]!r}")
                break

        await page.screenshot(path=str(SCREENSHOTS_DIR / "01_initial.png"), full_page=False)

        # Проверяем состояние Telegram и fetch
        state = await page.evaluate("""
            ({
                tgReady: window.__telegramReady,
                initDataLen: window.Telegram?.WebApp?.initData?.length || 0,
                initDataSample: window.Telegram?.WebApp?.initData?.substring(0, 80) || '',
                apiCalls: window.__apiCalls,
                apiResponses: window.__apiResponses,
                bodyText: document.body.innerText.substring(0, 300),
                rootHTML: document.getElementById('root')?.innerHTML?.substring(0, 500) || 'no root'
            })
        """)
        print("\n[STATE]:")
        print(f"  tgReady: {state['tgReady']}")
        print(f"  initData length: {state['initDataLen']}")
        print(f"  initData sample: {state['initDataSample']}")
        print(f"  body text: {state['bodyText']!r}")
        print(f"  root html: {state['rootHTML'][:300]}")
        print(f"  api calls ({len(state['apiCalls'])}):")
        for c in state['apiCalls']:
            print(f"    - {c['method']} {c['url']}")
        print(f"  api responses ({len(state['apiResponses'])}):")
        for r in state['apiResponses']:
            print(f"    - {r['status']} {r['url']} → {r['body'][:150]}")

        print(f"\n[CONSOLE] {len(console_msgs)} messages:")
        for m in console_msgs[:30]:
            print(f"  {m}")

        print(f"\n[ERRORS] {len(page_errors)} page errors:")
        for e in page_errors[:5]:
            print(f"  {e[:300]}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())

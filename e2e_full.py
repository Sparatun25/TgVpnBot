"""E2E test for OnyxVpn Mini App.

Генерирует валидный initData, инжектит мок Telegram.WebApp ДО загрузки
приложения, проходит весь onboarding flow и сохраняет скриншоты.
"""
import asyncio
import hashlib
import hmac
import json
import os
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
    """Генерация валидного initData (HMAC-SHA256 по документации Telegram)."""
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
    # Сортируем по ключу и собираем data_check_string
    data_check_parts = [f"{k}={v}" for k, v in sorted(params.items())]
    data_check_string = "\n".join(data_check_parts)

    # secret_key = HMAC-SHA256(key="WebAppData", message=bot_token)
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    # hash = HMAC-SHA256(key=secret_key, message=data_check_string)
    hash_value = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    params["hash"] = hash_value
    return urllib.parse.urlencode(params)


async def main():
    cfg = dotenv_values(PROJECT_ROOT / ".env")
    bot_token = cfg.get("BOT_TOKEN")
    if not bot_token:
        print("ERROR: BOT_TOKEN не найден в .env")
        sys.exit(1)
    print(f"[init] BOT_TOKEN: {bot_token[:8]}...")

    init_data = generate_init_data(bot_token, TEST_USER_ID, TEST_USERNAME)
    print(f"[init] initData ({len(init_data)} chars) сгенерирован для user_id={TEST_USER_ID}")

    # JS для инжекта Telegram WebApp мока ДО загрузки React
    telegram_mock = f"""
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
        ready: function() {{}},
        expand: function() {{}},
        close: function() {{}},
        MainButton: {{
          setText: function(t) {{ window.__mainButtonText = t; }},
          show: function() {{ window.__mainButtonShown = true; }},
          hide: function() {{ window.__mainButtonShown = false; }},
          enable: function() {{ window.__mainButtonActive = true; }},
          disable: function() {{ window.__mainButtonActive = false; }},
          showProgress: function() {{}},
          hideProgress: function() {{}},
          onClick: function(cb) {{ window.__mainButtonCallback = cb; }},
          offClick: function(cb) {{ window.__mainButtonCallback = null; }}
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
    console.log("[MOCK] Telegram.WebApp инициализирован с валидным initData");
    """

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 390, "height": 844},
            device_scale_factor=2,
        )

        # Инжектим мок ДО любых скриптов
        await context.add_init_script(telegram_mock)

        page = await context.new_page()

        # Сбор логов и ошибок
        console_msgs = []
        page_errors = []
        network_errors = []

        page.on("console", lambda msg: console_msgs.append(f"[{msg.type}] {msg.text}"))
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))
        page.on("requestfailed", lambda req: network_errors.append(f"{req.method} {req.url} - {req.failure}"))

        print("[step] Открываю http://127.0.0.1:5173/")
        await page.goto(FRONTEND_URL, wait_until="networkidle", timeout=15000)
        await asyncio.sleep(2)

        # Скриншот 1: начальное состояние
        path1 = SCREENSHOTS_DIR / "01_initial.png"
        await page.screenshot(path=str(path1), full_page=False)
        print(f"[shot] {path1.name}")

        # Проверяем что отрендерилось
        body_text = await page.evaluate("document.body.innerText")
        print(f"[ui] Текст на экране: {body_text[:200]}")

        # Проверяем что Telegram WebApp инициализирован
        tg_ready = await page.evaluate("typeof window.Telegram?.WebApp?.initData")
        print(f"[tg] typeof initData: {tg_ready}")

        # Проходим flow — кликаем по MainButton через window.__mainButtonCallback
        step = 1
        max_steps = 8

        while step <= max_steps:
            await asyncio.sleep(1.5)
            mb_text = await page.evaluate("window.__mainButtonText || ''")
            mb_shown = await page.evaluate("window.__mainButtonShown || false")

            print(f"[step {step}] MainButton: shown={mb_shown}, text={mb_text!r}")

            shot_path = SCREENSHOTS_DIR / f"02_step_{step}_{mb_text[:20] or 'unknown'}.png"
            await page.screenshot(path=str(shot_path), full_page=False)

            if not mb_shown:
                # Проверяем — может уже dashboard
                url = page.url
                text = await page.evaluate("document.body.innerText")
                if "VPN" in text and "Тариф" not in text and "Trial" not in text:
                    print("[done] Похоже что мы на dashboard или другом экране без MainButton")
                    break
                # Проверяем есть ли inline-кнопка для перехода дальше
                buttons = await page.query_selector_all("button")
                print(f"[step {step}] Найдено {len(buttons)} кнопок на экране")
                for btn in buttons[:3]:
                    txt = await btn.inner_text()
                    visible = await btn.is_visible()
                    print(f"  - button: {txt[:40]!r} visible={visible}")

            # Вызываем MainButton callback
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
                print(f"[step {step}] Нет MainButton callback — flow завершён или стагнировал")
                break

            step += 1

        # Финальный скриншот
        final_path = SCREENSHOTS_DIR / f"99_final_step_{step}.png"
        await page.screenshot(path=str(final_path), full_page=False)
        print(f"[shot] {final_path.name}")

        # Финальный текст
        final_text = await page.evaluate("document.body.innerText")
        print(f"\n[final UI] Текст ({len(final_text)} chars):\n{final_text[:600]}")

        print(f"\n[stats] Console: {len(console_msgs)} msgs, errors: {len(page_errors)}, net errors: {len(network_errors)}")
        if page_errors:
            print("[!] Page errors:")
            for e in page_errors[:5]:
                print(f"  - {e[:200]}")
        if network_errors:
            print("[!] Network errors:")
            for e in network_errors[:5]:
                print(f"  - {e[:200]}")

        # Сводка по скриншотам
        shots = sorted(SCREENSHOTS_DIR.glob("*.png"))
        print(f"\n[shots] Всего скриншотов: {len(shots)}")
        for s in shots:
            print(f"  - {s.name}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())

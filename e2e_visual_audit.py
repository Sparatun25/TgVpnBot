"""Visual audit: walk through onboarding + dashboard, extract computed styles
and DOM details for each screen. No backend needed (mocks /api/* + Telegram).

Usage:
  python e2e_visual_audit.py
"""
import asyncio
import sys
from pathlib import Path
from playwright.async_api import async_playwright

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

PROJECT_ROOT = Path(__file__).resolve().parent
FRONTEND_URL = "http://127.0.0.1:5173/"
SHOTS = PROJECT_ROOT / "e2e_visual_audit"
SHOTS.mkdir(exist_ok=True)

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
      query_id: 'test_query', auth_date: Math.floor(Date.now() / 1000)
    },
    version: '6.0', platform: 'web', colorScheme: 'dark',
    themeParams: {
      bg_color: '#0B0B0C', text_color: '#FFFFFF', hint_color: '#8E8E93',
      link_color: '#7C3AED', button_color: '#7C3AED', button_text_color: '#FFFFFF',
      secondary_bg_color: '#1C1C1E'
    },
    ready: function() {}, expand: function() {}, close: function() {},
    MainButton: {
      _text: '', _shown: false, _active: true, _progress: false, _cb: null,
      text: '', color: '#7C3AED', textColor: '#FFFFFF', isVisible: false, isActive: true, isProgressVisible: false,
      setText: function(t) { this._text = t; this.text = t; window.__mainButtonText = t; },
      show: function() { this._shown = true; this.isVisible = true; window.__mainButtonShown = true; },
      hide: function() { this._shown = false; this.isVisible = false; window.__mainButtonShown = false; },
      enable: function() { this._active = true; this.isActive = true; },
      disable: function() { this._active = false; this.isActive = false; },
      showProgress: function(leaveActive) { this._progress = true; this.isProgressVisible = true; },
      hideProgress: function(leaveActive) { this._progress = false; this.isProgressVisible = false; },
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
    HapticFeedback: { impactOccurred: function() {}, notificationOccurred: function() {}, selectionChanged: function() {} },
    openLink: function(url) { window.open(url, '_blank'); },
    openTelegramLink: function(url) { window.open(url, '_blank'); },
    onEvent: function() {}, offEvent: function() {}
  }
};
"""

# Returns full audit data for the currently rendered screen.
AUDIT_JS = """
() => {
  const pick = (el, props) => {
    if (!el) return null;
    const cs = window.getComputedStyle(el);
    const out = {};
    for (const p of props) {
      const v = cs.getPropertyValue(p);
      out[p] = v.length > 80 ? v.slice(0, 80) + '…' : v;
    }
    out.text = el.textContent ? el.textContent.trim().slice(0, 120) : '';
    out.bounding = (() => {
      const r = el.getBoundingClientRect();
      return r.width > 0 ? `${Math.round(r.width)}x${Math.round(r.height)}@${Math.round(r.left)},${Math.round(r.top)}` : 'hidden';
    })();
    return out;
  };

  return {
    url: location.href,
    viewport: { w: window.innerWidth, h: window.innerHeight },
    body_classes: document.body.className,
    onboarding_screen: !!document.querySelector('.onboarding-screen'),
    welcome: !!document.querySelector('.welcome-screen'),
    install: !!document.querySelector('.install-screen'),
    preparing: !!document.querySelector('.preparing-screen'),
    connect: !!document.querySelector('.connect-screen'),
    waiting: !!document.querySelector('.waiting-screen'),
    success: !!document.querySelector('.success-screen'),
    dashboard: !!document.querySelector('.dashboard-screen'),
    main_button: { text: window.__mainButtonText, shown: window.__mainButtonShown },
    visible_text: document.body.innerText.slice(0, 600),
    title: pick(document.querySelector('.welcome-title, .install-title, .preparing-title, .connect-title, .waiting-title, .success-title, .dashboard-greeting, h1, h2'),
      ['color', 'font-size', 'font-weight', 'font-family', 'line-height']),
    cat_svg: (() => {
      const svg = document.querySelector('.welcome-orb__core svg');
      if (!svg) return null;
      const r = svg.getBoundingClientRect();
      return {
        size: `${Math.round(r.width)}x${Math.round(r.height)}`,
        visible: r.width > 0 && r.height > 0,
        shield_present: !!svg.querySelector('path[fill="url(#shield-grad)"]'),
        vpn_label: svg.querySelector('text')?.textContent || null,
        child_count: svg.children.length,
      };
    })(),
    accent_color: window.getComputedStyle(document.documentElement).getPropertyValue('--tg-button').trim() || null,
    bg_color: window.getComputedStyle(document.documentElement).getPropertyValue('--tg-bg').trim() || null,
    primary_color: window.getComputedStyle(document.documentElement).getPropertyValue('--onyx-accent').trim() || null,
  };
}
"""


async def wait_for_step(page, marker_js, attempts=20, delay=0.5):
    """Poll until marker_js returns truthy or attempts exhausted."""
    for i in range(attempts):
        try:
            ok = await page.evaluate(marker_js)
            if ok:
                return True
        except Exception:
            pass
        await asyncio.sleep(delay)
    return False


async def snapshot(page, name):
    path = str(SHOTS / f"{name}.png")
    await page.screenshot(path=path)
    data = await page.evaluate(AUDIT_JS)
    print(f"\n{'=' * 70}\n{name.upper()}\n{'=' * 70}")
    for k, v in data.items():
        if k == 'visible_text':
            print(f"  text: {v[:300].replace(chr(10), ' | ')}")
        elif isinstance(v, dict):
            print(f"  {k}:")
            for kk, vv in v.items():
                print(f"    {kk}: {vv}")
        else:
            print(f"  {k}: {v}")
    return data


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
        await context.route("**/*", block_tg_sdk)

        async def mock_api(route):
            url = route.request.url
            if "/api/profile" in url:
                await route.fulfill(
                    status=200,
                    content_type="application/json",
                    body='{"subscription":{"active":false,"expires_at":null,"plan_type":null,"connection_url":null},"has_used_trial":false,"balance":0,"referral_code":"ONYXTEST","referral_count":0}',
                )
            elif "/api/subscription/trial" in url:
                await route.fulfill(
                    status=200,
                    content_type="application/json",
                    body='{"subscription":{"active":true,"expires_at":"2026-06-29T00:00:00Z","plan_type":"trial","connection_url":"vpn://test-key-AAA"},"has_used_trial":true,"balance":0,"referral_code":"ONYXTEST","referral_count":0}',
                )
            elif "/api/subscription/status" in url:
                await route.fulfill(
                    status=200,
                    content_type="application/json",
                    body='{"active":true,"auto_advance_eligible":true,"expires_at":"2026-06-29T00:00:00Z"}',
                )
            else:
                await route.continue_()
        await context.route("**/api/**", mock_api)

        await context.add_init_script(TELEGRAM_MOCK)
        page = await context.new_page()
        page.on("pageerror", lambda exc: print(f"[pageerror] {exc}"))

        print("[step] Loading app...")
        await page.goto(FRONTEND_URL, wait_until="domcontentloaded", timeout=15000)
        await wait_for_step(page, "document.querySelector('.onboarding-screen') !== null", attempts=15)
        await asyncio.sleep(2)  # let entrance animations settle

        await snapshot(page, "01_welcome")

        # Welcome → Install (click MainButton)
        await page.evaluate("window.__mainButtonCallback && window.__mainButtonCallback()")
        await wait_for_step(page, "document.querySelector('.install-screen') !== null")
        await asyncio.sleep(1)
        await snapshot(page, "02_install")

        # Install → Preparing
        await page.evaluate("window.__mainButtonCallback && window.__mainButtonCallback()")
        await wait_for_step(page, "document.querySelector('.preparing-screen') !== null")
        await asyncio.sleep(2)
        await snapshot(page, "03_preparing")

        # Preparing completes internally after 4.5s, then shows .preparing-cta "Продолжить"
        await wait_for_step(
            page,
            "document.querySelector('.preparing-cta') !== null",
            attempts=20,
        )
        await snapshot(page, "03b_preparing_done")

        # Click .preparing-cta to trigger activateTrial + advance to Connect
        await page.click(".preparing-cta")
        await wait_for_step(page, "document.querySelector('.connect-screen') !== null", attempts=30)
        await asyncio.sleep(1)
        await snapshot(page, "04_connect")

        # Connect → Waiting (MainButton should be present)
        await wait_for_step(page, "window.__mainButtonCallback !== null", attempts=10)
        await page.evaluate("window.__mainButtonCallback && window.__mainButtonCallback()")
        await wait_for_step(page, "document.querySelector('.waiting-screen') !== null")
        await asyncio.sleep(1)
        await snapshot(page, "05_waiting")

        # Waiting → Success (auto via setTimeout in component)
        await wait_for_step(page, "document.querySelector('.success-screen') !== null", attempts=30)
        await asyncio.sleep(1)
        await snapshot(page, "06_success")

        # Success → Dashboard (SuccessScreen has its own .success-cta button)
        await wait_for_step(page, "document.querySelector('.success-cta') !== null")
        await page.click(".success-cta")
        await wait_for_step(page, "document.querySelector('.dashboard-screen') !== null")
        await asyncio.sleep(2)
        await snapshot(page, "07_dashboard")

        print(f"\n[shots] Saved to {SHOTS}/")
        await browser.close()


asyncio.run(main())

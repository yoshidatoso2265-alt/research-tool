"""Playwright + stealth ヘルパー。

mercari / paypay_furima / rakuma が共通で使う bot 検知回避のためのコンテキスト生成。
playwright-stealth が `navigator.webdriver` を消し、WebGL/Canvas 指紋などを補正する。
"""
from playwright.async_api import async_playwright

try:
    from playwright_stealth import stealth_async
except ImportError:
    async def stealth_async(page):
        return None


STEALTH_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Safari/537.36"
)


async def launch_stealth(p):
    """async_playwright() のコンテキスト内で呼ぶ。browser, context を返す。

    実 Chrome がインストールされていれば優先的に使用（Chromium より bot 検知に強い）。
    """
    launch_args = dict(
        headless=True,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--disable-features=IsolateOrigins,site-per-process",
            "--no-sandbox",
        ],
    )
    try:
        browser = await p.chromium.launch(channel="chrome", **launch_args)
    except Exception:
        browser = await p.chromium.launch(**launch_args)
    context = await browser.new_context(
        user_agent=STEALTH_USER_AGENT,
        locale="ja-JP",
        timezone_id="Asia/Tokyo",
        viewport={"width": 1280, "height": 800},
        extra_http_headers={
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        },
    )
    return browser, context


async def apply_stealth(page):
    """各 page 生成後に呼ぶ。"""
    try:
        await stealth_async(page)
    except Exception:
        pass

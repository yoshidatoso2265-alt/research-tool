import asyncio
import re
from typing import List
from urllib.parse import quote
from playwright.async_api import async_playwright, BrowserContext

from core.models import Item

SITE = "ラクマ"
LIST_BASE = "https://fril.jp"
ITEM_BASE = "https://item.fril.jp"
MAX_DETAIL_FETCH = 500  # 実質無制限
DETAIL_PARALLEL = 4
MAX_LIST_PAGES = 5


async def search(keyword: str) -> List[Item]:
    url = f"{LIST_BASE}/s?query={quote(keyword)}&transaction=selling"
    items: List[Item] = []
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(locale="ja-JP")
            page = await context.new_page()
            preliminary = []
            seen = set()
            for page_num in range(1, MAX_LIST_PAGES + 1):
                page_url = url + (f"&page={page_num}" if page_num > 1 else "")
                await page.goto(page_url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(5000)
                cards = await page.query_selector_all(".item")
                if not cards:
                    break
                page_added = 0
                for c in cards:
                    try:
                        a = await c.query_selector("a[href*='item.fril.jp']")
                        if not a:
                            continue
                        href = await a.get_attribute("href")
                        if not href or href in seen:
                            continue
                        sold_marker = await c.query_selector(".item-sold, [class*='sold'], .item-status-sold")
                        if sold_marker:
                            continue
                        seen.add(href)
                        img = await c.query_selector("img")
                        image = await img.get_attribute("src") if img else None
                        txt = await c.inner_text()
                        if "SOLD" in txt.upper() or "売り切れ" in txt:
                            continue
                        price = _extract_price(txt)
                        preliminary.append({"url": href, "image": image, "price": price})
                        page_added += 1
                        if len(preliminary) >= MAX_DETAIL_FETCH:
                            break
                    except Exception:
                        continue
                if page_added == 0 or len(preliminary) >= MAX_DETAIL_FETCH:
                    break
            await page.close()
            print(f"[{SITE}] 一覧から{len(preliminary)}件のURLを取得 → 詳細ページ取得開始")

            sem = asyncio.Semaphore(DETAIL_PARALLEL)

            async def fetch(prelim):
                async with sem:
                    return await _fetch_detail(context, prelim)

            results = await asyncio.gather(*[fetch(p) for p in preliminary], return_exceptions=True)
            for r in results:
                if isinstance(r, Item):
                    items.append(r)

            await browser.close()
    except Exception as e:
        print(f"[{SITE}] error: {e}")
    return items


async def _fetch_detail(context: BrowserContext, prelim: dict):
    url = prelim["url"]
    page = await context.new_page()
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2500)

        title = ""
        og = await page.query_selector('meta[property="og:title"]')
        if og:
            t = (await og.get_attribute("content")) or ""
            title = re.sub(r"\s*\|\s*フリマアプリ.*$", "", t).strip()

        desc = None
        og_d = await page.query_selector('meta[property="og:description"]')
        if og_d:
            desc = ((await og_d.get_attribute("content")) or "")[:1000]

        html = await page.content()
        location = None
        m = re.search(r'発送元の地域</th>\s*<td[^>]*>\s*([^<]+?)\s*<', html)
        if m:
            location = m.group(1).strip()[:30]
        condition = None
        m = re.search(r'商品の状態</th>\s*<td[^>]*>\s*([^<]+?)\s*<', html)
        if m:
            condition = m.group(1).strip()[:20]

        shipping_method = None
        m = re.search(r'配送料の負担</th>\s*<td[^>]*>\s*([^<]+?)\s*<', html)
        if m:
            shipping_method = m.group(1).strip()[:30]
        m = re.search(r'配送方法</th>\s*<td[^>]*>\s*([^<]+?)\s*<', html)
        if m:
            sm = m.group(1).strip()[:30]
            shipping_method = f"{sm} / {shipping_method}" if shipping_method else sm

        # 販売中チェック (URLが /sold/ なら売切れ)
        if "sold" in url.lower():
            await page.close()
            return None

        await page.close()
        if not title:
            return None
        return Item(
            site=SITE, title=title, price=prelim.get("price"),
            condition=condition or "中古",
            image_url=prelim.get("image"),
            item_url=url, in_stock=True,
            description=desc, location=location,
            shipping_method=shipping_method,
        )
    except Exception:
        try:
            await page.close()
        except Exception:
            pass
        return None


def _extract_price(text: str):
    if not text:
        return None
    m = re.search(r"¥\s*([\d,]+)", text) or re.search(r"([\d,]+)\s*円", text)
    if m:
        try:
            v = int(m.group(1).replace(",", ""))
            if 100 <= v <= 100_000_000:
                return v
        except ValueError:
            pass
    return None


if __name__ == "__main__":
    import sys
    items = asyncio.run(search(sys.argv[1] if len(sys.argv) > 1 else "Panasonic NR-B18C2"))
    print(f"取得件数: {len(items)}")
    for it in items[:5]:
        print(f"{it.price} | {it.title[:60]} | {it.location} | {it.condition}")

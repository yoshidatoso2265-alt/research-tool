import asyncio
import re
from typing import List
from urllib.parse import quote
from playwright.async_api import async_playwright, BrowserContext

from core.models import Item

SITE = "PayPayフリマ"
BASE = "https://paypayfleamarket.yahoo.co.jp"
MAX_DETAIL_FETCH = 500  # 実質無制限
DETAIL_PARALLEL = 4


async def search(keyword: str) -> List[Item]:
    url = f"{BASE}/search/{quote(keyword)}?status=open&sort=ccon&order=asc"
    items: List[Item] = []
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(locale="ja-JP")

            page = await context.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(4000)

            cards = await page.query_selector_all("a[href*='/item/']")
            seen = set()
            preliminary = []
            for c in cards:
                href = await c.get_attribute("href")
                if not href or "/item/" not in href:
                    continue
                if not href.startswith("http"):
                    href = BASE + href
                if href in seen:
                    continue
                seen.add(href)
                img_el = await c.query_selector("img")
                image = await img_el.get_attribute("src") if img_el else None
                full_text = await c.inner_text() if c else ""
                price = _extract_price(full_text)
                preliminary.append({"url": href, "image": image, "price": price})
                if len(preliminary) >= MAX_DETAIL_FETCH:
                    break
            await page.close()

            sem = asyncio.Semaphore(DETAIL_PARALLEL)

            async def fetch_detail(prelim):
                async with sem:
                    return await _fetch_detail_page(context, prelim)

            results = await asyncio.gather(
                *[fetch_detail(p) for p in preliminary],
                return_exceptions=True,
            )
            for r in results:
                if isinstance(r, Item):
                    items.append(r)

            await browser.close()
    except Exception as e:
        print(f"[{SITE}] error: {e}")
    return items


async def _fetch_detail_page(context: BrowserContext, prelim: dict):
    url = prelim["url"]
    page = await context.new_page()
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        try:
            await page.wait_for_selector("h1", timeout=8000)
        except Exception:
            await page.wait_for_timeout(3000)

        # og:title が最も確実 (h1は描画タイミング次第で空のことがある)
        title = ""
        og = await page.query_selector('meta[property="og:title"]')
        if og:
            t = (await og.get_attribute("content")) or ""
            # "...｜Yahoo!フリマ（旧PayPayフリマ）" のサフィックスを削除
            title = re.sub(r"[\s|｜]+Yahoo!フリマ.*$", "", t).strip()
        if not title:
            h1 = await page.query_selector("h1")
            if h1:
                try:
                    title = (await h1.inner_text()).strip()
                except Exception:
                    pass

        html = await page.content()

        # 発送元の地域・商品の状態 はテーブル構造、HTMLに含まれているのでregexで抽出
        location = None
        m = re.search(r'発送元の地域</span></th>\s*<td[^>]*>\s*<span[^>]*>([^<]+)</span>', html)
        if m:
            location = m.group(1).strip()[:30]

        condition = None
        m = re.search(r'商品の状態</span></th>\s*<td[^>]*>\s*<span[^>]*>([^<]+)</span>', html)
        if m:
            condition = m.group(1).strip()[:20]

        shipping_method = None
        m = re.search(r'配送の方法</span></th>\s*<td[^>]*>\s*<span[^>]*>([^<]+)</span>', html)
        if m:
            shipping_method = m.group(1).strip()[:30]
        m = re.search(r'配送料の負担</span></th>\s*<td[^>]*>\s*<span[^>]*>([^<]+)</span>', html)
        if m:
            payer = m.group(1).strip()[:20]
            if shipping_method:
                shipping_method = f"{shipping_method} / {payer}"
            else:
                shipping_method = payer

        # 説明文 (og:description)
        desc = None
        og_desc = await page.query_selector('meta[property="og:description"]')
        if og_desc:
            desc = ((await og_desc.get_attribute("content")) or "")[:500]

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
    m = re.search(r"([\d,]+)", text.replace("¥", "").replace("￥", ""))
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

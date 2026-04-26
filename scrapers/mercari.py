import asyncio
import re
from typing import List
from urllib.parse import quote
from playwright.async_api import async_playwright, BrowserContext

from core.models import Item
from core.browser import launch_stealth, apply_stealth

SITE = "メルカリ"
BASE = "https://jp.mercari.com"
DETAIL_PARALLEL = 4
HARD_PAGE_LIMIT = 50  # 安全装置（事故時の暴走防止のみ。50ページ=約1500件）

# 注: メルカリは Akamai/独自 bot 検知が強く、無料の playwright-stealth では
# クライアント側 fetch がサイレントブロックされ skeleton で固まることが多い。
# 確実に取りたい場合の選択肢:
#   1. Apify Mercari Scraper を使う（Free tier $5/月以内で運用可能）
#   2. ユーザーがログイン済みの実 Chrome profile を流用する
#      (browser launch に user_data_dir を指定 + headed mode)


async def search(keyword: str) -> List[Item]:
    url = f"{BASE}/search?keyword={quote(keyword)}&status=on_sale&order=asc&sort=price"
    items: List[Item] = []
    try:
        async with async_playwright() as p:
            browser, context = await launch_stealth(p)

            # 1. 一覧ページからURL収集（全ページ走査・上限なし）
            page = await context.new_page()
            await apply_stealth(page)
            seen_urls = set()
            preliminary = []

            for page_num in range(1, HARD_PAGE_LIMIT + 1):
                page_url = url + (f"&page_token=v1:{page_num}" if page_num > 1 else "")
                await page.goto(page_url, wait_until="domcontentloaded", timeout=30000)
                # 人間的な操作で API fetch を発火させる
                try:
                    await page.mouse.move(400, 300)
                    await page.mouse.wheel(0, 400)
                except Exception:
                    pass
                await page.wait_for_timeout(2000)
                try:
                    await page.wait_for_load_state("networkidle", timeout=20000)
                except Exception:
                    pass
                try:
                    await page.wait_for_selector(
                        "li[data-testid='item-cell'], a[data-testid='thumbnail-link']",
                        timeout=10000,
                    )
                except Exception:
                    pass

                cards = await page.query_selector_all("li[data-testid='item-cell']")
                if not cards:
                    # フォールバック: 旧 testid が外れた場合
                    cards = await page.query_selector_all(
                        "a[data-testid='thumbnail-link'], a[href*='/item/m']"
                    )
                if not cards:
                    break
                page_added = 0
                for c in cards:
                    try:
                        # cards 自体が <a> の場合と、内側に <a> を持つ <li> の場合の両対応
                        link_el = c if (await c.evaluate("e => e.tagName")) == "A" else await c.query_selector("a")
                        if not link_el:
                            continue
                        href = await link_el.get_attribute("href")
                        if not href:
                            continue
                        if not href.startswith("http"):
                            href = BASE + href
                        if href in seen_urls:
                            continue
                        if "/item/" not in href and "/shops/product/" not in href:
                            continue
                        seen_urls.add(href)
                        img_el = await c.query_selector("img")
                        image = await img_el.get_attribute("src") if img_el else None
                        price_el = await c.query_selector("[class*='merPrice'], [class*='price'], [data-testid='price']")
                        price_text = await price_el.inner_text() if price_el else ""
                        price = _extract_price(price_text)
                        preliminary.append({"url": href, "image": image, "price": price})
                        page_added += 1
                    except Exception:
                        continue
                if page_added == 0:
                    break
            await page.close()
            print(f"[{SITE}] 一覧から{len(preliminary)}件のURLを取得 → 詳細ページ取得開始")

            # 2. 各詳細ページを並列で開いてフルタイトル等を取得
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
        # 発送元セレクタが現れるまで待つ（最大8秒）
        try:
            await page.wait_for_selector('span[data-testid="発送元の地域"]', timeout=8000)
        except Exception:
            await page.wait_for_timeout(3000)

        title = ""
        for sel in ["h1[class*='heading']", "[data-testid='item-name']", "h1", "meta[property='og:title']"]:
            el = await page.query_selector(sel)
            if el:
                t = (await el.get_attribute("content")) if "meta" in sel else None
                if not t:
                    try:
                        t = (await el.inner_text()).strip()
                    except Exception:
                        t = ""
                if t:
                    title = t
                    break

        desc = ""
        for sel in ["[data-testid='item-description']", "[class*='description']", "meta[name='description']"]:
            el = await page.query_selector(sel)
            if el:
                t = (await el.get_attribute("content")) if "meta" in sel else None
                if not t:
                    try:
                        t = (await el.inner_text()).strip()
                    except Exception:
                        t = ""
                if t:
                    desc = t[:500]
                    break

        # 発送元の地域 (Mercari固有: data-testid属性で抽出)
        location = None
        loc_el = await page.query_selector('span[data-testid="発送元の地域"]')
        if loc_el:
            try:
                location = (await loc_el.inner_text()).strip()[:30]
            except Exception:
                pass

        condition = None
        cond_el = await page.query_selector('span[data-testid="商品の状態"]')
        if cond_el:
            try:
                condition = (await cond_el.inner_text()).strip()[:20]
            except Exception:
                pass

        shipping_method = None
        sm_el = await page.query_selector('span[data-testid="配送の方法"]')
        if sm_el:
            try:
                shipping_method = (await sm_el.inner_text()).strip()[:30]
            except Exception:
                pass

        shipping_payer = None
        sp_el = await page.query_selector('span[data-testid="配送料の負担"]')
        if sp_el:
            try:
                shipping_payer = (await sp_el.inner_text()).strip()[:20]
                # 「(税込) 送料込み」のように shipping_method に組み合わせ
                if shipping_method and shipping_payer:
                    shipping_method = f"{shipping_method} / {shipping_payer}"
                elif shipping_payer and not shipping_method:
                    shipping_method = shipping_payer
            except Exception:
                pass

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
        print(f"{it.price} | {it.title[:60]} | {it.location}")

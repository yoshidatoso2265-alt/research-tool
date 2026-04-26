import asyncio
import re
from typing import List
from urllib.parse import urljoin, quote
from playwright.async_api import async_playwright

from core.models import Item
from core.browser import launch_stealth, apply_stealth

SITE = "セカンドストリート"
BASE = "https://www.2ndstreet.jp"
HARD_PAGE_LIMIT = 50  # Akamai bot challenge 経由のため Playwright 必須


async def search(keyword: str) -> List[Item]:
    items: List[Item] = []
    seen = set()
    try:
        async with async_playwright() as p:
            browser, context = await launch_stealth(p)
            page = await context.new_page()
            await apply_stealth(page)

            for page_num in range(1, HARD_PAGE_LIMIT + 1):
                url = f"{BASE}/search?keyword={quote(keyword)}"
                if page_num > 1:
                    url += f"&page={page_num}"
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                # Akamai challenge を抜けるための待機
                try:
                    await page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:
                    pass
                await page.wait_for_timeout(2500)

                cards = await page.query_selector_all("a[href*='/goods/detail']")
                if not cards:
                    break
                page_added = 0
                for a in cards:
                    href = await a.get_attribute("href")
                    if not href:
                        continue
                    item_url = urljoin(BASE, href)
                    if item_url in seen:
                        continue
                    seen.add(item_url)

                    # カード単位の親要素から title / price / image を取得
                    parent = await a.evaluate_handle("el => el.closest('li, article, div[class*=\"Card\"]') || el.parentElement")

                    # 親カードの innerText を行に分割し、商品名らしき行を選ぶ
                    title = ""
                    try:
                        ft = await parent.evaluate("e => e.innerText")
                        lines = [ln.strip() for ln in ft.split("\n") if ln.strip()]
                        # ブランド名（「その他ブランド」「Panasonic」等）の次に来る商品名を選ぶ
                        skipped_brand = False
                        for ln in lines:
                            if (
                                ln.startswith("¥")
                                or "商品の状態" in ln
                                or re.fullmatch(r"中古[A-Z]?", ln)
                                or len(ln) < 4
                            ):
                                continue
                            if not skipped_brand and ("ブランド" in ln or len(ln) <= 12):
                                skipped_brand = True
                                continue
                            title = ln[:200]
                            break
                    except Exception:
                        pass
                    img_el = await a.query_selector("img")
                    if not title and img_el:
                        alt = await img_el.get_attribute("alt")
                        if alt:
                            title = alt.strip()

                    image_url = None
                    if img_el:
                        image_url = await img_el.get_attribute("src") or await img_el.get_attribute("data-src")
                        if image_url and not image_url.startswith("http"):
                            image_url = urljoin(BASE, image_url)

                    # 価格は親要素のテキスト全体から抜く
                    price = None
                    try:
                        full_text = await parent.evaluate("e => e.innerText")
                        price = _extract_price(full_text)
                    except Exception:
                        pass

                    # 商品の状態 (例: 中古A, 中古B)
                    condition = "中古"
                    try:
                        ft = await parent.evaluate("e => e.innerText")
                        m = re.search(r"中古[A-Z]?", ft)
                        if m:
                            condition = m.group(0)
                    except Exception:
                        pass

                    items.append(Item(
                        site=SITE, title=title or "(タイトル不明)", price=price,
                        condition=condition, image_url=image_url,
                        item_url=item_url, in_stock=price is not None,
                    ))
                    page_added += 1
                if page_added == 0:
                    break
            await browser.close()
    except Exception as e:
        print(f"[{SITE}] error: {e}")
    return items


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
    items = asyncio.run(search(sys.argv[1] if len(sys.argv) > 1 else "PSP-3000"))
    print(f"取得件数: {len(items)}")
    for it in items[:5]:
        print(f"{it.price} | {it.title[:60]} | {it.condition}")
